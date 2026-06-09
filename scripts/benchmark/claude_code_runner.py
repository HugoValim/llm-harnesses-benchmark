"""Runner for Claude Code headless benchmark (claude -p --output-format stream-json)."""

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
class ClaudeCodeStreamResult:
    stdout: str
    stderr: str
    timed_out: bool
    stalled: bool
    stall_reason: str | None
    usage_limit_reached: bool = False
    final_result_event: dict[str, Any] | None = None
    tool_use_counts: Counter = field(default_factory=Counter)
    subagent_invocations: list[dict[str, Any]] = field(default_factory=list)
    assistant_turns: int = 0


def build_command(
    model: str, prompt: str, command_prefix: list[str] | None = None
) -> list[str]:
    """Build the claude -p command. Prompt is passed as positional arg.

    command_prefix replaces the default ["claude"] head — e.g. ["ollama", "launch", "claude"]
    for Ollama-served models invoked through the user's ollama-launch shim.

    The `ollama launch <integration>` shim has its own `--model` flag and forwards
    everything after `--` to the integration, so for that prefix we route the model
    through the shim and pass the remaining claude args after `--` (no `--model`
    on the claude side, since the shim configures it).
    """
    prefix = command_prefix if command_prefix else ["claude"]
    is_ollama_launch = (
        len(prefix) >= 2 and prefix[0] == "ollama" and prefix[1] == "launch"
    )
    claude_args = [
        "-p",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--verbose",
        prompt,
    ]
    if is_ollama_launch:
        return [*prefix, "--model", model, "--", *claude_args]
    return [*prefix, "--model", model, *claude_args]


def write_project_agent(project_dir: Path, subagent: dict[str, Any] | None) -> None:
    """Write the subagent definition into .claude/agents/ in the project directory."""
    if not subagent:
        return
    agents_dir = project_dir / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_name = subagent["name"]
    frontmatter_lines = [
        "---",
        f"name: {agent_name}",
        f"description: {subagent['description']}",
        f"model: {subagent['model']}",
        "---",
        "",
        subagent["prompt"].strip(),
        "",
    ]
    (agents_dir / f"{agent_name}.md").write_text("\n".join(frontmatter_lines))


def _describe_event(event: dict[str, Any]) -> str | None:
    etype = event.get("type")
    if etype == "system":
        sub = event.get("subtype", "")
        if sub == "init":
            return f"session init model={event.get('model', '-')} agents={event.get('agents', [])}"
        return f"system: {sub}"
    if etype == "assistant":
        msg = event.get("message", {})
        model = msg.get("model", "-")
        content = msg.get("content", [])
        for part in content:
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text", "")
                if text.strip():
                    return f"assistant({model}): {shorten_text(text)}"
            if ptype == "tool_use":
                name = part.get("name", "?")
                input_data = part.get("input", {})
                if name == "Task":
                    sub = input_data.get("subagent_type", "?")
                    desc = input_data.get("description", "")
                    return f"delegate to {sub}: {shorten_text(desc)}"
                if name in ("Write", "Edit"):
                    path = input_data.get("file_path", "?")
                    return f"{name} {path}"
                if name == "Bash":
                    cmd = input_data.get("command", "")
                    return f"Bash: {shorten_text(cmd, 80)}"
                return f"tool_use: {name}"
        return f"assistant({model})"
    if etype == "user":
        return None  # tool results — noisy
    if etype == "result":
        reason = event.get("stop_reason", "?")
        turns = event.get("num_turns", 0)
        return f"result: {reason} turns={turns}"
    return None


class _ClaudeCliAdapter(CliStreamAdapter[ClaudeCodeStreamResult]):
    """Event parser + result builder for the Claude Code stream-json format."""

    _error_loop_threshold = ERROR_LOOP_THRESHOLD

    def __init__(self, model_slug: str) -> None:
        self.model_slug = model_slug
        self._assistant_turns = 0
        self._tool_use_counts: Counter = Counter()
        self._subagent_invocations: list[dict[str, Any]] = []
        self._final_result_event: dict[str, Any] | None = None
        self._session_id: str | None = None
        self._consecutive_error_events = 0

    def on_event(self, event: dict[str, Any], now: float) -> EventDecision:
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            self._session_id = event.get("session_id")

        if etype == "assistant":
            self._assistant_turns += 1
            msg = event.get("message", {})
            model = msg.get("model", "?")
            for part in msg.get("content", []):
                if part.get("type") != "tool_use":
                    continue
                tool_name = part.get("name", "?")
                self._tool_use_counts[tool_name] += 1
                if tool_name == "Task":
                    tinput = part.get("input", {})
                    self._subagent_invocations.append(
                        {
                            "parent_model": model,
                            "subagent_type": tinput.get("subagent_type"),
                            "description": tinput.get("description", "")[:300],
                        }
                    )

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

        is_error = (etype == "result" and event.get("is_error")) or (
            etype == "system" and event.get("subtype") == "error"
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

        self._consecutive_error_events = 0
        return EventDecision(description=description, is_terminal=is_terminal)

    def heartbeat_detail(self) -> str:
        return (
            f"turns={self._assistant_turns} "
            f"delegations={len(self._subagent_invocations)} "
            f"session={self._session_id or '-'}"
        )

    def build_result(
        self,
        *,
        stdout: str,
        stderr: str,
        timed_out: bool,
        stalled: bool,
        stall_reason: str | None,
    ) -> ClaudeCodeStreamResult:
        return ClaudeCodeStreamResult(
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
            usage_limit_reached=(stall_reason == USAGE_LIMIT_REACHED),
            final_result_event=self._final_result_event,
            tool_use_counts=self._tool_use_counts,
            subagent_invocations=self._subagent_invocations,
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
) -> ClaudeCodeStreamResult:
    return run_cli_stream_loop(
        process,
        _ClaudeCliAdapter(model_slug),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=project_dir,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )


def _phase_status_from_stream(
    result: ClaudeCodeStreamResult,
    final: dict[str, Any],
) -> str:
    usage_limited = result.usage_limit_reached or (
        bool(final.get("is_error"))
        and (
            contains_usage_limit(json.dumps(final))
            or text_looks_rate_limited(json.dumps(final))
        )
    )
    if usage_limited:
        return derive_cli_stream_status(
            usage_limited=True,
            timed_out=result.timed_out,
            stalled=result.stalled,
            final_is_error=bool(final.get("is_error")),
            final_indicates_success=False,
            has_final_event=bool(final),
        )
    stop_reason = final.get("stop_reason")
    success = stop_reason in ("end_turn", "stop_sequence", None) and bool(final)
    return derive_cli_stream_status(
        usage_limited=False,
        timed_out=result.timed_out,
        stalled=result.stalled,
        final_is_error=bool(final.get("is_error")),
        final_indicates_success=success,
        has_final_event=bool(final),
    )


def _run_claude_phase(
    *,
    variant: dict[str, Any],
    prompt: str,
    project_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
    command_prefix: list[str] | None,
    isolated_env: dict[str, str],
    harness: str,
    slug: str,
    phase_name: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
) -> tuple[ClaudeCodeStreamResult, subprocess.Popen[str], float]:
    command = build_command(variant["main_model"], prompt, command_prefix)
    wall_start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=project_dir.resolve(),
        env=isolated_env,
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


def _subagent_counts(invocations: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for invocation in invocations:
        counts[invocation.get("subagent_type") or "unknown"] += 1
    return dict(counts)


def _merge_counts(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    merged = dict(first)
    for key, value in second.items():
        merged[key] = merged.get(key, 0) + value
    return merged


def _merge_claude_model_usage(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {key: dict(value) for key, value in first.items()}
    for model_id, usage in second.items():
        if model_id not in merged:
            merged[model_id] = dict(usage)
            continue
        _merge_token_counts(merged[model_id], usage)
    return merged


def _merge_token_counts(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "inputTokens",
        "outputTokens",
        "cacheReadInputTokens",
        "cacheCreationInputTokens",
    ):
        target[key] = target.get(key, 0) + source.get(key, 0)


def _apply_env_overrides(
    env: dict[str, str],
    overrides: dict[str, Any],
    log_tag: str,
) -> None:
    if not overrides:
        return
    applied: list[str] = []
    for raw_key, raw_value in overrides.items():
        _apply_one_env_override(env, str(raw_key), raw_value, applied, log_tag)
    print_line(f"[{log_tag}] env_overrides applied: {', '.join(applied)}")


def _apply_one_env_override(
    env: dict[str, str],
    raw_key: str,
    raw_value: Any,
    applied: list[str],
    log_tag: str,
) -> None:
    if raw_key.startswith("UNSET:"):
        target = raw_key.split(":", 1)[1]
        env.pop(target, None)
        applied.append(f"unset {target}")
        return
    _set_env_override(env, raw_key, str(raw_value), applied, log_tag)


def _set_env_override(
    env: dict[str, str],
    key: str,
    value: str,
    applied: list[str],
    log_tag: str,
) -> None:
    if not value.startswith("$"):
        env[key] = value
        applied.append(f"{key}={value}")
        return
    resolved = os.environ.get(value[1:], "")
    if not resolved:
        print_line(
            f"[{log_tag}] WARNING: env override {key} references {value} "
            "but it is empty in parent env"
        )
    env[key] = resolved
    applied.append(f"{key}=<{value}>")


def _build_claude_env(
    *,
    variant: dict[str, Any],
    log_tag: str,
) -> dict[str, str]:
    env = os.environ.copy()
    _apply_env_overrides(env, variant.get("env_overrides") or {}, log_tag)
    return env


def _run_claude_lifecycle_phase(
    *,
    request: PhaseRunRequest,
    variant: dict[str, Any],
    command_prefix: list[str] | None,
    isolated_env: dict[str, str],
    harness: str,
    slug: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    elapsed_field: str = "elapsed_seconds",
) -> dict[str, Any]:
    request.prompt_path.write_text(request.prompt)
    result, process, elapsed = _run_claude_phase(
        variant=variant,
        prompt=request.prompt,
        project_dir=request.project_dir,
        stdout_path=request.stdout_path,
        stderr_path=request.stderr_path,
        command_prefix=command_prefix,
        isolated_env=isolated_env,
        harness=harness,
        slug=slug,
        phase_name=request.phase_name,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )
    return _claude_phase_payload(
        request=request,
        variant=variant,
        result=result,
        process=process,
        elapsed=elapsed,
        command_prefix=command_prefix,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
        elapsed_field=elapsed_field,
    )


def _claude_phase_payload(
    *,
    request: PhaseRunRequest,
    variant: dict[str, Any],
    result: ClaudeCodeStreamResult,
    process: subprocess.Popen[str],
    elapsed: float,
    command_prefix: list[str] | None,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    elapsed_field: str = "elapsed_seconds",
) -> dict[str, Any]:
    final = result.final_result_event or {}
    usage = _dict_or_empty(final.get("usage"))
    model_usage = _dict_or_empty(final.get("modelUsage"))
    status = _phase_status_from_stream(result, final)
    command = build_command(variant["main_model"], request.prompt, command_prefix)
    return {
        "phase": request.phase_name,
        "status": status,
        "started_at": request.started_at,
        "ended_at": utc_now(),
        elapsed_field: elapsed,
        "timed_out": result.timed_out,
        "stalled": result.stalled,
        "stall_reason": result.stall_reason,
        "timeout_seconds": timeout_seconds,
        "no_progress_timeout_seconds": no_progress_timeout_seconds,
        "exit_code": process.returncode,
        "file_count": count_files(request.project_dir),
        "num_turns": final.get("num_turns", result.assistant_turns),
        "assistant_turns": result.assistant_turns,
        "stop_reason": final.get("stop_reason"),
        "usage_total": usage,
        "model_usage": model_usage,
        "tool_use_counts": dict(result.tool_use_counts),
        "subagent_invocations": result.subagent_invocations,
        "subagent_invocation_counts": _subagent_counts(result.subagent_invocations),
        "prompt_sha256": prompt_sha256(request.prompt),
        "command": command[:-1] + ["<prompt>"],
        "paths": {
            "stream_ndjson": str(request.stdout_path),
            "stderr_log": str(request.stderr_path),
        },
    }


def _claude_phase_record(
    phase: dict[str, Any], *, elapsed_field: str = "elapsed_seconds"
) -> dict[str, Any]:
    keys = (
        "phase",
        "status",
        "started_at",
        "ended_at",
        elapsed_field,
        "timed_out",
        "stalled",
        "exit_code",
        "file_count",
        "num_turns",
        "model_usage",
        "prompt_sha256",
    )
    return {key: phase[key] for key in keys if key in phase}


def _finalize_claude_payload(
    *,
    payload: dict[str, Any],
    phases: list[dict[str, Any]],
    variant: dict[str, Any],
    prompt: str,
    followup_prompt: str | None,
    cli_version_fields: dict[str, Any],
    elapsed_field: str = "elapsed_seconds",
) -> dict[str, Any]:
    phase1 = phases[0]
    payload.update(
        {
            "slug": variant["slug"],
            "label": variant.get("label"),
            "main_model": variant["main_model"],
            "subagent": variant.get("subagent"),
            "prompt_sha256": prompt_sha256(prompt),
            "command": phase1.get("command", []),
            "phases": [
                _claude_phase_record(phase, elapsed_field=elapsed_field)
                for phase in phases
            ],
            **cli_version_fields,
        }
    )
    if len(phases) > 1:
        _merge_claude_followup_payload(payload, phase1, phases[-1], followup_prompt)
    return payload


def _merge_claude_followup_payload(
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
            "model_usage": _merge_claude_model_usage(
                phase1["model_usage"], phase2["model_usage"]
            ),
            "tool_use_counts": _merge_counts(
                phase1["tool_use_counts"], phase2["tool_use_counts"]
            ),
            "subagent_invocations": phase1["subagent_invocations"]
            + phase2["subagent_invocations"],
            "subagent_invocation_counts": _merge_counts(
                phase1["subagent_invocation_counts"],
                phase2["subagent_invocation_counts"],
            ),
            "followup_prompt_sha256": prompt_sha256(followup_prompt),
        }
    )


def _print_claude_start(
    *,
    slug: str,
    variant: dict[str, Any],
    result_dir: Path,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    command_prefix: list[str] | None,
    log_tag: str,
) -> None:
    subagent = variant.get("subagent")
    subagent_name = subagent.get("name") if isinstance(subagent, dict) else "none"
    print_line("")
    print_line(
        f"Starting {slug} -> {variant['main_model']} "
        f"(subagent={subagent_name})"
    )
    print_line(f"[{log_tag}] results_dir={result_dir}")
    print_line(
        f"[{log_tag}] timeout={timeout_seconds}s "
        f"no_progress_timeout={no_progress_timeout_seconds}s"
    )
    if command_prefix:
        print_line(f"[{log_tag}] command_prefix={command_prefix}")


def _print_claude_completion(
    payload: dict[str, Any],
    slug: str,
    log_tag: str,
) -> None:
    model_usage = _dict_or_empty(payload.get("model_usage"))
    elapsed = payload.get("elapsed_seconds", payload.get("elapsed_minutes"))
    print_line("")
    print_line(
        f"Finished {slug} status={payload['status']} "
        f"elapsed={float(elapsed):.2f}s "
        f"files={payload['file_count']} turns={payload['num_turns']} "
        f"delegations={len(payload.get('subagent_invocations', []))}"
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
    harness: str = "claude",
    explicit_result_dir: Path | None = None,
    followup_prompt: str | None = None,
    rate_limit_policy: RateLimitWaitPolicy | None = None,
    replicate_index: int = 1,
    num_runs: int | None = None,
    include_agent_rules: bool = True,
    for_benchmark_build: bool = False,
    wrap_primary_prompt: bool = True,
    elapsed_field: str = "elapsed_seconds",
) -> dict[str, Any]:
    """Run a single benchmark variant.

    runner_command_prefix overrides the default ["claude"] head — used for setups
    where Claude Code is invoked via a wrapper (e.g. ["ollama","launch","claude"]
    for Ollama-served models). A per-variant `command_prefix` field takes precedence.

    explicit_result_dir: when set (e.g. audit harness), use this path directly
    instead of ``results_dir / f"{harness}-{slug}"``.
    """
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
    env_cache: dict[str, str] | None = None
    cli_version_fields_cache: dict[str, Any] | None = None
    runtime_isolation: dict[str, str] = {}

    def get_env() -> dict[str, str]:
        nonlocal env_cache
        if env_cache is None:
            env_cache = _build_claude_env(variant=variant, log_tag=log_tag)
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
        write_project_agent(paths.project_dir, variant.get("subagent"))
        _print_claude_start(
            slug=slug,
            variant=variant,
            result_dir=result_dir,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            command_prefix=command_prefix,
            log_tag=log_tag,
        )
        get_env()
        return None

    def run_phase(request: PhaseRunRequest) -> dict[str, Any]:
        return _run_claude_lifecycle_phase(
            request=request,
            variant=variant,
            command_prefix=command_prefix,
            isolated_env=get_env(),
            harness=harness,
            slug=slug,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            elapsed_field=elapsed_field,
        )

    def finalize_payload(
        payload: dict[str, Any],
        phases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _finalize_claude_payload(
            payload=payload,
            phases=phases,
            variant=variant,
            prompt=prompt,
            followup_prompt=followup_prompt,
            cli_version_fields=get_cli_version_fields(),
            elapsed_field=elapsed_field,
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
        after_save=lambda payload: _print_claude_completion(
            payload, slug=slug, log_tag=log_tag
        ),
        phase_log_tag=lambda phase_name: stream_log_prefix(harness, slug, phase_name),
        replicate_index=replicate_index,
        num_runs=effective_num_runs,
        include_agent_rules=include_agent_rules,
        wrap_primary_prompt=wrap_primary_prompt,
        extra_payload_fields={"runtime_isolation": runtime_isolation},
        elapsed_field=elapsed_field,
    ).run()
