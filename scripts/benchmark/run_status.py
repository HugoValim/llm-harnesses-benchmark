"""Canonical run status and retry predicates for benchmark results."""

from __future__ import annotations

from typing import Any

from benchmark.util import USAGE_LIMIT_REACHED, contains_usage_limit, text_has_http_429

STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_ERRORS = "completed_with_errors"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"

TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_ERRORS,
        STATUS_FAILED,
        STATUS_TIMEOUT,
        USAGE_LIMIT_REACHED,
    }
)

RETRYABLE_AUDIT_STATUSES = frozenset(
    {
        USAGE_LIMIT_REACHED,
        STATUS_TIMEOUT,
        STATUS_FAILED,
        "error",
        "stalled",
    }
)


def derive_run_status(
    *,
    timed_out: bool,
    stalled: bool,
    stall_reason: str | None,
    finish_reason: str | None,
    exit_code: int | None,
    works_as_intended: str | bool,
) -> str:
    """Return the canonical status for a benchmark phase or validated result.

    Example:
        ``derive_run_status(..., finish_reason="stop", exit_code=0, works_as_intended="yes")``
        returns ``"completed"``.
    """
    if stalled and stall_reason == USAGE_LIMIT_REACHED:
        return USAGE_LIMIT_REACHED
    if timed_out:
        return STATUS_TIMEOUT
    if stalled:
        return STATUS_FAILED
    works = works_as_intended is True or works_as_intended == "yes"
    if finish_reason == "stop":
        return _completed_status(works)
    if exit_code == 0:
        return _completed_status(works)
    return STATUS_FAILED


def derive_cli_stream_status(
    *,
    usage_limited: bool,
    timed_out: bool,
    stalled: bool,
    final_is_error: bool,
    final_indicates_success: bool,
    has_final_event: bool,
) -> str:
    """Return a canonical status for Claude/Cursor stream-json results."""
    if usage_limited:
        return USAGE_LIMIT_REACHED
    if timed_out:
        return STATUS_TIMEOUT
    if stalled or final_is_error:
        return STATUS_FAILED
    if final_indicates_success:
        return STATUS_COMPLETED
    if has_final_event:
        return STATUS_COMPLETED_WITH_ERRORS
    return STATUS_FAILED


def payload_phases(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return dict phases from a result payload."""
    if not payload:
        return []
    phases = payload.get("phases")
    if not isinstance(phases, list):
        return []
    return [phase for phase in phases if isinstance(phase, dict)]


def payload_hit_usage_limit(payload: dict[str, Any] | None) -> bool:
    """True when a result payload or any phase reports provider quota exhaustion."""
    if not payload:
        return False
    if status_hit_usage_limit(payload):
        return True
    if _payload_text_hit_usage_limit(payload):
        return True
    return any(status_hit_usage_limit(phase) for phase in payload_phases(payload))


def payload_was_stalled(payload: dict[str, Any] | None) -> bool:
    """True when a result payload or any phase reports a stall."""
    if not payload:
        return False
    if payload.get("stalled"):
        return True
    return any(bool(phase.get("stalled")) for phase in payload_phases(payload))


def status_hit_usage_limit(row: dict[str, Any]) -> bool:
    """True when one result/phase row reports a usage-limit status or stall."""
    if row.get("status") == USAGE_LIMIT_REACHED:
        return True
    return row.get("stall_reason") == USAGE_LIMIT_REACHED


def validation_retryable_status(payload: dict[str, Any] | None) -> bool:
    """False when a payload is quota-blocked and immediate retry will not help."""
    return not payload_hit_usage_limit(payload)


def audit_status_retryable(status: Any, *, incomplete_status: str) -> bool:
    """True when an audit status should trigger another auditor run."""
    retryable = RETRYABLE_AUDIT_STATUSES | {incomplete_status}
    return status in retryable


def _payload_text_hit_usage_limit(payload: dict[str, Any]) -> bool:
    for key in ("stderr_excerpt", "assistant_output_excerpt", "result"):
        value = payload.get(key)
        if isinstance(value, str) and _text_hit_usage_limit(value):
            return True
    return False


def _text_hit_usage_limit(text: str) -> bool:
    if contains_usage_limit(text):
        return True
    return text_has_http_429(text)


def _completed_status(works_as_intended: bool) -> str:
    if works_as_intended:
        return STATUS_COMPLETED
    return STATUS_COMPLETED_WITH_ERRORS
