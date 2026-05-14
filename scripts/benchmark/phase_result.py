"""Shared phase result builder for opencode and codex harnesses."""

from __future__ import annotations

from typing import Any

from benchmark.util import prompt_sha256


def derive_phase_status(
    *,
    timed_out: bool,
    stalled: bool,
    finish_reason: str | None,
    exit_code: int | None,
    works_as_intended: str,
) -> str:
    """Return the canonical status string for a completed benchmark phase.

    Priority: timeout > stalled > terminal-stop outcome > exit-code outcome.

    >>> derive_phase_status(timed_out=False, stalled=False,
    ...     finish_reason="stop", exit_code=0, works_as_intended="yes")
    'completed'
    """
    if timed_out:
        return "timeout"
    if stalled:
        return "failed"
    if finish_reason == "stop":
        return "completed" if works_as_intended == "yes" else "completed_with_errors"
    if exit_code == 0:
        return "completed" if works_as_intended == "yes" else "completed_with_errors"
    return "failed"


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
    latest_preview_output_tps: float | None,
    preview_average_output_tps: float | None,
) -> dict[str, Any]:
    """Assemble the result payload dict for one benchmark phase.

    >>> payload = build_phase_payload(phase_name="phase1", assistant_output="",
    ...     command=[], continued_from_session=None, elapsed_seconds=1.0,
    ...     ended_at="t", exit_code=0, finish_reason="stop", model={},
    ...     session_id=None, paths={}, project_summary={"works_as_intended": "yes"},
    ...     prompt="", started_at="t", stderr="", stalled=False, stall_reason=None,
    ...     timed_out=False, timeout_seconds=60, no_progress_timeout_seconds=30,
    ...     tokens={"input": 0, "output": 0, "total": 0},
    ...     latest_preview_output_tps=None, preview_average_output_tps=None)
    >>> payload["status"]
    'completed'
    """
    works_as_intended = project_summary.get("works_as_intended", "no")
    status = derive_phase_status(
        timed_out=timed_out,
        stalled=stalled,
        finish_reason=finish_reason,
        exit_code=exit_code,
        works_as_intended=works_as_intended,
    )

    total_tokens = tokens.get("total")
    output_tokens = tokens.get("output")

    return {
        "phase": phase_name,
        "assistant_output_excerpt": assistant_output[:4000],
        "command": command,
        "continued_from_session": continued_from_session,
        "elapsed_seconds": elapsed_seconds,
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
        "preview_output_tokens_per_second": latest_preview_output_tps,
        "preview_output_tokens_per_second_average": preview_average_output_tps,
        "tokens_per_second": round(total_tokens / elapsed_seconds, 2)
        if total_tokens and elapsed_seconds
        else None,
        "output_tokens_per_second": round(output_tokens / elapsed_seconds, 2)
        if output_tokens and elapsed_seconds
        else None,
    }
