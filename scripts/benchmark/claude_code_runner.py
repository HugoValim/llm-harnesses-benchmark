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

from benchmark.cli_stream import CliStreamAdapter, EventDecision, run_cli_stream_loop
from benchmark.harnesses.stall_policy import ERROR_LOOP_THRESHOLD
from benchmark.timeouts import (
    DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from benchmark.result_layout import target_dir as layout_target_dir
from benchmark.util import (
    RESULT_SCHEMA_VERSION,
    USAGE_LIMIT_REACHED,
    contains_usage_limit,
    count_files,
    format_value,
    init_project_git,
    print_line,
    prompt_sha256,
    save_json,
    shorten_text,
    stream_log_prefix,
    utc_now,
    validate_benchmark_workspace,
    write_project_context,
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

        is_error = (etype == "result" and event.get("is_error")) or (
            etype == "system" and event.get("subtype") == "error"
        )
        if is_error:
            if contains_usage_limit(json.dumps(event)):
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


def run_variant(
    *,
    variant: dict[str, Any],
    prompt: str,
    results_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    no_progress_timeout_seconds: int = DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    force: bool = False,
    runner_command_prefix: list[str] | None = None,
    isolate_home: bool = False,
    harness: str = "claude",
    explicit_result_dir: Path | None = None,
    followup_prompt: str | None = None,
) -> dict[str, Any]:
    """Run a single benchmark variant.

    runner_command_prefix overrides the default ["claude"] head — used for setups
    where Claude Code is invoked via a wrapper (e.g. ["ollama","launch","claude"]
    for Ollama-served models). A per-variant `command_prefix` field takes precedence.

    isolate_home replaces $HOME with the result_dir during the run. This prevents
    user-level ~/.claude/agents/*.md from leaking into the run, but it also breaks
    Claude subscription auth (which reads credentials from the real ~/.claude/).
    Default is False; opt in via runner.isolate_home in the variants config when
    you're using API-key auth and want strict agent isolation.

    explicit_result_dir: when set (e.g. audit harness), use this path directly
    instead of ``results_dir / f"{harness}-{slug}"``.
    """
    slug = variant["slug"]
    log_tag = stream_log_prefix(harness, slug)
    result_dir = (
        explicit_result_dir.resolve()
        if explicit_result_dir is not None
        else layout_target_dir(results_dir, harness, slug).resolve()
    )
    project_dir = result_dir / "project"
    prompt_path = result_dir / "prompt.txt"
    stdout_path = result_dir / "stream.ndjson"
    stderr_path = result_dir / "stderr.log"
    result_path = result_dir / "result.json"

    result_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    init_project_git(project_dir)
    validate_benchmark_workspace(results_dir, result_dir, project_dir)
    write_project_context(project_dir)

    if not force and result_path.exists():
        try:
            cached = json.loads(result_path.read_text())
            if cached.get("status") in (
                "completed",
                "completed_with_errors",
                "failed",
                "timeout",
                USAGE_LIMIT_REACHED,
            ):
                print_line(
                    f"[{log_tag}] cached result status={cached['status']}; "
                    "skipping (use --force to rerun)"
                )
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    # Write project-local agent definition (for delegation variants)
    write_project_agent(project_dir, variant.get("subagent"))

    prompt_path.write_text(prompt)
    started_at = utc_now()
    command_prefix = variant.get("command_prefix") or runner_command_prefix
    command = build_command(variant["main_model"], prompt, command_prefix)
    wall_start = time.monotonic()

    print_line("")
    print_line(
        f"Starting {slug} -> {variant['main_model']} (subagent={variant.get('subagent', {}).get('name') if variant.get('subagent') else 'none'})"
    )
    print_line(f"[{log_tag}] results_dir={result_dir}")
    print_line(
        f"[{log_tag}] timeout={timeout_seconds}s "
        f"no_progress_timeout={no_progress_timeout_seconds}s"
    )
    if command_prefix:
        print_line(f"[{log_tag}] command_prefix={command_prefix}")

    isolated_env = os.environ.copy()
    if isolate_home:
        # Replace HOME with the result_dir to prevent user-level ~/.claude/agents/*.md
        # from leaking into the run. Only safe when auth is via ANTHROPIC_API_KEY —
        # subscription auth reads ~/.claude/.credentials.json from the real HOME and
        # will fail under isolation.
        isolated_env["HOME"] = str(result_dir.resolve())
        print_line(
            f"[{log_tag}] HOME isolated to {result_dir} "
            "(API-key auth required; subscription auth will fail)"
        )
    else:
        print_line(
            f"[{log_tag}] HOME not isolated — subscription auth via ~/.claude/ works; "
            "user-level agents may leak"
        )

    # Optional per-variant env overrides — used by deepclaude-style variants that swap
    # ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN + ANTHROPIC_DEFAULT_*_MODEL to point
    # Claude Code's tool loop at a different (Anthropic-compatible) backend like
    # DeepSeek V4 Pro via OpenRouter. Values may reference $ENVVAR for indirection
    # (e.g. "$OPENROUTER_API_KEY") which gets resolved against the parent env at run
    # time so secrets aren't committed to config files. UNSET= prefix removes the
    # variable from the subprocess env (used to drop ANTHROPIC_API_KEY when swapping).
    overrides = variant.get("env_overrides") or {}
    if overrides:
        applied = []
        for raw_key, raw_val in overrides.items():
            if raw_key.startswith("UNSET:"):
                target = raw_key.split(":", 1)[1]
                isolated_env.pop(target, None)
                applied.append(f"unset {target}")
                continue
            val = str(raw_val)
            if val.startswith("$"):
                # Indirect lookup so we don't commit secrets to JSON
                resolved = os.environ.get(val[1:], "")
                if not resolved:
                    print_line(
                        f"[{log_tag}] WARNING: env override {raw_key} references {val} "
                        "but it is empty in parent env"
                    )
                isolated_env[raw_key] = resolved
                applied.append(f"{raw_key}=<{val}>")
            else:
                isolated_env[raw_key] = val
                applied.append(f"{raw_key}={val}")
        print_line(f"[{log_tag}] env_overrides applied: {', '.join(applied)}")

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
        model_slug=stream_log_prefix(harness, slug, "phase1"),
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )
    wall_end = time.monotonic()
    elapsed = round(wall_end - wall_start, 2)

    # Extract usage and timing data from the final result event
    final = result.final_result_event or {}
    usage = final.get("usage", {})
    model_usage = final.get("modelUsage", {})
    stop_reason = final.get("stop_reason")
    num_turns = final.get("num_turns", result.assistant_turns)

    usage_limited = result.usage_limit_reached or (
        bool(final.get("is_error")) and contains_usage_limit(json.dumps(final))
    )
    if usage_limited:
        status = USAGE_LIMIT_REACHED
        print_line(
            f"[{log_tag}] usage limit reached — aborting remaining Claude variants"
        )
    elif result.timed_out:
        status = "timeout"
    elif result.stalled:
        status = "failed"
    elif final.get("is_error"):
        status = "failed"
    elif stop_reason in ("end_turn", "stop_sequence", None) and final:
        status = "completed"
    else:
        status = "completed_with_errors"

    file_count = count_files(project_dir)

    # Aggregate subagent token usage per model
    subagent_counts_by_type: dict[str, int] = defaultdict(int)
    for inv in result.subagent_invocations:
        subagent_counts_by_type[inv.get("subagent_type") or "unknown"] += 1

    payload = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "harness": "claude",
        "slug": slug,
        "label": variant.get("label"),
        "main_model": variant["main_model"],
        "subagent": variant.get("subagent"),
        "status": status,
        "started_at": started_at,
        "ended_at": utc_now(),
        "elapsed_seconds": elapsed,
        "timed_out": result.timed_out,
        "stalled": result.stalled,
        "stall_reason": result.stall_reason,
        "timeout_seconds": timeout_seconds,
        "no_progress_timeout_seconds": no_progress_timeout_seconds,
        "exit_code": process.returncode,
        "file_count": file_count,
        "num_turns": num_turns,
        "assistant_turns": result.assistant_turns,
        "stop_reason": stop_reason,
        "usage_total": usage,
        "model_usage": model_usage,
        "tool_use_counts": dict(result.tool_use_counts),
        "subagent_invocations": result.subagent_invocations,
        "subagent_invocation_counts": dict(subagent_counts_by_type),
        "prompt_sha256": prompt_sha256(prompt),
        "command": command[:-1]
        + ["<prompt>"],  # don't dump the full prompt into result.json
        "paths": {
            "project_dir": str(project_dir),
            "prompt": str(prompt_path),
            "stream_ndjson": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
    }
    run_phase2 = (
        followup_prompt is not None
        and not payload.get("timed_out")
        and not payload.get("stalled")
        and payload.get("status") != USAGE_LIMIT_REACHED
    )
    if run_phase2:
        assert followup_prompt is not None  # narrowing for type checker
        followup_prompt_path = result_dir / "followup-prompt.txt"
        followup_stdout_path = result_dir / "followup-stream.ndjson"
        followup_stderr_path = result_dir / "followup-stderr.log"
        followup_prompt_path.write_text(followup_prompt)
        p2_command = build_command(variant["main_model"], followup_prompt, command_prefix)
        p2_started_at = utc_now()
        p2_wall_start = time.monotonic()
        print_line(
            f"[{stream_log_prefix(harness, slug, 'phase1')}] complete; "
            "starting phase 2 (follow-up prompt)"
        )
        p2_process = subprocess.Popen(
            p2_command,
            cwd=project_dir.resolve(),
            env=isolated_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=1,
        )
        p2_result = stream_process(
            process=p2_process,
            stdout_path=followup_stdout_path,
            stderr_path=followup_stderr_path,
            project_dir=project_dir,
            model_slug=stream_log_prefix(harness, slug, "phase2"),
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
        )
        p2_elapsed = round(time.monotonic() - p2_wall_start, 2)
        p2_final = p2_result.final_result_event or {}
        p2_model_usage = p2_final.get("modelUsage", {})
        p2_stop_reason = p2_final.get("stop_reason")
        p2_num_turns = p2_final.get("num_turns", p2_result.assistant_turns)
        p2_usage_limited = p2_result.usage_limit_reached or (
            bool(p2_final.get("is_error")) and contains_usage_limit(json.dumps(p2_final))
        )
        if p2_usage_limited:
            p2_status = USAGE_LIMIT_REACHED
        elif p2_result.timed_out:
            p2_status = "timeout"
        elif p2_result.stalled:
            p2_status = "failed"
        elif p2_final.get("is_error"):
            p2_status = "failed"
        elif p2_stop_reason in ("end_turn", "stop_sequence", None) and p2_final:
            p2_status = "completed"
        else:
            p2_status = "completed_with_errors"
        p2_file_count = count_files(project_dir)
        p2_subagent_counts: dict[str, int] = defaultdict(int)
        for inv in p2_result.subagent_invocations:
            p2_subagent_counts[inv.get("subagent_type") or "unknown"] += 1
        phase1_core = {
            "phase": "phase1",
            "status": payload["status"],
            "started_at": payload["started_at"],
            "ended_at": payload["ended_at"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "timed_out": payload["timed_out"],
            "stalled": payload["stalled"],
            "exit_code": payload["exit_code"],
            "file_count": payload["file_count"],
            "num_turns": payload["num_turns"],
            "model_usage": payload["model_usage"],
            "prompt_sha256": payload["prompt_sha256"],
        }
        phase2_core = {
            "phase": "phase2",
            "status": p2_status,
            "started_at": p2_started_at,
            "ended_at": utc_now(),
            "elapsed_seconds": p2_elapsed,
            "timed_out": p2_result.timed_out,
            "stalled": p2_result.stalled,
            "exit_code": p2_process.returncode,
            "file_count": p2_file_count,
            "num_turns": p2_num_turns,
            "model_usage": p2_model_usage,
            "prompt_sha256": prompt_sha256(followup_prompt),
        }
        merged_model_usage: dict[str, Any] = {k: dict(v) for k, v in model_usage.items()}
        for model_id, p2_u in p2_model_usage.items():
            if model_id in merged_model_usage:
                m = merged_model_usage[model_id]
                for tok_key in (
                    "inputTokens",
                    "outputTokens",
                    "cacheReadInputTokens",
                    "cacheCreationInputTokens",
                ):
                    m[tok_key] = m.get(tok_key, 0) + p2_u.get(tok_key, 0)
            else:
                merged_model_usage[model_id] = dict(p2_u)
        combined_tool_use = dict(result.tool_use_counts)
        for k, v in p2_result.tool_use_counts.items():
            combined_tool_use[k] = combined_tool_use.get(k, 0) + v
        combined_subagent_counts: dict[str, int] = dict(subagent_counts_by_type)
        for k, v in p2_subagent_counts.items():
            combined_subagent_counts[k] = combined_subagent_counts.get(k, 0) + v
        payload.update({
            "status": p2_status,
            "ended_at": utc_now(),
            "elapsed_seconds": round(elapsed + p2_elapsed, 2),
            "timed_out": p2_result.timed_out,
            "stalled": p2_result.stalled,
            "stall_reason": p2_result.stall_reason,
            "exit_code": p2_process.returncode,
            "file_count": p2_file_count,
            "num_turns": num_turns + p2_num_turns,
            "assistant_turns": result.assistant_turns + p2_result.assistant_turns,
            "stop_reason": p2_stop_reason,
            "usage_total": p2_final.get("usage", {}),
            "model_usage": merged_model_usage,
            "tool_use_counts": combined_tool_use,
            "subagent_invocations": result.subagent_invocations + p2_result.subagent_invocations,
            "subagent_invocation_counts": combined_subagent_counts,
            "followup_prompt_sha256": prompt_sha256(followup_prompt),
            "phases": [phase1_core, phase2_core],
            "paths": {
                **payload["paths"],
                "followup_prompt": str(followup_prompt_path),
                "followup_stream_ndjson": str(followup_stdout_path),
                "followup_stderr_log": str(followup_stderr_path),
            },
        })
        status = p2_status
        elapsed = elapsed + p2_elapsed
        file_count = p2_file_count
        num_turns = num_turns + p2_num_turns
        model_usage = merged_model_usage

    save_json(result_path, payload)

    print_line("")
    print_line(
        f"Finished {slug} status={status} elapsed={elapsed:.2f}s files={file_count} "
        f"turns={num_turns} delegations={len(payload.get('subagent_invocations', []))}"
    )
    if model_usage:
        print_line(f"[{log_tag}] model_usage:")
        for model, u in model_usage.items():
            in_tok = u.get("inputTokens", 0)
            out_tok = u.get("outputTokens", 0)
            cache_read = u.get("cacheReadInputTokens", 0)
            print_line(f"  {model}: in={in_tok} out={out_tok} cache_read={cache_read}")

    return payload
