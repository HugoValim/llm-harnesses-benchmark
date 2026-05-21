"""Stream event parsing state machine for the benchmark runner.

Owns all mutable parsing state and returns explicit StreamAction values so
the IO loop in stream_process_output() can act without containing any
decision logic.

Usage example::

    state = EventStreamState(
        model_slug="my-model",
        min_preview_output_tps=10.0,
        min_preview_samples=3,
    )
    action = state.process_event(event)
    if action.kind == ActionKind.STALL:
        kill_process_group(proc)
        return make_result(stall_reason=action.reason)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from benchmark.util import USAGE_LIMIT_REACHED, contains_usage_limit


class ToolCallLoopDetector:
    """Detects repetitive tool calls using SHA256 hashing.

    Generates a unique key from tool_name + serialized args and tracks
    consecutive identical calls. When the count reaches *threshold*,
    the call is considered a loop.
    """

    def __init__(self, threshold: int = 5) -> None:
        self.threshold = threshold
        self._last_key: str | None = None
        self._consecutive_count = 0
        self._total_calls = 0
        self._history: list[tuple[str, str, dict[str, Any]]] = []

    def record(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Record a tool call and return True if a loop is detected."""
        self._total_calls += 1
        key = self._make_key(tool_name, args)

        if key == self._last_key:
            self._consecutive_count += 1
        else:
            self._last_key = key
            self._consecutive_count = 1

        self._history.append((tool_name, key, args))
        return self._consecutive_count >= self.threshold

    @property
    def last_key(self) -> str | None:
        return self._last_key

    @property
    def consecutive_count(self) -> int:
        return self._consecutive_count

    @property
    def total_calls(self) -> int:
        return self._total_calls

    def loop_description(self, tool_name: str) -> str:
        return (
            f"tool-call loop: '{tool_name}' called {self._consecutive_count} times "
            f"consecutively with the same arguments"
        )

    @staticmethod
    def _make_key(tool_name: str, args: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class ActionKind(Enum):
    CONTINUE = "continue"
    STALL = "stall"
    GRACEFUL_STOP = "graceful_stop"
    TPS_GATE_FAIL = "tps_gate_fail"


@dataclass
class StreamAction:
    kind: ActionKind
    reason: str | None = None


def _extract_error_detail(event: dict[str, Any]) -> str:
    """Pull a human-readable error string from various event shapes."""
    detail = (
        event.get("part", {}).get("error")
        or event.get("part", {}).get("message")
        or event.get("error")
        or event.get("message")
        or "unknown"
    )
    if isinstance(detail, dict):
        detail = detail.get("message", str(detail))
    return str(detail)


def _shorten(text: str, max_len: int = 120) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


class EventStreamState:
    """Parses NDJSON events from opencode/codex and returns StreamAction decisions.

    The IO loop retains ownership of select/readline/file-writes/kill.
    This class owns all mutable parsing state so decisions are unit-testable
    without a real subprocess.
    """

    def __init__(
        self,
        *,
        model_slug: str,
        min_preview_output_tps: float | None,
        min_preview_samples: int,
        error_loop_threshold: int = 5,
        tool_loop_threshold: int = 5,
    ) -> None:
        self._model_slug = model_slug
        self._min_preview_output_tps = min_preview_output_tps
        self._min_preview_samples = min_preview_samples
        self._error_loop_threshold = error_loop_threshold

        # Error loop state
        self._consecutive_error_events = 0
        self._last_is_error = False

        # Terminal stop state
        self._terminal_stop_seen_at: float | None = None

        # TPS tracking
        self._current_step_started_at: int | None = None
        self._latest_preview_output_tps: float | None = None
        self._preview_average_output_tps: float | None = None
        self._preview_output_tps_samples: list[float] = []
        self._preview_gate_decided = False

        # Tool-call / command loop detection
        self._tool_call_loop_detector = ToolCallLoopDetector(threshold=tool_loop_threshold)

        # Session continuity
        self._session_id: str | None = None

        # Last human-readable event description
        self._last_description: str | None = None

    # ── public API ──────────────────────────────────────────────────────────

    def process_event(self, event: dict[str, Any]) -> StreamAction:
        """Parse one NDJSON event and return what the IO loop should do next."""
        is_error = self._classify_error(event)
        self._last_is_error = is_error

        if is_error:
            return self._handle_error_event(event)

        # Non-error path — reset consecutive counter
        self._consecutive_error_events = 0

        # Extract session ID (first one wins)
        self._session_id = self._session_id or event.get("sessionID")

        event_type = event.get("type", "")

        if event_type == "step_start":
            self._terminal_stop_seen_at = None
            timestamp = event.get("timestamp")
            if isinstance(timestamp, int):
                self._current_step_started_at = timestamp

        elif event_type == "step_finish":
            action = self._handle_step_finish(event)
            if action.kind != ActionKind.CONTINUE:
                return action

        elif event_type == "turn.completed":
            # Codex terminal stop equivalent
            import time as _time
            self._terminal_stop_seen_at = _time.monotonic()

        elif event_type == "tool_use":
            action = self._handle_tool_use(event)
            if action.kind != ActionKind.CONTINUE:
                return action

        elif event_type == "item.completed":
            action = self._handle_item_completed(event)
            if action.kind != ActionKind.CONTINUE:
                return action

        # Update description for heartbeat logging
        description = self._describe(event)
        if description:
            self._last_description = description

        return StreamAction(kind=ActionKind.CONTINUE)

    def check_terminal_grace(self, now: float, grace_seconds: float) -> StreamAction:
        """Return GRACEFUL_STOP if terminal stop was seen and grace has elapsed."""
        if self._terminal_stop_seen_at is None:
            return StreamAction(kind=ActionKind.CONTINUE)
        if now - self._terminal_stop_seen_at >= grace_seconds:
            return StreamAction(kind=ActionKind.GRACEFUL_STOP)
        return StreamAction(kind=ActionKind.CONTINUE)

    def check_idle(
        self,
        idle_seconds: float,
        no_progress_timeout_seconds: int,
        last_activity_detail: str,
    ) -> StreamAction:
        """Return STALL if idle_seconds has reached the timeout threshold."""
        if idle_seconds >= no_progress_timeout_seconds:
            reason = (
                f"no progress for {_format_duration(idle_seconds)}; "
                f"last activity: {last_activity_detail}"
            )
            return StreamAction(kind=ActionKind.STALL, reason=reason)
        return StreamAction(kind=ActionKind.CONTINUE)

    # ── properties ──────────────────────────────────────────────────────────

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def latest_preview_output_tps(self) -> float | None:
        return self._latest_preview_output_tps

    @property
    def preview_average_output_tps(self) -> float | None:
        return self._preview_average_output_tps

    @property
    def last_description(self) -> str | None:
        return self._last_description

    @property
    def is_error_event(self) -> bool:
        """True if the last processed event was classified as an error."""
        return self._last_is_error

    @property
    def consecutive_error_events(self) -> int:
        return self._consecutive_error_events

    @property
    def tps_sample_count(self) -> int:
        return len(self._preview_output_tps_samples)

    # ── private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _classify_error(event: dict[str, Any]) -> bool:
        return (
            event.get("part", {}).get("type") == "error"
            or event.get("type") == "error"
            or event.get("type") == "turn.failed"
        )

    def _handle_error_event(self, event: dict[str, Any]) -> StreamAction:
        error_detail = _extract_error_detail(event)
        if contains_usage_limit(error_detail):
            self._last_description = f"error: {_shorten(error_detail)}"
            return StreamAction(kind=ActionKind.STALL, reason=USAGE_LIMIT_REACHED)

        self._consecutive_error_events += 1
        description = f"error: {_shorten(error_detail)}"
        self._last_description = description

        if self._consecutive_error_events >= self._error_loop_threshold:
            reason = (
                f"error loop: {self._consecutive_error_events} consecutive error events; "
                f"last error: {_shorten(error_detail, 200)}"
            )
            return StreamAction(kind=ActionKind.STALL, reason=reason)

        return StreamAction(kind=ActionKind.CONTINUE)

    def _handle_step_finish(self, event: dict[str, Any]) -> StreamAction:
        import time as _time

        part = event.get("part", {})
        reason = part.get("reason")
        if reason == "stop":
            self._terminal_stop_seen_at = _time.monotonic()

        timestamp = event.get("timestamp")
        output_tokens = part.get("tokens", {}).get("output")

        if (
            self._current_step_started_at is not None
            and isinstance(timestamp, int)
            and isinstance(output_tokens, int)
            and timestamp > self._current_step_started_at
        ):
            duration_seconds = (timestamp - self._current_step_started_at) / 1000
            self._latest_preview_output_tps = round(
                output_tokens / duration_seconds, 2
            )
            self._preview_output_tps_samples.append(self._latest_preview_output_tps)

            if (
                not self._preview_gate_decided
                and len(self._preview_output_tps_samples) >= self._min_preview_samples
            ):
                self._preview_gate_decided = True
                self._preview_average_output_tps = round(
                    sum(self._preview_output_tps_samples[: self._min_preview_samples])
                    / self._min_preview_samples,
                    2,
                )
                if (
                    self._min_preview_output_tps is not None
                    and self._preview_average_output_tps < self._min_preview_output_tps
                ):
                    reason = (
                        f"preview average output_tps {self._preview_average_output_tps:.2f} "
                        f"over first {self._min_preview_samples} steps "
                        f"below threshold {self._min_preview_output_tps:.2f}"
                    )
                    return StreamAction(kind=ActionKind.TPS_GATE_FAIL, reason=reason)

        return StreamAction(kind=ActionKind.CONTINUE)

    def _handle_tool_use(self, event: dict[str, Any]) -> StreamAction:
        part = event.get("part", {})
        tool_name = part.get("tool", "")
        tool_input = part.get("state", {}).get("input", {})
        if tool_name and self._tool_call_loop_detector.record(tool_name, tool_input):
            reason = self._tool_call_loop_detector.loop_description(tool_name)
            return StreamAction(kind=ActionKind.STALL, reason=reason)
        return StreamAction(kind=ActionKind.CONTINUE)

    def _handle_item_completed(self, event: dict[str, Any]) -> StreamAction:
        item = event.get("item", {})
        if item.get("type") == "command_execution":
            cmd = item.get("command", "")
            if cmd and self._tool_call_loop_detector.record(
                "command_execution", {"command": cmd}
            ):
                reason = self._tool_call_loop_detector.loop_description(
                    "command_execution"
                )
                return StreamAction(kind=ActionKind.STALL, reason=reason)
        return StreamAction(kind=ActionKind.CONTINUE)

    @staticmethod
    def _describe(event: dict[str, Any]) -> str | None:
        """Produce a short human-readable label for heartbeat logging."""
        event_type = event.get("type", "")
        if event_type == "step_start":
            return "step started"
        if event_type == "step_finish":
            reason = event.get("part", {}).get("reason", "")
            return f"step finished (reason={reason})"
        if event_type == "tool_use":
            tool = event.get("part", {}).get("tool", "")
            return f"tool_use: {tool}" if tool else "tool_use"
        if event_type == "item.completed":
            item_type = event.get("item", {}).get("type", "")
            return f"item.completed: {item_type}" if item_type else "item.completed"
        return None


def _format_duration(seconds: float) -> str:
    """Human-readable duration (mirrors runner.format_duration)."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m{secs:02d}s"
