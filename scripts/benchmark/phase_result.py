"""Shared phase result builder for opencode and codex harnesses."""

from __future__ import annotations

from typing import Any

from benchmark.run_status import derive_run_status
from benchmark.util import prompt_sha256


def derive_phase_status(
    *,
    timed_out: bool,
    stalled: bool,
    stall_reason: str | None = None,
    finish_reason: str | None,
    exit_code: int | None,
    works_as_intended: str,
) -> str:
    """Return the canonical status string for a completed benchmark phase.

    Priority: usage-limit stall > timeout > other stalled > terminal-stop > exit-code.

    >>> derive_phase_status(timed_out=False, stalled=False,
    ...     finish_reason="stop", exit_code=0, works_as_intended="yes")
    'completed'
    """
    return derive_run_status(
        timed_out=timed_out,
        stalled=stalled,
        stall_reason=stall_reason,
        finish_reason=finish_reason,
        exit_code=exit_code,
        works_as_intended=works_as_intended,
    )


def sum_phase_tokens(phases: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum token counters across benchmark phases for top-level ``result.json``."""
    total_input = 0
    total_output = 0
    total_reasoning = 0
    cache_read = 0
    cache_write = 0
    saw_tokens = False
    for phase in phases:
        tokens = phase.get("tokens")
        if not isinstance(tokens, dict) or not tokens:
            continue
        saw_tokens = True
        total_input += int(tokens.get("input") or 0)
        total_output += int(tokens.get("output") or 0)
        total_reasoning += int(tokens.get("reasoning") or 0)
        cache = tokens.get("cache")
        if isinstance(cache, dict):
            cache_read += int(cache.get("read") or 0)
            cache_write += int(cache.get("write") or 0)
    if not saw_tokens:
        return {}
    return {
        "input": total_input,
        "output": total_output,
        "reasoning": total_reasoning,
        "total": total_input + total_output,
        "cache": {"read": cache_read, "write": cache_write},
    }


def build_phase_payload(
    *,
    phase_name: str,
    assistant_output: str,
    command: list[str],
    continued_from_session: str | None,
    elapsed_seconds: float,
    ended_at: str,
    exit_code: int | None,
    finish_reason: str | None,
    model: dict[str, Any],
    session_id: str | None,
    paths: dict[str, Any],
    project_summary: dict[str, Any],
    prompt: str,
    started_at: str,
    stderr: str,
    stalled: bool,
    stall_reason: str | None,
    timed_out: bool,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    tokens: dict[str, Any],
    harness_metrics: dict[str, Any] | None = None,
    elapsed_field: str = "elapsed_seconds",
) -> dict[str, Any]:
    """Assemble the result payload dict for one benchmark phase.

    ``harness_metrics`` is a harness-neutral bag whose keys splat into the
    payload alongside core fields; harnesses that don't emit a metric (e.g.
    Claude has no preview TPS) simply omit that key.

    >>> payload = build_phase_payload(phase_name="phase1", assistant_output="",
    ...     command=[], continued_from_session=None, elapsed_seconds=1.0,
    ...     ended_at="t", exit_code=0, finish_reason="stop", model={},
    ...     session_id=None, paths={}, project_summary={"works_as_intended": "yes"},
    ...     prompt="", started_at="t", stderr="", stalled=False, stall_reason=None,
    ...     timed_out=False, timeout_seconds=60, no_progress_timeout_seconds=30,
    ...     tokens={"input": 0, "output": 0, "total": 0})
    >>> payload["status"]
    'completed'
    """
    works_as_intended = project_summary.get("works_as_intended", "no")
    status = derive_phase_status(
        timed_out=timed_out,
        stalled=stalled,
        stall_reason=stall_reason,
        finish_reason=finish_reason,
        exit_code=exit_code,
        works_as_intended=works_as_intended,
    )

    total_tokens = tokens.get("total")
    output_tokens = tokens.get("output")

    payload: dict[str, Any] = {
        "phase": phase_name,
        "assistant_output_excerpt": assistant_output[:4000],
        "command": command,
        "continued_from_session": continued_from_session,
        elapsed_field: elapsed_seconds,
        "ended_at": ended_at,
        "exit_code": exit_code,
        "finish_reason": finish_reason,
        "model": model,
        "opencode_session_id": session_id,
        "paths": paths,
        "project_summary": project_summary,
        "prompt_sha256": prompt_sha256(prompt),
        "started_at": started_at,
        "status": status,
        "stderr_excerpt": stderr[:4000],
        "stalled": stalled,
        "stall_reason": stall_reason,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "no_progress_timeout_seconds": no_progress_timeout_seconds,
        "tokens": tokens,
        "tokens_per_second": round(total_tokens / elapsed_seconds, 2)
        if total_tokens and elapsed_seconds
        else None,
        "output_tokens_per_second": round(output_tokens / elapsed_seconds, 2)
        if output_tokens and elapsed_seconds
        else None,
    }
    if harness_metrics:
        payload.update(harness_metrics)
    return payload
