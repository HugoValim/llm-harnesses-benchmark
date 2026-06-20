"""Shared streaming loop for CLI-style harnesses (claude, cursor).

These harnesses emit NDJSON events ending in a terminal ``result`` event. The
loop owns IO (select/readline/write-through), heartbeat, stall detection,
terminal-result grace, timeout, and process-group teardown.

Per-harness specifics live on a ``CliStreamAdapter`` subclass:

- :meth:`CliStreamAdapter.on_event` parses one event and mutates adapter
  state (turn count, tool counts, subagent invocations, error counter, …).
  It returns an :class:`EventDecision` telling the loop what to do.
- :meth:`CliStreamAdapter.heartbeat_detail` returns the per-harness
  heartbeat suffix (e.g. ``"turns=N delegations=N session=X"``).
- :meth:`CliStreamAdapter.build_result` produces the harness-specific
  result struct (claude vs cursor).

The opencode/codex runner uses :class:`benchmark.stream_state.EventStreamState`
instead — it parses a different event schema (``step_start``/``step_finish``
/``tool_use``) and has a separate TPS-gating concern.
"""

from __future__ import annotations

import json
import select
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from benchmark.util import (
    count_files,
    format_duration,
    print_line,
    shorten_text,
    terminate_process_group,
)

_HEARTBEAT_INTERVAL_SECONDS = 10.0
_TERMINAL_GRACE_SECONDS = 5.0
_TERMINATE_WAIT_SECONDS = 2.0
_SELECT_TIMEOUT_SECONDS = 1.0


@dataclass
class EventDecision:
    """What the shared loop should do with one parsed event.

    Adapters return this from :meth:`CliStreamAdapter.on_event`.
    """

    description: str | None = None
    """Human-readable label used for log lines and ``last_activity_detail``."""

    is_terminal: bool = False
    """True when this event is the terminal ``result`` event — starts the grace clock."""

    mark_activity: bool = True
    """Whether this event resets the idle-stall clock. Cursor sets this False for
    ``user`` events so a long human-driven prompt cycle doesn't count as activity."""

    abort_reason: str | None = None
    """Non-None means abort immediately. Used for usage-limit and error-loop hits."""


ResultT = TypeVar("ResultT")


class CliStreamAdapter(Generic[ResultT]):
    """Per-harness event parser and result builder for the shared CLI stream loop.

    Subclass and implement :meth:`on_event`, :meth:`heartbeat_detail`, and
    :meth:`build_result`. The base class only declares the contract.
    """

    model_slug: str

    def on_event(self, event: dict[str, Any], now: float) -> EventDecision:
        raise NotImplementedError

    def heartbeat_detail(self) -> str:
        raise NotImplementedError

    def build_result(
        self,
        *,
        stdout: str,
        stderr: str,
        timed_out: bool,
        stalled: bool,
        stall_reason: str | None,
    ) -> ResultT:
        raise NotImplementedError


def run_cli_stream_loop(
    process: subprocess.Popen[str],
    adapter: CliStreamAdapter[ResultT],
    *,
    stdout_path: Path,
    stderr_path: Path,
    project_dir: Path,
    timeout_seconds: int,
    no_progress_timeout_seconds: int,
    append_output: bool = False,
) -> ResultT:
    """Drive a CLI-style harness subprocess and return the adapter-built result.

    Owns: select/readline, NDJSON write-through, heartbeat with file-count
    snapshot, idle-stall detection, terminal-result grace, timeout, and
    process-group teardown. Delegates event semantics to ``adapter``.
    """
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    started = time.monotonic()
    last_activity = started
    last_activity_detail = "process started"
    last_heartbeat = 0.0
    last_file_count = count_files(project_dir)
    terminal_seen_at: float | None = None

    def _finalize(
        *, timed_out: bool, stalled: bool, stall_reason: str | None
    ) -> ResultT:
        return adapter.build_result(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            timed_out=timed_out,
            stalled=stalled,
            stall_reason=stall_reason,
        )

    output_mode = "a" if append_output else "w"
    with stdout_path.open(output_mode) as stdout_file, stderr_path.open(output_mode) as stderr_file:
        while True:
            now = time.monotonic()
            elapsed = now - started

            if elapsed >= timeout_seconds:
                terminate_process_group(process)
                return _finalize(timed_out=True, stalled=False, stall_reason=None)

            streams = [s for s in (process.stdout, process.stderr) if s is not None]
            ready, _, _ = (
                select.select(streams, [], [], _SELECT_TIMEOUT_SECONDS)
                if streams
                else ([], [], [])
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

                    decision = adapter.on_event(event, now)

                    if decision.abort_reason is not None:
                        terminate_process_group(process)
                        return _finalize(
                            timed_out=False,
                            stalled=True,
                            stall_reason=decision.abort_reason,
                        )
                    if decision.is_terminal:
                        terminal_seen_at = now
                    if decision.description:
                        last_activity_detail = decision.description
                        print_line(f"[{adapter.model_slug}] {decision.description}")
                    if decision.mark_activity:
                        last_activity = now
                else:
                    stderr_chunks.append(chunk)
                    stderr_file.write(chunk)
                    stderr_file.flush()
                    last_activity = now
                    stripped = chunk.strip()
                    if stripped:
                        last_activity_detail = f"stderr: {shorten_text(stripped)}"
                        print_line(f"[{adapter.model_slug}] {last_activity_detail}")

            if (
                terminal_seen_at is not None
                and (now - terminal_seen_at) >= _TERMINAL_GRACE_SECONDS
            ):
                if process.poll() is None:
                    terminate_process_group(process)
                    try:
                        process.wait(timeout=_TERMINATE_WAIT_SECONDS)
                    except subprocess.TimeoutExpired:
                        pass
                print_line(
                    f"[{adapter.model_slug}] terminal result observed; "
                    f"finalizing after {_TERMINAL_GRACE_SECONDS:.0f}s grace"
                )
                return _finalize(timed_out=False, stalled=False, stall_reason=None)

            if now - last_heartbeat >= _HEARTBEAT_INTERVAL_SECONDS:
                file_count = count_files(project_dir)
                if file_count != last_file_count:
                    last_file_count = file_count
                    last_activity = now
                    last_activity_detail = f"project file count changed to {file_count}"
                print_line(
                    f"[{adapter.model_slug}] heartbeat elapsed={format_duration(elapsed)} "
                    f"files={file_count} {adapter.heartbeat_detail()} "
                    f"{last_activity_detail}"
                )
                last_heartbeat = now

            idle = now - last_activity
            if idle >= no_progress_timeout_seconds:
                terminate_process_group(process)
                return _finalize(
                    timed_out=False,
                    stalled=True,
                    stall_reason=(
                        f"no progress for {format_duration(idle)}; "
                        f"last: {last_activity_detail}"
                    ),
                )

            if process.poll() is not None and not ready:
                return _finalize(timed_out=False, stalled=False, stall_reason=None)
