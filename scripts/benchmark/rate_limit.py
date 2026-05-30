"""Rate-limit detection, reset extraction, and capped wait/retry helpers."""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.run_status import payload_hit_usage_limit
from benchmark.util import USAGE_LIMIT_REACHED, contains_usage_limit, print_line

DEFAULT_RATE_LIMIT_WAIT_CAP_HOURS = 6
DEFAULT_RATE_LIMIT_BACKOFF_INITIAL_SECONDS = 60
DEFAULT_RATE_LIMIT_BACKOFF_MAX_SECONDS = 900
DEFAULT_RATE_LIMIT_POLL_INTERVAL_SECONDS = 1800
_RATE_LIMIT_JITTER_SECONDS = 30

_RESETS_AT_KEYS = ("resetsAt", "resets_at", "reset_at")
_RETRY_AFTER_KEYS = ("retry_after", "retry-after", "retryAfter")
_SESSION_LIMIT_RE = re.compile(r"session\s+limit", re.IGNORECASE)
_RESETS_AT_TEXT_RE = re.compile(
    r"resets?\s+(?:at\s+)?(\d{1,2}:\d{2}\s*(?:am|pm)?(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)
_RETRY_AFTER_SECONDS_RE = re.compile(
    r"retry\s+(?:after|in)\s+(\d+)\s*(second|minute|hour)s?",
    re.IGNORECASE,
)
# Match HTTP 429 / API status 429, not unrelated digit runs (e.g. ls -la byte counts).
_STANDALONE_429_RE = re.compile(r"(?<![0-9])429(?![0-9])")


@dataclass(frozen=True)
class RateLimitWaitPolicy:
    """Capped wait/backoff settings for provider throttling."""

    cap_seconds: int = DEFAULT_RATE_LIMIT_WAIT_CAP_HOURS * 3600
    backoff_initial_seconds: int = DEFAULT_RATE_LIMIT_BACKOFF_INITIAL_SECONDS
    backoff_max_seconds: int = DEFAULT_RATE_LIMIT_BACKOFF_MAX_SECONDS
    poll_interval_seconds: int = DEFAULT_RATE_LIMIT_POLL_INTERVAL_SECONDS


def add_rate_limit_cli_args(parser: argparse.ArgumentParser) -> None:
    """Register shared rate-limit wait/retry flags on ``parser``."""
    parser.add_argument(
        "--rate-limit-wait-cap-hours",
        type=int,
        default=DEFAULT_RATE_LIMIT_WAIT_CAP_HOURS,
        help=(
            "Max total wait time when a run hits provider usage/rate limits "
            f"(default: {DEFAULT_RATE_LIMIT_WAIT_CAP_HOURS}h)."
        ),
    )
    parser.add_argument(
        "--rate-limit-backoff-initial-seconds",
        type=int,
        default=DEFAULT_RATE_LIMIT_BACKOFF_INITIAL_SECONDS,
        help="Initial backoff when no explicit reset time is available.",
    )
    parser.add_argument(
        "--rate-limit-backoff-max-seconds",
        type=int,
        default=DEFAULT_RATE_LIMIT_BACKOFF_MAX_SECONDS,
        help="Maximum backoff interval when reset time is unknown.",
    )
    parser.add_argument(
        "--rate-limit-poll-interval-seconds",
        type=int,
        default=DEFAULT_RATE_LIMIT_POLL_INTERVAL_SECONDS,
        help=(
            "Max sleep before retrying after a rate limit (checks whether the "
            f"limit recharged; default: {DEFAULT_RATE_LIMIT_POLL_INTERVAL_SECONDS}s / 30min)."
        ),
    )


def rate_limit_policy_from_args(args: argparse.Namespace) -> RateLimitWaitPolicy:
    """Build a :class:`RateLimitWaitPolicy` from parsed CLI args."""
    cap_hours = getattr(args, "rate_limit_wait_cap_hours", DEFAULT_RATE_LIMIT_WAIT_CAP_HOURS)
    if cap_hours < 0:
        raise ValueError(f"rate_limit_wait_cap_hours must be >= 0, got {cap_hours}")
    initial = getattr(
        args, "rate_limit_backoff_initial_seconds", DEFAULT_RATE_LIMIT_BACKOFF_INITIAL_SECONDS
    )
    maximum = getattr(
        args, "rate_limit_backoff_max_seconds", DEFAULT_RATE_LIMIT_BACKOFF_MAX_SECONDS
    )
    poll_interval = getattr(
        args, "rate_limit_poll_interval_seconds", DEFAULT_RATE_LIMIT_POLL_INTERVAL_SECONDS
    )
    if initial <= 0:
        raise ValueError(f"rate_limit_backoff_initial_seconds must be > 0, got {initial}")
    if maximum < initial:
        raise ValueError(
            f"rate_limit_backoff_max_seconds ({maximum}) must be >= "
            f"rate_limit_backoff_initial_seconds ({initial})"
        )
    if poll_interval <= 0:
        raise ValueError(f"rate_limit_poll_interval_seconds must be > 0, got {poll_interval}")
    return RateLimitWaitPolicy(
        cap_seconds=cap_hours * 3600,
        backoff_initial_seconds=initial,
        backoff_max_seconds=maximum,
        poll_interval_seconds=poll_interval,
    )


def text_looks_rate_limited(text: str) -> bool:
    """Return True when free-form text looks like a provider throttle message."""
    if not text:
        return False
    if contains_usage_limit(text):
        return True
    if _SESSION_LIMIT_RE.search(text):
        return True
    lowered = text.lower()
    return bool(_STANDALONE_429_RE.search(lowered)) or '"error":"rate_limit"' in lowered


def _rate_limit_info_rejected(info: dict[str, Any]) -> bool:
    """True when Claude rate_limit_info indicates the request was throttled."""
    return info.get("status") == "rejected"


def stream_event_looks_rate_limited(event: dict[str, Any]) -> bool:
    """Return True when one NDJSON stream event indicates throttling."""
    if event.get("type") == "rate_limit_event":
        info = event.get("rate_limit_info")
        return isinstance(info, dict) and _rate_limit_info_rejected(info)
    if event.get("error") == "rate_limit":
        return True
    if event.get("api_error_status") == 429:
        return True
    rate_info = event.get("rate_limit_info")
    if isinstance(rate_info, dict) and _rate_limit_info_rejected(rate_info):
        return True
    return text_looks_rate_limited(json.dumps(event))


def _coerce_reset_timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return ts if ts > 0 else None
    if isinstance(value, str) and value.isdigit():
        return _coerce_reset_timestamp(int(value))
    return None


def _wait_from_reset_timestamp(reset_at: int, *, now: float | None = None) -> int | None:
    current = int(now if now is not None else time.time())
    wait = reset_at - current
    return wait if wait > 0 else 0


def _wait_from_retry_after(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        return seconds if seconds > 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return _wait_from_retry_after(int(stripped))
        match = _RETRY_AFTER_SECONDS_RE.search(stripped)
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("minute"):
            return amount * 60
        if unit.startswith("hour"):
            return amount * 3600
        return amount
    return None


def _scan_json_obj(obj: Any, *, now: float) -> int | None:
    if isinstance(obj, dict):
        if obj.get("type") == "rate_limit_event":
            info = obj.get("rate_limit_info")
            if not isinstance(info, dict) or not _rate_limit_info_rejected(info):
                return None
            for key in _RESETS_AT_KEYS:
                reset_at = _coerce_reset_timestamp(info.get(key))
                if reset_at is not None:
                    wait = _wait_from_reset_timestamp(reset_at, now=now)
                    if wait is not None:
                        return wait
        for key in _RESETS_AT_KEYS:
            reset_at = _coerce_reset_timestamp(obj.get(key))
            if reset_at is not None:
                wait = _wait_from_reset_timestamp(reset_at, now=now)
                if wait is not None:
                    return wait
        for key in _RETRY_AFTER_KEYS:
            wait = _wait_from_retry_after(obj.get(key))
            if wait is not None:
                return wait
        for value in obj.values():
            found = _scan_json_obj(value, now=now)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _scan_json_obj(item, now=now)
            if found is not None:
                return found
    return None


def _scan_text(text: str, *, now: float) -> int | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            found = _scan_json_obj(payload, now=now)
            if found is not None:
                return found
        wait = _wait_from_retry_after(stripped)
        if wait is not None:
            return wait
    return None


def extract_rate_limit_wait_seconds(*sources: Path | str | None) -> int | None:
    """Best-effort wait duration until a provider limit resets.

    Returns seconds to wait, ``0`` when reset is already past, or ``None``
    when no reliable reset time was found.
    """
    now = time.time()
    for source in sources:
        if source is None:
            continue
        text = source.read_text() if isinstance(source, Path) else str(source)
        if not text.strip():
            continue
        found = _scan_text(text, now=now)
        if found is not None:
            return found
    return None


def _apply_jitter(seconds: int, *, jitter_seconds: int = _RATE_LIMIT_JITTER_SECONDS) -> int:
    if seconds <= 0:
        return 0
    return seconds + random.randint(0, min(jitter_seconds, max(1, seconds // 10 + 1)))


def _format_reset_time(seconds_from_now: int) -> str:
    target = datetime.fromtimestamp(time.time() + seconds_from_now, tz=timezone.utc)
    return target.isoformat()


def wait_for_rate_limit_reset(
    *,
    log_tag: str,
    policy: RateLimitWaitPolicy,
    wait_seconds: int | None,
    attempt: int,
) -> tuple[bool, int]:
    """Sleep until retry is allowed. Returns ``(should_retry, slept_seconds)``."""
    if policy.cap_seconds <= 0:
        print_line(f"[{log_tag}] rate limit hit; cap is 0s — not waiting")
        return False, 0

    if wait_seconds is not None:
        sleep_for = min(_apply_jitter(wait_seconds), policy.cap_seconds)
        reason = f"provider reset in ~{wait_seconds}s"
    else:
        sleep_for = min(
            policy.backoff_initial_seconds * (2 ** max(0, attempt - 1)),
            policy.backoff_max_seconds,
            policy.cap_seconds,
        )
        reason = f"unknown reset; backoff attempt {attempt}"

    if sleep_for <= 0:
        return True, 0

    poll_cap = min(policy.poll_interval_seconds, policy.cap_seconds)
    sleep_chunk = min(sleep_for, poll_cap)
    provider_reset_hint = (
        f"provider reset in ~{wait_seconds}s" if wait_seconds is not None else reason
    )
    print_line(
        f"[{log_tag}] rate limit reached — sleeping {sleep_chunk}s then retry "
        f"({provider_reset_hint}); poll every {policy.poll_interval_seconds}s; "
        f"retry ETA ~{_format_reset_time(sleep_chunk)}; cap={policy.cap_seconds}s"
    )
    time.sleep(sleep_chunk)
    return True, sleep_chunk


def run_with_rate_limit_retry(
    *,
    log_tag: str,
    policy: RateLimitWaitPolicy,
    run_once: Callable[[], dict[str, Any]],
    capture_paths: Callable[[dict[str, Any]], list[Path | None]],
) -> dict[str, Any]:
    """Run ``run_once`` until success or the wait cap is exhausted."""
    total_waited = 0
    attempt = 0
    last_payload: dict[str, Any] | None = None

    while True:
        attempt += 1
        payload = run_once()
        last_payload = payload
        if not payload_hit_usage_limit(payload):
            return payload

        remaining_cap = policy.cap_seconds - total_waited
        if remaining_cap <= 0:
            break

        paths = [p for p in capture_paths(payload) if p is not None]
        wait_seconds = extract_rate_limit_wait_seconds(*paths)
        if wait_seconds is not None:
            wait_seconds = min(wait_seconds, remaining_cap)

        limited_policy = RateLimitWaitPolicy(
            cap_seconds=remaining_cap,
            backoff_initial_seconds=min(policy.backoff_initial_seconds, remaining_cap),
            backoff_max_seconds=min(policy.backoff_max_seconds, remaining_cap),
            poll_interval_seconds=min(policy.poll_interval_seconds, remaining_cap),
        )
        should_retry, slept = wait_for_rate_limit_reset(
            log_tag=log_tag,
            policy=limited_policy,
            wait_seconds=wait_seconds,
            attempt=attempt,
        )
        total_waited += slept
        if not should_retry or total_waited >= policy.cap_seconds:
            break

    assert last_payload is not None
    last_payload = dict(last_payload)
    last_payload["status"] = USAGE_LIMIT_REACHED
    last_payload["stall_reason"] = (
        f"{USAGE_LIMIT_REACHED}: wait cap of {policy.cap_seconds}s exhausted "
        f"after {attempt} attempt(s)"
    )
    last_payload["rate_limit_wait_exhausted"] = True
    last_payload["rate_limit_total_wait_seconds"] = total_waited
    return last_payload
