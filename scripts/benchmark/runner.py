"""Process management and benchmark execution."""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from benchmark.backends import LocalModelBackend
from benchmark.agent_runtime_env import codex_env_for_phase, runtime_isolation_for_env
from benchmark.build_parity import FOLLOWUP_CONTINUITY_COLD
from benchmark.commands import (
    build_codex_command,
    build_opencode_command,
    write_codex_subagent_toml,
)
from benchmark.util import ollama_launch_command_prefix
from benchmark.config import (
    OPENCODE_YOLO_PERMISSION,
    BenchmarkConfig,
    _resolve_model_num_runs,
    existing_terminal_result,
    mark_model_skip_by_default,
)
from benchmark.harnesses.stall_policy import (
    ERROR_LOOP_THRESHOLD,
    TOOL_LOOP_THRESHOLD,
)
from benchmark.phase_result import build_phase_payload
from benchmark.rate_limit import RateLimitWaitPolicy, run_with_rate_limit_retry
from benchmark.timeouts import (
    DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from benchmark.replicates import attach_replicate_fields, resolve_result_dir
from benchmark.session_export import export_opencode_session
from benchmark.stream_state import ActionKind, EventStreamState
from benchmark.target_lifecycle import (
    PhaseRunRequest,
    TargetRunLifecycle,
    TargetRunPaths,
)

_SKIP_CONFIG_LOCK = threading.Lock()

_CODEX_RUNNERS: frozenset[str] = frozenset({"codex", "ollama"})

from benchmark.workspace import (
    detect_workspace_escape,
    prepare_project_workspace,
    summarize_project,
    snapshot_root_generated_markers,
)
from benchmark.util import (
    RESULT_SCHEMA_VERSION,
    USAGE_LIMIT_REACHED,
    count_files,
    format_duration,
    format_value,
    print_line,
    prompt_sha256,
    resolve_harness_cli_versions,
    save_json,
    shorten_text,
    stream_log_prefix,
    terminate_process_group,
    utc_now,
)


@dataclass
class StreamResult:
    """Output from a streamed opencode process."""

    stdout: str
    stderr: str
    timed_out: bool
    stalled: bool
    stall_reason: str | None
    latest_preview_output_tps: float | None
    preview_average_output_tps: float | None


def kill_process_group(process: subprocess.Popen[str]) -> None:
    terminate_process_group(process)


def _phase_capture_paths(payload: dict[str, Any]) -> list[Path | None]:
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return []
    captured: list[Path | None] = []
    for key in ("stdout", "stderr"):
        value = paths.get(key)
        captured.append(Path(value) if isinstance(value, str) else None)
    return captured


def _run_phase_with_rate_limit_retry(
    *,
    log_tag: str,
    policy: RateLimitWaitPolicy,
    run_once: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return run_with_rate_limit_retry(
        log_tag=log_tag,
        policy=policy,
        run_once=run_once,
        capture_paths=_phase_capture_paths,
    )


def parse_event_stream(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def extract_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    finish = next(
        (event for event in reversed(events) if event.get("type") == "step_finish"), {}
    )
    tokens = finish.get("part", {}).get("tokens", {}) if finish else {}
    text_parts = []
    for event in events:
        if event.get("type") != "text":
            continue
        text = event.get("part", {}).get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return {
        "session_id": next(
            (event.get("sessionID") for event in events if event.get("sessionID")), None
        ),
        "finish_reason": finish.get("part", {}).get("reason"),
        "tokens": tokens,
        "assistant_output": "\n".join(text_parts).strip(),
    }


def extract_codex_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract session/token metrics from Codex CLI JSONL events."""
    thread_id = None
    total_input = 0
    total_output = 0
    text_parts: list[str] = []
    last_turn_failed = False

    for event in events:
        etype = event.get("type")
        if etype == "thread.started":
            thread_id = event.get("thread_id")
        elif etype == "turn.completed":
            usage = event.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            last_turn_failed = False
        elif etype == "turn.failed":
            last_turn_failed = True
        elif etype == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                text = item.get("text", "")
                if isinstance(text, str) and text:
                    text_parts.append(text)

    total_tokens = total_input + total_output
    return {
        "session_id": thread_id,
        "finish_reason": "stop" if not last_turn_failed else "error",
        "tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_tokens,
        },
        "assistant_output": "\n".join(text_parts).strip(),
    }


def describe_event(event: dict[str, Any]) -> str | None:
    event_type = event.get("type")
    part = event.get("part", {})
    if event_type == "step_start":
        return "assistant started"
    if event_type == "step_finish":
        reason = part.get("reason", "unknown")
        tokens = part.get("tokens", {}).get("total")
        if tokens is None:
            return f"assistant finished ({reason})"
        return f"assistant finished ({reason}, total_tokens={tokens})"
    if event_type == "text":
        text = part.get("text", "")
        if isinstance(text, str) and text:
            return f"assistant text: {shorten_text(text)}"
        return "assistant text"
    if part.get("type"):
        return f"event: {part['type']}"
    if event_type:
        return f"event: {event_type}"
    return None


def describe_codex_event(event: dict[str, Any]) -> str | None:
    """Human-readable description of a Codex JSONL event for heartbeat logs."""
    etype = event.get("type")
    if etype == "thread.started":
        return f"codex thread started: {event.get('thread_id', '-')}"
    if etype == "turn.started":
        return "codex turn started"
    if etype == "turn.completed":
        usage = event.get("usage", {})
        out = usage.get("output_tokens", 0)
        return f"codex turn completed (output_tokens={out})"
    if etype == "turn.failed":
        msg = event.get("error", {}).get("message", "unknown")
        return f"codex turn failed: {shorten_text(str(msg))}"
    if etype == "error":
        return f"codex error: {shorten_text(event.get('message', 'unknown'))}"
    if etype == "item.started":
        item = event.get("item", {})
        return f"codex item started: {item.get('type', 'unknown')}"
    if etype == "item.completed":
        item = event.get("item", {})
        itype = item.get("type", "unknown")
        if itype == "agent_message":
            text = item.get("text", "")
            return f"codex message: {shorten_text(text)}"
        if itype == "command_execution":
            cmd = item.get("command", "")
            return f"codex command: {shorten_text(cmd)}"
        if itype == "file_change":
            return "codex file_change"
        return f"codex item completed: {itype}"
    return None


def stream_process_output(
    *,
    process: subprocess.Popen[str],
    stdout_path: Path,
    stderr_path: Path,
    project_dir: Path,
    model_slug: str,
    backend: LocalModelBackend | None,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    min_preview_output_tps: float | None,
    min_preview_samples: int,
    event_describer: Callable[[dict[str, Any]], str | None] | None = None,
) -> StreamResult:
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_buffer = ""
    stderr_buffer = ""
    last_event_message: str | None = None
    last_heartbeat = 0.0
    heartbeat_interval = 10.0
    started = time.monotonic()
    last_activity = started
    last_activity_detail = "process started"
    last_file_count = count_files(project_dir)
    terminal_stop_grace_seconds = 5.0
    error_loop_threshold = ERROR_LOOP_THRESHOLD

    event_state = EventStreamState(
        model_slug=model_slug,
        min_preview_output_tps=min_preview_output_tps,
        min_preview_samples=min_preview_samples,
        error_loop_threshold=error_loop_threshold,
        tool_loop_threshold=TOOL_LOOP_THRESHOLD,
    )

    def _make_result(
        timed_out: bool, stalled: bool, stall_reason: str | None
    ) -> StreamResult:
        return StreamResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
            latest_preview_output_tps=event_state.latest_preview_output_tps,
            preview_average_output_tps=event_state.preview_average_output_tps,
        )

    closed_streams: set[Any] = set()

    with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
        while True:
            now = time.monotonic()
            elapsed = now - started

            if elapsed >= timeout_seconds:
                kill_process_group(process)
                if stdout_buffer:
                    stdout_chunks.append(stdout_buffer)
                    stdout_file.write(stdout_buffer)
                if stderr_buffer:
                    stderr_chunks.append(stderr_buffer)
                    stderr_file.write(stderr_buffer)
                return _make_result(True, False, None)

            ready_streams: list[Any] = []
            streams = [
                s
                for s in (process.stdout, process.stderr)
                if s is not None and s not in closed_streams
            ]
            if streams:
                ready_streams, _, _ = select.select(streams, [], [], 1.0)

            for stream in ready_streams:
                chunk = stream.readline()
                if chunk == "":
                    closed_streams.add(stream)
                    continue
                if stream is process.stdout:
                    stdout_chunks.append(chunk)
                    stdout_file.write(chunk)
                    stdout_file.flush()
                    stripped = chunk.strip()
                    if stripped:
                        try:
                            event = json.loads(stripped)
                        except json.JSONDecodeError:
                            last_activity = now
                            last_event_message = f"stdout: {shorten_text(stripped)}"
                            last_activity_detail = last_event_message
                        else:
                            prev_tps_count = event_state.tps_sample_count
                            action = event_state.process_event(event)

                            if event_state.is_error_event:
                                count = event_state.consecutive_error_events
                                description = event_state.last_description or ""
                                last_event_message = description
                                last_activity_detail = description
                                if count <= 2:
                                    print_line(f"[{model_slug}] {description}")
                                elif count == error_loop_threshold:
                                    print_line(
                                        f"[{model_slug}] {count} consecutive error events, suppressing further output"
                                    )
                                last_activity = now
                            else:
                                last_activity = now

                            if event_state.tps_sample_count > prev_tps_count:
                                tps = event_state.latest_preview_output_tps
                                print_line(
                                    f"[{model_slug}] preview output_tps={tps:.2f}"
                                )
                                avg = event_state.preview_average_output_tps
                                if avg is not None and event_state.tps_sample_count == min_preview_samples:
                                    print_line(
                                        f"[{model_slug}] preview average output_tps="
                                        f"{avg:.2f} over first {min_preview_samples} steps"
                                    )

                            if action.kind in (ActionKind.STALL, ActionKind.TPS_GATE_FAIL):
                                assert action.reason is not None
                                kill_process_group(process)
                                print_line(f"[{model_slug}] {action.reason}")
                                return _make_result(False, True, action.reason)

                            if not event_state.is_error_event:
                                _describer = event_describer or describe_event
                                description = _describer(event)
                                if description:
                                    last_event_message = description
                                    last_activity_detail = description
                                    print_line(f"[{model_slug}] {description}")
                else:
                    stderr_chunks.append(chunk)
                    stderr_file.write(chunk)
                    stderr_file.flush()
                    last_activity = now
                    stripped = chunk.strip()
                    if stripped:
                        last_event_message = f"stderr: {shorten_text(stripped)}"
                        last_activity_detail = last_event_message
                        print_line(f"[{model_slug}] {last_event_message}")

            grace_action = event_state.check_terminal_grace(
                now=now, grace_seconds=terminal_stop_grace_seconds
            )
            if grace_action.kind == ActionKind.GRACEFUL_STOP:
                if process.poll() is None:
                    kill_process_group(process)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                print_line(
                    f"[{model_slug}] terminal stop observed; finalizing after {terminal_stop_grace_seconds:.0f}s grace period"
                )
                return _make_result(False, False, None)

            if now - last_heartbeat >= heartbeat_interval:
                file_count = count_files(project_dir)
                if file_count != last_file_count:
                    last_file_count = file_count
                    last_activity = now
                    last_activity_detail = f"project file count changed to {file_count}"
                session_hint = event_state.session_id if event_state.session_id else "-"
                detail = (
                    last_event_message if last_event_message else "waiting for output"
                )
                remote_state = backend.fetch_status_string() if backend else None
                remote_suffix = f" {remote_state}" if remote_state else ""
                print_line(
                    f"[{model_slug}] heartbeat elapsed={format_duration(elapsed)} files={file_count} session={session_hint}{remote_suffix} {detail}"
                )
                last_heartbeat = now

            idle_seconds = now - last_activity
            idle_action = event_state.check_idle(
                idle_seconds=idle_seconds,
                no_progress_timeout_seconds=no_progress_timeout_seconds,
                last_activity_detail=last_activity_detail,
            )
            if idle_action.kind == ActionKind.STALL:
                assert idle_action.reason is not None
                kill_process_group(process)
                print_line(f"[{model_slug}] {idle_action.reason}")
                return _make_result(False, True, idle_action.reason)

            if process.poll() is not None and not streams:
                if stdout_buffer:
                    stdout_chunks.append(stdout_buffer)
                    stdout_file.write(stdout_buffer)
                if stderr_buffer:
                    stderr_chunks.append(stderr_buffer)
                    stderr_file.write(stderr_buffer)
                return _make_result(False, False, None)


def apply_opencode_noninteractive_env(env: dict[str, str]) -> None:
    """Force OpenCode into noninteractive, benchmark-safe configuration mode."""

    env["OPENCODE_YOLO"] = "1"
    env["OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS"] = "true"
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        {"permission": OPENCODE_YOLO_PERMISSION}, separators=(",", ":")
    )





def run_opencode_phase(
    *,
    bench: BenchmarkConfig,
    model: dict[str, Any],
    model_slug: str,
    prompt: str,
    started_at: str,
    project_dir: Path,
    prompt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    result_path: Path | None,
    continue_session_id: str | None = None,
    phase_name: str = "phase1",
    override_min_preview_tps: float | None = ...,  # sentinel
    command_prefix: list[str] | None = None,
) -> dict[str, Any]:
    root_dir = bench.results_dir.resolve().parent
    before_markers = snapshot_root_generated_markers(root_dir, bench.results_dir)
    prompt_path.write_text(prompt)
    effective_prefix = command_prefix or model.get("command_prefix")
    command = build_opencode_command(
        bench.runner,
        model["id"],
        prompt,
        project_dir,
        continue_session_id=continue_session_id,
        command_prefix=effective_prefix,
    )
    wall_start = time.monotonic()
    process_env = os.environ.copy()
    process_env["OPENCODE_PERMISSION"] = json.dumps(
        OPENCODE_YOLO_PERMISSION, separators=(",", ":")
    )
    apply_opencode_noninteractive_env(process_env)
    log_tag = stream_log_prefix(bench.harness, model_slug, phase_name)
    process = subprocess.Popen(
        command,
        cwd=project_dir,
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        bufsize=1,
    )

    effective_min_tps = (
        bench.min_preview_output_tps
        if override_min_preview_tps is ...
        else override_min_preview_tps
    )

    result = stream_process_output(
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=project_dir,
        model_slug=stream_log_prefix(bench.harness, model_slug, phase_name),
        backend=bench.backend,
        timeout_seconds=bench.timeout_seconds,
        no_progress_timeout_seconds=bench.no_progress_timeout_seconds,
        min_preview_output_tps=effective_min_tps,
        min_preview_samples=bench.min_preview_samples,
    )

    wall_end = time.monotonic()
    events = parse_event_stream(result.stdout)
    metrics = extract_metrics(events)
    project_summary = summarize_project(project_dir)
    elapsed_seconds = round(wall_end - wall_start, 2)
    payload = build_phase_payload(
        phase_name=phase_name,
        assistant_output=metrics["assistant_output"],
        command=command,
        continued_from_session=continue_session_id,
        elapsed_seconds=elapsed_seconds,
        ended_at=utc_now(),
        exit_code=process.returncode,
        finish_reason=metrics["finish_reason"],
        model=model,
        session_id=metrics["session_id"],
        paths={
            "project_dir": str(project_dir),
            "prompt": str(prompt_path),
            "stderr": str(stderr_path),
            "stdout": str(stdout_path),
        },
        project_summary=project_summary,
        prompt=prompt,
        started_at=started_at,
        stderr=result.stderr,
        stalled=result.stalled,
        stall_reason=result.stall_reason,
        timed_out=result.timed_out,
        timeout_seconds=bench.timeout_seconds,
        no_progress_timeout_seconds=bench.no_progress_timeout_seconds,
        tokens=metrics["tokens"],
        harness_metrics={
            "preview_output_tokens_per_second": result.latest_preview_output_tps,
            "preview_output_tokens_per_second_average": result.preview_average_output_tps,
        },
    )
    payload["runtime_isolation"] = runtime_isolation_for_env(process_env)
    payload = detect_workspace_escape(
        payload,
        root_dir=root_dir,
        results_dir=bench.results_dir,
        project_dir=project_dir,
        before_markers=before_markers,
    )
    if result_path is not None:
        save_json(result_path, payload)
    return payload


def run_codex_phase(
    *,
    bench: BenchmarkConfig,
    model: dict[str, Any],
    model_slug: str,
    prompt: str,
    started_at: str,
    project_dir: Path,
    prompt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    result_path: Path | None,
    phase_name: str = "phase1",
    override_min_preview_tps: float | None = ...,  # sentinel
    command_prefix: list[str] | None = None,
    for_benchmark_build: bool = False,
) -> dict[str, Any]:
    """Run a single benchmark phase using the Codex CLI."""
    root_dir = bench.results_dir.resolve().parent
    before_markers = snapshot_root_generated_markers(root_dir, bench.results_dir)
    prompt_path.write_text(prompt)
    command = build_codex_command(
        model["id"],
        project_dir,
        reasoning_effort=model.get("codex_reasoning_effort"),
        codex_subagent=model.get("codex_subagent"),
        command_prefix=command_prefix,
        auto_compact_token_limit=model.get("codex_auto_compact_token_limit"),
    )
    wall_start = time.monotonic()

    process_env = codex_env_for_phase(
        os.environ.copy(),
        result_dir=prompt_path.parent,
        command_prefix=command_prefix,
    )
    log_tag = stream_log_prefix(bench.harness, model_slug, phase_name)

    process = subprocess.Popen(
        command,
        cwd=project_dir.resolve(),
        env=process_env,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        bufsize=1,
    )
    # Write prompt to stdin then close it so codex reads it via '-'
    if process.stdin:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except BrokenPipeError:
            pass

    effective_min_tps = (
        bench.min_preview_output_tps
        if override_min_preview_tps is ...
        else override_min_preview_tps
    )

    result = stream_process_output(
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=project_dir,
        model_slug=stream_log_prefix(bench.harness, model_slug, phase_name),
        backend=None,  # Codex models are cloud-only
        timeout_seconds=bench.timeout_seconds,
        no_progress_timeout_seconds=bench.no_progress_timeout_seconds,
        min_preview_output_tps=effective_min_tps,
        min_preview_samples=bench.min_preview_samples,
        event_describer=describe_codex_event,
    )

    wall_end = time.monotonic()
    events = parse_event_stream(result.stdout)
    metrics = extract_codex_metrics(events)
    project_summary = summarize_project(project_dir)
    elapsed_seconds = round(wall_end - wall_start, 2)
    payload = build_phase_payload(
        phase_name=phase_name,
        assistant_output=metrics["assistant_output"],
        command=command,
        continued_from_session=None,
        elapsed_seconds=elapsed_seconds,
        ended_at=utc_now(),
        exit_code=process.returncode,
        finish_reason=metrics["finish_reason"],
        model=model,
        session_id=metrics["session_id"],
        paths={
            "project_dir": str(project_dir),
            "prompt": str(prompt_path),
            "stderr": str(stderr_path),
            "stdout": str(stdout_path),
        },
        project_summary=project_summary,
        prompt=prompt,
        started_at=started_at,
        stderr=result.stderr,
        stalled=result.stalled,
        stall_reason=result.stall_reason,
        timed_out=result.timed_out,
        timeout_seconds=bench.timeout_seconds,
        no_progress_timeout_seconds=bench.no_progress_timeout_seconds,
        tokens=metrics["tokens"],
        harness_metrics={
            "preview_output_tokens_per_second": result.latest_preview_output_tps,
            "preview_output_tokens_per_second_average": result.preview_average_output_tps,
        },
    )
    if for_benchmark_build:
        payload["runtime_isolation"] = runtime_isolation_for_env(process_env)
    payload = detect_workspace_escape(
        payload,
        root_dir=root_dir,
        results_dir=bench.results_dir,
        project_dir=project_dir,
        before_markers=before_markers,
    )
    if result_path is not None:
        save_json(result_path, payload)
    return payload


def run_codex_variant(
    *,
    variant: dict[str, Any],
    prompt: str,
    results_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    no_progress_timeout_seconds: int = DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS,
    force: bool = False,
    harness: str = "codex",
    explicit_result_dir: Path | None = None,
    rate_limit_policy: RateLimitWaitPolicy | None = None,
    include_agent_rules: bool = True,
) -> dict[str, Any]:
    """Run a single one-shot variant through the Codex CLI.

    Mirrors :func:`benchmark.claude_code_runner.run_variant` so audit and
    meta-analysis scripts can dispatch through codex/ollama harnesses the
    same way they dispatch through Claude Code.

    ``variant`` schema is intentionally permissive: it accepts both
    ``id`` (build-style ``models.json`` entries) and ``main_model`` (audit-
    style entries) for the model identifier. ``runner_type`` controls the
    codex command-prefix shim:

    - ``"codex"`` (default): plain ``codex exec ...``.
    - ``"ollama"``: auto-injects ``["ollama","launch","codex"]`` as the
      command prefix unless the variant already sets ``command_prefix``.

    ``explicit_result_dir`` takes the same role it does in ``run_variant`` —
    audit harness uses it to land outputs in
    ``audit-reports/<auditor>/<target>/`` rather than the default
    ``results/<harness>-<slug>/`` layout.
    """
    slug = variant["slug"]
    model_id = variant.get("id") or variant.get("main_model")
    if not model_id:
        raise ValueError(
            f"variant {slug!r} is missing both 'id' and 'main_model' fields"
        )

    runner_type = variant.get("runner_type", "codex")
    if runner_type not in _CODEX_RUNNERS:
        raise ValueError(
            f"run_codex_variant requires runner_type in {sorted(_CODEX_RUNNERS)}, "
            f"got {runner_type!r}"
        )

    command_prefix = variant.get("command_prefix")
    if not command_prefix and runner_type == "ollama":
        command_prefix = ollama_launch_command_prefix("codex")

    result_dir = (
        explicit_result_dir.resolve()
        if explicit_result_dir is not None
        else layout_target_dir(results_dir, harness, slug).resolve()
    )
    project_dir = result_dir
    prepare_project_workspace(
        results_dir,
        result_dir,
        project_dir,
        include_agent_rules=include_agent_rules,
    )
    prompt_path = result_dir / "prompt.txt"
    stdout_path = result_dir / "stream.ndjson"
    stderr_path = result_dir / "stderr.log"
    result_path = result_dir / "result.json"

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
                    f"[{slug}] cached result status={cached['status']}; "
                    "skipping (use --force to rerun)"
                )
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    bench = BenchmarkConfig(
        runner={},
        config_path=Path(),
        results_dir=results_dir,
        harness=harness,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
        min_preview_output_tps=None,
        min_preview_samples=0,
        auto_skip_slow_preview=False,
        force=force,
        backend=None,
        selected_models=[],
        prompt=prompt,
        followup_prompt=None,
    )

    codex_model = {
        "slug": slug,
        "id": model_id,
        "label": variant.get("label", slug),
        "provider": variant.get("provider", "ollama_cloud" if runner_type == "ollama" else "codex"),
        "runner_type": runner_type,
    }
    for opt in (
        "codex_reasoning_effort",
        "codex_subagent",
        "codex_auto_compact_token_limit",
    ):
        if opt in variant:
            codex_model[opt] = variant[opt]

    print_line("")
    print_line(
        f"Starting codex-variant {slug} -> {model_id} (runner={runner_type})"
    )
    print_line(f"[{slug}] results_dir={result_dir}")
    print_line(
        f"[{slug}] timeout={timeout_seconds}s "
        f"no_progress_timeout={no_progress_timeout_seconds}s"
    )
    if command_prefix:
        print_line(f"[{slug}] command_prefix={command_prefix}")

    started_at = utc_now()
    effective_rate_limit_policy = rate_limit_policy or RateLimitWaitPolicy()
    payload = _run_phase_with_rate_limit_retry(
        log_tag=slug,
        policy=effective_rate_limit_policy,
        run_once=lambda: run_codex_phase(
            bench=bench,
            model=codex_model,
            model_slug=slug,
            prompt=prompt,
            started_at=started_at,
            project_dir=project_dir,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_path=result_path,
            phase_name="phase1",
            override_min_preview_tps=None,
            command_prefix=command_prefix,
        ),
    )
    payload.setdefault("result_schema_version", RESULT_SCHEMA_VERSION)
    payload.setdefault("harness", harness)
    payload.update(
        resolve_harness_cli_versions(harness=harness, command_prefix=command_prefix)
    )
    return payload


def _kill_stale_opencode_processes() -> None:
    """Kill stale opencode run processes that may hold the SQLite DB lock.

    When a benchmark run times out, the opencode child processes can survive
    and keep a write lock on ~/.local/share/opencode/opencode.db, causing all
    new opencode instances to hang silently with zero output.

    opencode launches as npm→node→.opencode, so we need multiple patterns
    to catch all layers of the process tree.
    """
    patterns = [
        "opencode.*run.*--agent",
        "opencode.*run.*--format",
        r"opencode-ai/bin/\.opencode",
    ]
    our_pid = os.getpid()
    our_ppid = os.getppid()
    stale: list[int] = []

    for pattern in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = [int(p) for p in result.stdout.strip().split() if p.strip()]
            stale.extend(
                p for p in pids if p not in (our_pid, our_ppid) and p not in stale
            )
        except (OSError, ValueError):
            continue

    if not stale:
        return

    print_line(f"Killing {len(stale)} stale opencode process(es): {stale}")
    for pid in stale:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(2)
    for pid in stale:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)


def _get_ollama_for_eviction() -> Any | None:
    """Get an OllamaBackend pointed at the home config URL, for eviction only."""
    from benchmark.backends import OllamaBackend
    from benchmark.config import load_opencode_ollama_api_base

    ollama_base = load_opencode_ollama_api_base()
    if ollama_base:
        return OllamaBackend(ollama_base)
    return None


def _evict_competing_backend(bench: BenchmarkConfig, log_tag: str) -> None:
    """Unload models from the other backend to free GPU memory.

    Ollama and llama-swap share the same GPU, so before using one backend
    we must ensure the other has released VRAM. Without this the server
    OOMs and hangs.
    """
    from benchmark.backends import LlamaSwapBackend, OllamaBackend

    if bench.backend is None:
        return

    if isinstance(bench.backend, LlamaSwapBackend):
        ollama = _get_ollama_for_eviction()
        if ollama:
            active = ollama.list_active()
            if active:
                print_line(
                    f"[{log_tag}] evicting Ollama models to free GPU: {', '.join(active)}"
                )
                ollama.unload_all()
                # Verify eviction succeeded
                still_active = ollama.list_active()
                if still_active:
                    print_line(
                        f"[{log_tag}] WARNING: Ollama still has models loaded after eviction: {', '.join(still_active)}"
                    )
    elif isinstance(bench.backend, OllamaBackend):
        # llama-swap auto-evicts on TTL but we can't force it.
        # Best-effort: load a tiny model to trigger swap, then unload it.
        pass


def _ensure_local_model_ready(
    model: dict[str, Any],
    bench: BenchmarkConfig,
) -> tuple[bool, str]:
    """Run preflight for a local model using the configured backend."""
    from benchmark.backends import LlamaSwapBackend

    log_tag = stream_log_prefix(bench.harness, model["slug"])

    if bench.backend is None:
        print_line(f"[{log_tag}] preflight skipped: no local backend configured")
        return True, "preflight skipped: no local backend configured"

    # Free GPU from the competing backend before loading
    _evict_competing_backend(bench, log_tag)

    if isinstance(bench.backend, LlamaSwapBackend):
        # llama-swap uses its own model names (e.g. "qwen3:32b"), not Ollama IDs.
        # Context is configured server-side, so context_limit is irrelevant.
        target_model = model.get("llama_swap_model")
        if not target_model:
            print_line(
                f"[{log_tag}] preflight skipped: no llama_swap_model configured"
            )
            return False, "no llama_swap_model configured for this model"
        return bench.backend.ensure_model_ready(
            target_model, log_tag, context_limit=None
        )

    target_model = model.get("ollama_model_name") or model["id"].split("/", 1)[-1]
    return bench.backend.ensure_model_ready(target_model, log_tag, context_limit=None)


def run_model(
    model: dict[str, Any],
    bench: BenchmarkConfig,
    index: int,
    total: int,
    *,
    skip_stale_kill: bool = False,
    replicate_index: int = 1,
    num_runs: int | None = None,
) -> dict[str, Any]:
    """Execute one harness run for ``model``.

    Args:
        model: Registry entry including ``slug``, ``runner_type``, etc.
        bench: Shared benchmark settings (timeouts, prompts, backend, …).
        index: Position in this batch for progress logs (``[index/total]``).
        total: Batch size used in progress logs.
        skip_stale_kill: When True, do not invoke :func:`_kill_stale_opencode_processes`;
            use once per concurrent opencode batch (see ``run_benchmark``).
        replicate_index: 1-based replicate folder index (``run_01``, …).
        num_runs: Total configured replicates; defaults to ``model['num_runs']``.
    """
    effective_num_runs = (
        num_runs if num_runs is not None else _resolve_model_num_runs(model)
    )
    result_dir = resolve_result_dir(
        results_dir=bench.results_dir,
        harness=bench.harness,
        slug=model["slug"],
        replicate_index=replicate_index,
    )
    paths = TargetRunPaths.opencode(result_dir)
    runner_type = model.get("runner_type", "opencode")
    log_tag = stream_log_prefix(bench.harness, model["slug"])
    phase_command_prefix: list[str] | None = None
    if runner_type in _CODEX_RUNNERS:
        phase_command_prefix = model.get("command_prefix")
        if not phase_command_prefix and runner_type == "ollama":
            phase_command_prefix = ollama_launch_command_prefix("codex")
    elif model.get("command_prefix"):
        phase_command_prefix = model.get("command_prefix")
    cli_version_fields_cache: dict[str, Any] | None = None

    def get_cli_version_fields() -> dict[str, Any]:
        nonlocal cli_version_fields_cache
        if cli_version_fields_cache is None:
            cli_version_fields_cache = resolve_harness_cli_versions(
                harness=bench.harness,
                command_prefix=phase_command_prefix,
            )
        return cli_version_fields_cache

    started_at = utc_now()
    is_local = model["provider"] == "ollama"

    def before_phases() -> dict[str, Any] | None:
        if runner_type not in _CODEX_RUNNERS and not skip_stale_kill:
            _kill_stale_opencode_processes()

        print_line("")
        print_line(
            f"[{index}/{total}] starting {log_tag} -> {model['id']} "
            f"(runner={runner_type})"
        )
        print_line(f"[{log_tag}] results_dir={result_dir}")
        print_line(f"[{log_tag}] timeout={bench.timeout_seconds}s")
        print_line(
            f"[{log_tag}] no_progress_timeout={bench.no_progress_timeout_seconds}s"
        )

        if not is_local:
            return None
        preflight_ok, preflight_message = _ensure_local_model_ready(model, bench)
        if preflight_ok:
            return None
        payload = {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "harness": bench.harness,
            "assistant_output_excerpt": "",
            "command": [],
            "elapsed_seconds": 0.0,
            "ended_at": utc_now(),
            "exit_code": None,
            "finish_reason": None,
            "model": model,
            "opencode_session_id": None,
            "paths": {
                "project_dir": str(paths.project_dir),
                "prompt": str(paths.prompt_path),
                "stderr": str(paths.stderr_path),
                "stdout": str(paths.stdout_path),
            },
            "project_summary": summarize_project(paths.project_dir),
            "prompt_sha256": prompt_sha256(bench.prompt),
            "started_at": started_at,
            "status": "failed",
            "stderr_excerpt": "",
            "timed_out": False,
            "timeout_seconds": bench.timeout_seconds,
            "no_progress_timeout_seconds": bench.no_progress_timeout_seconds,
            "tokens": {},
            "tokens_per_second": None,
            "output_tokens_per_second": None,
            "preview_output_tokens_per_second": None,
            "preview_output_tokens_per_second_average": None,
            "preflight_error": preflight_message,
            "phases": [],
            **get_cli_version_fields(),
        }
        return payload

    runtime_isolation: dict[str, str] = {}

    def run_phase(request: PhaseRunRequest) -> dict[str, Any]:
        phase_func = (
            run_codex_phase if runner_type in _CODEX_RUNNERS else run_opencode_phase
        )
        phase_kwargs: dict[str, Any] = {
            "bench": bench,
            "model": model,
            "model_slug": model["slug"],
            "prompt": request.prompt,
            "started_at": request.started_at,
            "project_dir": request.project_dir,
            "prompt_path": request.prompt_path,
            "stdout_path": request.stdout_path,
            "stderr_path": request.stderr_path,
            "result_path": request.result_path,
            "phase_name": request.phase_name,
        }
        if request.phase_name == "phase2":
            phase_kwargs["override_min_preview_tps"] = None
        if phase_command_prefix is not None:
            phase_kwargs["command_prefix"] = phase_command_prefix
        if runner_type not in _CODEX_RUNNERS:
            phase_kwargs["continue_session_id"] = request.continue_session_id
        if runner_type in _CODEX_RUNNERS:
            phase_kwargs["for_benchmark_build"] = True
        result = phase_func(**phase_kwargs)
        iso = result.get("runtime_isolation")
        if isinstance(iso, dict):
            runtime_isolation.clear()
            runtime_isolation.update(iso)
        return result

    def finalize_payload(
        payload: dict[str, Any],
        phases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        final_phase = phases[-1]
        phase1 = phases[0]
        mark_slow_preview_skip(final_phase)
        session_id = final_phase.get("opencode_session_id") or phase1.get(
            "opencode_session_id"
        )
        exported_session = export_session_artifact(session_id)
        payload.update(
            {
                "model": model,
                "opencode_session_id": session_id,
                "paths": {
                    **payload["paths"],
                    "session_export": str(exported_session)
                    if exported_session is not None
                    else None,
                },
                "session_exported": exported_session is not None,
                **get_cli_version_fields(),
            }
        )
        root_dir = bench.results_dir.resolve().parent
        return detect_workspace_escape(
            payload,
            root_dir=root_dir,
            results_dir=bench.results_dir,
            project_dir=paths.project_dir,
            before_markers=snapshot_root_generated_markers(
                root_dir, bench.results_dir
            ),
            session_export_path=exported_session,
        )

    def mark_slow_preview_skip(final_phase: dict[str, Any]) -> None:
        if not should_mark_slow_preview_skip(final_phase):
            return
        average_tps = float(final_phase["preview_output_tokens_per_second_average"])
        note = (
            " Skipped by default after benchmark preview averaged "
            f"{average_tps:.2f} output tok/s over the first "
            f"{bench.min_preview_samples} steps (< {bench.min_preview_output_tps:.2f})."
        )
        with _SKIP_CONFIG_LOCK:
            wrote = mark_model_skip_by_default(bench.config_path, model["slug"], note)
        if wrote:
            print_line(f"[{log_tag}] marked skip_by_default in {bench.config_path}")

    def should_mark_slow_preview_skip(final_phase: dict[str, Any]) -> bool:
        return (
            bench.auto_skip_slow_preview
            and isinstance(bench.min_preview_output_tps, float)
            and isinstance(
                final_phase.get("preview_output_tokens_per_second_average"),
                float,
            )
            and float(final_phase["preview_output_tokens_per_second_average"])
            < bench.min_preview_output_tps
        )

    def export_session_artifact(session_id: Any) -> Path | None:
        if runner_type in _CODEX_RUNNERS:
            return None
        process_env = os.environ.copy()
        process_env["OPENCODE_PERMISSION"] = json.dumps(
            OPENCODE_YOLO_PERMISSION, separators=(",", ":")
        )
        if not isinstance(session_id, str) or not session_id:
            return None
        assert paths.session_export_path is not None
        return export_opencode_session(
            session_id, paths.session_export_path, process_env, log_tag
        )

    def after_save(payload: dict[str, Any]) -> None:
        if payload.get("preflight_error"):
            print_line(
                f"[{index}/{total}] finished {model['slug']} status=failed "
                f"preflight_error={payload['preflight_error']}"
            )
            return
        total_elapsed = float(payload.get("elapsed_seconds") or 0.0)
        project_summary = payload.get("project_summary", {})
        file_count = (
            project_summary.get("file_count")
            if isinstance(project_summary, dict)
            else None
        )
        tokens = payload.get("tokens", {})
        total_tokens = tokens.get("total") if isinstance(tokens, dict) else None
        print_line(
            f"[{index}/{total}] finished {model['slug']} status={payload['status']} "
            f"elapsed={total_elapsed:.2f}s files={file_count} "
            f"total_tokens={format_value(total_tokens)}"
        )
        if is_local and bench.backend is not None:
            active = bench.backend.list_active()
            if active:
                print_line(
                    f"[{log_tag}] post-run cleanup: unloading {', '.join(active)}"
                )
                bench.backend.unload_all()

    return TargetRunLifecycle(
        harness=bench.harness,
        slug=model["slug"],
        results_dir=bench.results_dir,
        paths=paths,
        force=bench.force,
        prompt=bench.prompt,
        followup_prompt=bench.followup_prompt,
        run_phase=run_phase,
        rate_limit_policy=bench.rate_limit_policy,
        before_phases=before_phases,
        final_payload_hook=finalize_payload,
        after_save=after_save,
        phase_log_tag=lambda phase_name: stream_log_prefix(
            bench.harness, model["slug"], phase_name
        ),
        followup_continuity=FOLLOWUP_CONTINUITY_COLD,
        replicate_index=replicate_index,
        num_runs=effective_num_runs,
        include_agent_rules=bench.include_agent_rules,
        extra_payload_fields={"runtime_isolation": runtime_isolation},
    ).run()
