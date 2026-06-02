"""Runner for Cursor Agent CLI headless benchmark (agent -p --output-format stream-json)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.agent_runtime_env import runtime_isolation_for_env
from benchmark.cli_stream import CliStreamAdapter, EventDecision, run_cli_stream_loop
from benchmark.pricing import merge_cursor_model_usage, model_usage_from_cursor_final
from benchmark.harnesses.stall_policy import ERROR_LOOP_THRESHOLD
from benchmark.rate_limit import (
    RateLimitWaitPolicy,
    stream_event_looks_rate_limited,
    text_looks_rate_limited,
)
from benchmark.timeouts import (
    DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from benchmark.config import _resolve_model_num_runs
from benchmark.replicates import resolve_result_dir
from benchmark.run_status import derive_cli_stream_status
from benchmark.target_lifecycle import (
    PhaseRunRequest,
    TargetRunLifecycle,
    TargetRunPaths,
)
from benchmark.util import (
    USAGE_LIMIT_REACHED,
    contains_usage_limit,
    count_files,
    print_line,
    prompt_sha256,
    resolve_harness_cli_versions,
    shorten_text,
    stream_log_prefix,
    utc_now,
)


@dataclass
class CursorStreamResult:
    stdout: str
    stderr: str
    timed_out: bool
    stalled: bool
    stall_reason: str | None
    usage_limit_reached: bool = False
    final_result_event: dict[str, Any] | None = None
    tool_use_counts: Counter = field(default_factory=Counter)
    assistant_turns: int = 0


def build_command(
    model: str,
    prompt: str,
    command_prefix: list[str] | None = None,
    *,
    continue_session: bool = False,
) -> list[str]:
    """Build the Cursor Agent CLI command for print mode."""
    prefix = command_prefix if command_prefix else ["agent"]
    args = [
        "--model",
        model,
        "-p",
        "--output-format",
        "stream-json",
        "--force",
        "--trust",
    ]
    if continue_session:
        args.append("--continue")
    args.append(prompt)
    return [*prefix, *args]


def _tool_call_label(tool_call: dict[str, Any]) -> str:
    for key in ("writeToolCall", "readToolCall", "shellToolCall", "grepToolCall"):
        if key in tool_call:
            inner = tool_call[key]
            args = inner.get("args") or {}
            if key == "writeToolCall":
                return f"write {args.get('path', '?')}"
            if key == "readToolCall":
                return f"read {args.get('path', '?')}"
            if key == "shellToolCall":
                return f"shell {shorten_text(str(args.get('command', '')), 80)}"
            return key.replace("ToolCall", "")
    fn = tool_call.get("function")
    if isinstance(fn, dict):
        return str(fn.get("name", "tool"))
    return "tool"


def _describe_event(event: dict[str, Any]) -> str | None:
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        return f"session init model={event.get('model', '-')}"
    if etype == "assistant":
        msg = event.get("message", {})
        content = msg.get("content", [])
        for part in content:
            if part.get("type") == "text":
                text = part.get("text", "")
                if text.strip():
                    return f"assistant: {shorten_text(text)}"
        return "assistant"
    if etype == "tool_call":
        sub = event.get("subtype", "")
        tc = event.get("tool_call") or {}
        label = _tool_call_label(tc)
        return f"tool_call {sub}: {label}"
    if etype == "result":
        return (
            f"result: {event.get('subtype', '?')} "
            f"duration_ms={event.get('duration_ms', 0)}"
        )
    return None


def _result_indicates_success(event: dict[str, Any] | None) -> bool:
    if not event or event.get("type") != "result":
        return False
    if event.get("is_error"):
        return False
    subtype = event.get("subtype")
    return subtype in ("success", None)


class _CursorCliAdapter(CliStreamAdapter[CursorStreamResult]):
    """Event parser + result builder for the Cursor Agent CLI stream-json format."""

    _error_loop_threshold = ERROR_LOOP_THRESHOLD

    def __init__(self, model_slug: str) -> None:
        self.model_slug = model_slug
        self._assistant_turns = 0
        self._tool_use_counts: Counter = Counter()
        self._final_result_event: dict[str, Any] | None = None
        self._consecutive_error_events = 0

    def on_event(self, event: dict[str, Any], now: float) -> EventDecision:
        etype = event.get("type")
        if etype == "assistant":
            self._assistant_turns += 1
        if etype == "tool_call":
            tc = event.get("tool_call") or {}
            self._tool_use_counts[_tool_call_label(tc)] += 1

        is_terminal = False
        if etype == "result":
            self._final_result_event = event
            is_terminal = True

        description = _describe_event(event)

        if stream_event_looks_rate_limited(event):
            return EventDecision(
                description=description,
                is_terminal=is_terminal,
                mark_activity=False,
                abort_reason=USAGE_LIMIT_REACHED,
            )

        is_error = bool(event.get("is_error")) or (
            etype == "result" and event.get("subtype") not in ("success", None)
        )
        if is_error:
            if contains_usage_limit(json.dumps(event)) or text_looks_rate_limited(
                json.dumps(event)
            ):
                return EventDecision(
                    description=description,
                    is_terminal=is_terminal,
                    mark_activity=False,
                    abort_reason=USAGE_LIMIT_REACHED,
                )
            self._consecutive_error_events += 1
            if self._consecutive_error_events >= self._error_loop_threshold:
                return EventDecision(
                    description=description,
                    is_terminal=is_terminal,
                    mark_activity=False,
                    abort_reason=(
                        f"{self._consecutive_error_events} consecutive errors"
                    ),
                )
            return EventDecision(
                description=description,
                is_terminal=is_terminal,
                mark_activity=False,
            )

        if etype == "user":
            # Cursor emits user-role tool results — don't reset the error
            # counter and don't count as activity (matches pre-refactor behavior).
            return EventDecision(
                description=description,
                is_terminal=is_terminal,
                mark_activity=False,
            )

        self._consecutive_error_events = 0
        return EventDecision(description=description, is_terminal=is_terminal)

    def heartbeat_detail(self) -> str:
        return f"turns={self._assistant_turns}"

    def build_result(
        self,
        *,
        stdout: str,
        stderr: str,
        timed_out: bool,
        stalled: bool,
        stall_reason: str | None,
    ) -> CursorStreamResult:
        return CursorStreamResult(
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
            usage_limit_reached=(stall_reason == USAGE_LIMIT_REACHED),
            final_result_event=self._final_result_event,
            tool_use_counts=self._tool_use_counts,
            assistant_turns=self._assistant_turns,
        )


def stream_process(
    process: subprocess.Popen[str],
    stdout_path: Path,
    stderr_path: Path,
    project_dir: Path,
    model_slug: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
) -> CursorStreamResult:
    return run_cli_stream_loop(
        process,
        _CursorCliAdapter(model_slug),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=project_dir,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )


def _phase_status(
    stream_result: CursorStreamResult,
    final: dict[str, Any],
) -> str:
    usage_limited = stream_result.usage_limit_reached or (
        bool(final.get("is_error"))
        and (
            contains_usage_limit(json.dumps(final))
            or text_looks_rate_limited(json.dumps(final))
        )
    )
    return derive_cli_stream_status(
        usage_limited=usage_limited,
        timed_out=stream_result.timed_out,
        stalled=stream_result.stalled,
        final_is_error=bool(final.get("is_error")),
        final_indicates_success=_result_indicates_success(final),
        has_final_event=bool(final),
    )


def _run_cursor_phase(
    *,
    variant: dict[str, Any],
    prompt: str,
    project_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
    command_prefix: list[str] | None,
    harness: str,
    slug: str,
    phase_name: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    continue_session: bool = False,
    env: dict[str, str] | None = None,
) -> tuple[CursorStreamResult, subprocess.Popen[str], float]:
    command = build_command(
        variant["main_model"],
        prompt,
        command_prefix,
        continue_session=continue_session,
    )
    wall_start = time.monotonic()
    process_env = env if env is not None else os.environ.copy()
    process = subprocess.Popen(
        command,
        cwd=project_dir.resolve(),
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        bufsize=1,
    )
    result = stream_process(
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=project_dir,
        model_slug=stream_log_prefix(harness, slug, phase_name),
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )
    return result, process, round(time.monotonic() - wall_start, 2)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_counts(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    merged = dict(first)
    for key, value in second.items():
        merged[key] = merged.get(key, 0) + value
    return merged


def _run_cursor_lifecycle_phase(
    *,
    request: PhaseRunRequest,
    variant: dict[str, Any],
    command_prefix: list[str] | None,
    harness: str,
    slug: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    request.prompt_path.write_text(request.prompt)
    result, process, elapsed = _run_cursor_phase(
        variant=variant,
        prompt=request.prompt,
        project_dir=request.project_dir,
        stdout_path=request.stdout_path,
        stderr_path=request.stderr_path,
        command_prefix=command_prefix,
        harness=harness,
        slug=slug,
        phase_name=request.phase_name,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
        continue_session=False,
        env=env,
    )
    return _cursor_phase_payload(
        request=request,
        variant=variant,
        result=result,
        process=process,
        elapsed=elapsed,
        command_prefix=command_prefix,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )


def _cursor_phase_payload(
    *,
    request: PhaseRunRequest,
    variant: dict[str, Any],
    result: CursorStreamResult,
    process: subprocess.Popen[str],
    elapsed: float,
    command_prefix: list[str] | None,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
) -> dict[str, Any]:
    final = result.final_result_event or {}
    usage = _dict_or_empty(final.get("usage"))
    model_usage = model_usage_from_cursor_final(variant["main_model"], final)
    status = _phase_status(result, final)
    command = build_command(
        variant["main_model"],
        request.prompt,
        command_prefix,
        continue_session=False,
    )
    return {
        "phase": request.phase_name,
        "status": status,
        "started_at": request.started_at,
        "ended_at": utc_now(),
        "elapsed_seconds": elapsed,
        "timed_out": result.timed_out,
        "stalled": result.stalled,
        "stall_reason": result.stall_reason,
        "timeout_seconds": timeout_seconds,
        "no_progress_timeout_seconds": no_progress_timeout_seconds,
        "exit_code": process.returncode,
        "file_count": count_files(request.project_dir),
        "num_turns": result.assistant_turns,
        "assistant_turns": result.assistant_turns,
        "result_subtype": final.get("subtype"),
        "duration_ms": final.get("duration_ms"),
        "usage_total": usage,
        "model_usage": model_usage,
        "tool_use_counts": dict(result.tool_use_counts),
        "prompt_sha256": prompt_sha256(request.prompt),
        "command": command[:-1] + ["<prompt>"],
        "paths": {
            "stream_ndjson": str(request.stdout_path),
            "stderr_log": str(request.stderr_path),
        },
    }


def _cursor_phase_record(phase: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "phase",
        "status",
        "elapsed_seconds",
        "num_turns",
        "file_count",
        "model_usage",
    )
    return {key: phase[key] for key in keys if key in phase}


def _finalize_cursor_payload(
    *,
    payload: dict[str, Any],
    phases: list[dict[str, Any]],
    variant: dict[str, Any],
    prompt: str,
    followup_prompt: str | None,
    cli_version_fields: dict[str, Any],
) -> dict[str, Any]:
    phase1 = phases[0]
    payload.update(
        {
            "slug": variant["slug"],
            "label": variant.get("label"),
            "main_model": variant["main_model"],
            "prompt_sha256": prompt_sha256(prompt),
            "command": phase1.get("command", []),
            "phases": [_cursor_phase_record(phase) for phase in phases],
            **cli_version_fields,
        }
    )
    if len(phases) > 1:
        _merge_cursor_followup_payload(payload, phase1, phases[-1], followup_prompt)
    return payload


def _merge_cursor_followup_payload(
    payload: dict[str, Any],
    phase1: dict[str, Any],
    phase2: dict[str, Any],
    followup_prompt: str | None,
) -> None:
    assert followup_prompt is not None
    payload.update(
        {
            "started_at": phase1["started_at"],
            "num_turns": phase1["num_turns"] + phase2["num_turns"],
            "assistant_turns": phase1["assistant_turns"] + phase2["assistant_turns"],
            "model_usage": merge_cursor_model_usage(
                phase1["model_usage"], phase2["model_usage"]
            ),
            "tool_use_counts": _merge_counts(
                phase1["tool_use_counts"], phase2["tool_use_counts"]
            ),
            "followup_prompt_sha256": prompt_sha256(followup_prompt),
        }
    )


def _print_cursor_start(
    *,
    slug: str,
    variant: dict[str, Any],
    result_dir: Path,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    log_tag: str,
) -> None:
    print_line("")
    print_line(f"Starting {slug} -> {variant['main_model']} (Cursor CLI)")
    print_line(f"[{log_tag}] results_dir={result_dir}")
    print_line(
        f"[{log_tag}] timeout={timeout_seconds}s "
        f"no_progress_timeout={no_progress_timeout_seconds}s"
    )


def _print_cursor_completion(
    payload: dict[str, Any],
    slug: str,
    log_tag: str,
) -> None:
    model_usage = _dict_or_empty(payload.get("model_usage"))
    print_line(
        f"Finished {slug} status={payload['status']} "
        f"elapsed={float(payload['elapsed_seconds']):.2f}s "
        f"files={payload['file_count']} turns={payload['num_turns']}"
    )
    if model_usage:
        _print_model_usage(log_tag, model_usage)


def _print_model_usage(log_tag: str, model_usage: dict[str, Any]) -> None:
    print_line(f"[{log_tag}] model_usage:")
    for model, usage in model_usage.items():
        in_tok = usage.get("inputTokens", 0)
        out_tok = usage.get("outputTokens", 0)
        cache_read = usage.get("cacheReadInputTokens", 0)
        print_line(f"  {model}: in={in_tok} out={out_tok} cache_read={cache_read}")


def run_variant(
    *,
    variant: dict[str, Any],
    prompt: str,
    results_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    no_progress_timeout_seconds: int = DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    force: bool = False,
    runner_command_prefix: list[str] | None = None,
    harness: str = "cursor",
    explicit_result_dir: Path | None = None,
    followup_prompt: str | None = None,
    rate_limit_policy: RateLimitWaitPolicy | None = None,
    replicate_index: int = 1,
    num_runs: int | None = None,
    include_agent_rules: bool = True,
    for_benchmark_build: bool = False,
    wrap_primary_prompt: bool = True,
) -> dict[str, Any]:
    """Run a single Cursor CLI benchmark variant."""
    slug = variant["slug"]
    log_tag = stream_log_prefix(harness, slug)
    result_dir = resolve_result_dir(
        results_dir=results_dir,
        harness=harness,
        slug=slug,
        replicate_index=replicate_index,
        explicit_result_dir=explicit_result_dir,
    )
    paths = TargetRunPaths.cli(result_dir)
    command_prefix = variant.get("command_prefix") or runner_command_prefix
    effective_num_runs = (
        num_runs if num_runs is not None else _resolve_model_num_runs(variant)
    )
    cli_version_fields_cache: dict[str, Any] | None = None
    env_cache: dict[str, str] | None = None
    runtime_isolation: dict[str, str] = {}

    def get_env() -> dict[str, str]:
        nonlocal env_cache
        if env_cache is None:
            env_cache = os.environ.copy()
            runtime_isolation.clear()
            runtime_isolation.update(runtime_isolation_for_env(env_cache))
        return env_cache

    def get_cli_version_fields() -> dict[str, Any]:
        nonlocal cli_version_fields_cache
        if cli_version_fields_cache is None:
            cli_version_fields_cache = resolve_harness_cli_versions(
                harness=harness,
                command_prefix=command_prefix,
            )
        return cli_version_fields_cache

    def before_phases() -> dict[str, Any] | None:
        _print_cursor_start(
            slug=slug,
            variant=variant,
            result_dir=result_dir,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            log_tag=log_tag,
        )
        if for_benchmark_build:
            get_env()
        return None

    def run_phase(request: PhaseRunRequest) -> dict[str, Any]:
        phase_env = get_env()
        return _run_cursor_lifecycle_phase(
            request=request,
            variant=variant,
            command_prefix=command_prefix,
            harness=harness,
            slug=slug,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            env=phase_env,
        )

    def finalize_payload(
        payload: dict[str, Any],
        phases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _finalize_cursor_payload(
            payload=payload,
            phases=phases,
            variant=variant,
            prompt=prompt,
            followup_prompt=followup_prompt,
            cli_version_fields=get_cli_version_fields(),
        )

    return TargetRunLifecycle(
        harness=harness,
        slug=slug,
        results_dir=results_dir,
        paths=paths,
        force=force,
        prompt=prompt,
        followup_prompt=followup_prompt,
        run_phase=run_phase,
        rate_limit_policy=rate_limit_policy or RateLimitWaitPolicy(),
        before_phases=before_phases,
        final_payload_hook=finalize_payload,
        after_save=lambda payload: _print_cursor_completion(
            payload, slug=slug, log_tag=log_tag
        ),
        phase_log_tag=lambda phase_name: stream_log_prefix(harness, slug, phase_name),
        replicate_index=replicate_index,
        num_runs=effective_num_runs,
        include_agent_rules=include_agent_rules,
        wrap_primary_prompt=wrap_primary_prompt,
        extra_payload_fields={"runtime_isolation": runtime_isolation},
    ).run()
