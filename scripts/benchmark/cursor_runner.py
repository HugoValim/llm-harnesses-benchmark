"""Runner for Cursor Agent CLI headless benchmark (agent -p --output-format stream-json)."""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.util import (
    USAGE_LIMIT_REACHED,
    contains_usage_limit,
    count_files,
    format_duration,
    init_project_git,
    print_line,
    prompt_sha256,
    save_json,
    shorten_text,
    terminate_process_group,
    utc_now,
    validate_benchmark_workspace,
    write_project_context,
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


def _kill_group(process: subprocess.Popen[str]) -> None:
    terminate_process_group(process)


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


def stream_process(
    process: subprocess.Popen[str],
    stdout_path: Path,
    stderr_path: Path,
    project_dir: Path,
    model_slug: str,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
) -> CursorStreamResult:
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    last_heartbeat = 0.0
    heartbeat_interval = 10.0
    started = time.monotonic()
    last_activity = started
    last_activity_detail = "process started"
    last_file_count = count_files(project_dir)
    consecutive_error_events = 0
    error_loop_threshold = 5
    final_result_event: dict[str, Any] | None = None
    terminal_result_seen_at: float | None = None
    terminal_grace_seconds = 5.0
    tool_use_counts: Counter = Counter()
    assistant_turns = 0

    def _build(
        timed_out: bool, stalled: bool, stall_reason: str | None
    ) -> CursorStreamResult:
        return CursorStreamResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
            usage_limit_reached=(stall_reason == USAGE_LIMIT_REACHED),
            final_result_event=final_result_event,
            tool_use_counts=tool_use_counts,
            assistant_turns=assistant_turns,
        )

    with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
        while True:
            now = time.monotonic()
            elapsed = now - started

            if elapsed >= timeout_seconds:
                _kill_group(process)
                return _build(True, False, None)

            streams = [s for s in (process.stdout, process.stderr) if s is not None]
            ready, _, _ = (
                select.select(streams, [], [], 1.0) if streams else ([], [], [])
            )

            for stream in ready:
                chunk = stream.readline()
                if chunk == "":
                    continue
                if stream is process.stdout:
                    stdout_chunks.append(chunk)
                    stdout_file.write(chunk)
                    stdout_file.flush()
                    stripped = chunk.strip()
                    if not stripped:
                        continue
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError:
                        last_activity = now
                        continue

                    etype = event.get("type")
                    if etype == "assistant":
                        assistant_turns += 1
                    if etype == "tool_call":
                        tc = event.get("tool_call") or {}
                        tool_use_counts[_tool_call_label(tc)] += 1
                        last_activity = now
                    if etype == "result":
                        final_result_event = event
                        terminal_result_seen_at = now

                    description = _describe_event(event)
                    if description:
                        last_activity_detail = description
                        print_line(f"[{model_slug}] {description}")

                    is_error = bool(event.get("is_error")) or (
                        etype == "result" and event.get("subtype") not in ("success", None)
                    )
                    if is_error:
                        if contains_usage_limit(json.dumps(event)):
                            _kill_group(process)
                            return _build(False, True, USAGE_LIMIT_REACHED)
                        consecutive_error_events += 1
                        if consecutive_error_events >= error_loop_threshold:
                            _kill_group(process)
                            return _build(
                                False,
                                True,
                                f"{consecutive_error_events} consecutive errors",
                            )
                    elif etype != "user":
                        consecutive_error_events = 0
                        last_activity = now
                else:
                    stderr_chunks.append(chunk)
                    stderr_file.write(chunk)
                    stderr_file.flush()
                    last_activity = now
                    stripped = chunk.strip()
                    if stripped:
                        last_activity_detail = f"stderr: {shorten_text(stripped)}"
                        print_line(f"[{model_slug}] {last_activity_detail}")

            if (
                terminal_result_seen_at is not None
                and (now - terminal_result_seen_at) >= terminal_grace_seconds
            ):
                if process.poll() is None:
                    _kill_group(process)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                print_line(
                    f"[{model_slug}] terminal result observed; finalizing after "
                    f"{terminal_grace_seconds:.0f}s grace"
                )
                return _build(False, False, None)

            if now - last_heartbeat >= heartbeat_interval:
                file_count = count_files(project_dir)
                if file_count != last_file_count:
                    last_file_count = file_count
                    last_activity = now
                    last_activity_detail = f"project file count changed to {file_count}"
                print_line(
                    f"[{model_slug}] heartbeat elapsed={format_duration(elapsed)} "
                    f"files={file_count} turns={assistant_turns} {last_activity_detail}"
                )
                last_heartbeat = now

            idle = now - last_activity
            if idle >= no_progress_timeout_seconds:
                _kill_group(process)
                return _build(
                    False,
                    True,
                    f"no progress for {format_duration(idle)}; last: {last_activity_detail}",
                )

            if process.poll() is not None and not ready:
                return _build(False, False, None)


def _phase_status(
    stream_result: CursorStreamResult,
    final: dict[str, Any],
) -> str:
    if stream_result.usage_limit_reached or (
        bool(final.get("is_error")) and contains_usage_limit(json.dumps(final))
    ):
        return USAGE_LIMIT_REACHED
    if stream_result.timed_out:
        return "timeout"
    if stream_result.stalled:
        return "failed"
    if final.get("is_error"):
        return "failed"
    if _result_indicates_success(final):
        return "completed"
    if final:
        return "completed_with_errors"
    return "failed"


def run_variant(
    *,
    variant: dict[str, Any],
    prompt: str,
    results_dir: Path,
    timeout_seconds: int = 5400,
    no_progress_timeout_seconds: int = 360,
    force: bool = False,
    runner_command_prefix: list[str] | None = None,
    harness: str = "cursor",
    explicit_result_dir: Path | None = None,
    followup_prompt: str | None = None,
) -> dict[str, Any]:
    """Run a single Cursor CLI benchmark variant."""
    slug = variant["slug"]
    result_dir = (
        explicit_result_dir.resolve()
        if explicit_result_dir is not None
        else (results_dir / f"{harness}-{slug}").resolve()
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
                    f"[{slug}] cached result status={cached['status']}; "
                    "skipping (use --force to rerun)"
                )
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    prompt_path.write_text(prompt)
    started_at = utc_now()
    command_prefix = variant.get("command_prefix") or runner_command_prefix
    command = build_command(variant["main_model"], prompt, command_prefix)
    wall_start = time.monotonic()

    print_line("")
    print_line(f"Starting {slug} -> {variant['main_model']} (Cursor CLI)")
    print_line(f"[{slug}] results_dir={result_dir}")
    print_line(
        f"[{slug}] timeout={timeout_seconds}s "
        f"no_progress_timeout={no_progress_timeout_seconds}s"
    )

    process = subprocess.Popen(
        command,
        cwd=project_dir.resolve(),
        env=os.environ.copy(),
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
        model_slug=slug,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
    )
    elapsed = round(time.monotonic() - wall_start, 2)
    final = result.final_result_event or {}
    num_turns = result.assistant_turns
    status = _phase_status(result, final)
    file_count = count_files(project_dir)

    payload: dict[str, Any] = {
        "slug": slug,
        "label": variant.get("label"),
        "main_model": variant["main_model"],
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
        "result_subtype": final.get("subtype"),
        "duration_ms": final.get("duration_ms"),
        "tool_use_counts": dict(result.tool_use_counts),
        "prompt_sha256": prompt_sha256(prompt),
        "command": command[:-1] + ["<prompt>"],
        "paths": {
            "project_dir": str(project_dir),
            "prompt": str(prompt_path),
            "stream_ndjson": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
    }

    run_phase2 = (
        followup_prompt is not None
        and not result.timed_out
        and not result.stalled
        and status != USAGE_LIMIT_REACHED
    )
    if run_phase2:
        followup_prompt_path = result_dir / "followup-prompt.txt"
        followup_stdout_path = result_dir / "followup-stream.ndjson"
        followup_stderr_path = result_dir / "followup-stderr.log"
        followup_prompt_path.write_text(followup_prompt)
        p2_command = build_command(
            variant["main_model"],
            followup_prompt,
            command_prefix,
            continue_session=True,
        )
        p2_started_at = utc_now()
        p2_wall_start = time.monotonic()
        print_line(f"[{slug}] starting phase 2 (follow-up, --continue)")
        p2_process = subprocess.Popen(
            p2_command,
            cwd=project_dir.resolve(),
            env=os.environ.copy(),
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
            model_slug=slug,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
        )
        p2_elapsed = round(time.monotonic() - p2_wall_start, 2)
        p2_final = p2_result.final_result_event or {}
        p2_status = _phase_status(p2_result, p2_final)
        phase1_core = {
            "phase": "phase1",
            "status": payload["status"],
            "elapsed_seconds": payload["elapsed_seconds"],
            "num_turns": payload["num_turns"],
            "file_count": payload["file_count"],
        }
        phase2_core = {
            "phase": "phase2",
            "status": p2_status,
            "elapsed_seconds": p2_elapsed,
            "num_turns": p2_result.assistant_turns,
            "file_count": count_files(project_dir),
        }
        combined_tools = dict(result.tool_use_counts)
        for k, v in p2_result.tool_use_counts.items():
            combined_tools[k] = combined_tools.get(k, 0) + v
        payload.update({
            "status": p2_status,
            "ended_at": utc_now(),
            "elapsed_seconds": round(elapsed + p2_elapsed, 2),
            "timed_out": p2_result.timed_out,
            "stalled": p2_result.stalled,
            "stall_reason": p2_result.stall_reason,
            "exit_code": p2_process.returncode,
            "file_count": phase2_core["file_count"],
            "num_turns": num_turns + p2_result.assistant_turns,
            "assistant_turns": result.assistant_turns + p2_result.assistant_turns,
            "result_subtype": p2_final.get("subtype"),
            "duration_ms": p2_final.get("duration_ms"),
            "tool_use_counts": combined_tools,
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
        elapsed = payload["elapsed_seconds"]
        file_count = payload["file_count"]
        num_turns = payload["num_turns"]

    save_json(result_path, payload)
    print_line(
        f"Finished {slug} status={status} elapsed={elapsed:.2f}s "
        f"files={file_count} turns={num_turns}"
    )
    return payload
