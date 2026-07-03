"""Track in-flight subprocesses so Ctrl+C stops parallel benchmark jobs."""

from __future__ import annotations

import signal
import subprocess
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from benchmark.util import print_line, terminate_process_group

_lock = threading.RLock()
_processes: set[subprocess.Popen[Any]] = set()
_handlers_installed = False


def register(process: subprocess.Popen[Any]) -> None:
    """Register one subprocess for interrupt-driven teardown."""
    with _lock:
        _processes.add(process)


def unregister(process: subprocess.Popen[Any]) -> None:
    """Stop tracking a subprocess after it exits."""
    with _lock:
        _processes.discard(process)


def terminate_all(*, reason: str = "interrupt", log: bool = True) -> int:
    """SIGTERM then SIGKILL every registered subprocess process group."""
    with _lock:
        targets = list(_processes)
    if not targets:
        return 0
    if log:
        print_line(f"Stopping {len(targets)} in-flight job(s) ({reason})...")
    for process in targets:
        terminate_process_group(process)
    with _lock:
        _processes.difference_update(targets)
    return len(targets)


def run_tracked_subprocess(
    cmd: Sequence[str],
    *,
    cwd: Path | str | None = None,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` in a new session and register it until completion."""
    kwargs.setdefault("start_new_session", True)
    kwargs.setdefault("text", True)
    process = subprocess.Popen(list(cmd), cwd=cwd, **kwargs)
    register(process)
    try:
        stdout, stderr = process.communicate()
        completed = subprocess.CompletedProcess(
            list(cmd),
            process.returncode or 0,
            stdout,
            stderr,
        )
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode, completed.args, completed.stdout, completed.stderr
            )
        return completed
    finally:
        unregister(process)


@contextmanager
def track_process(process: subprocess.Popen[Any]) -> Iterator[subprocess.Popen[Any]]:
    """Register an existing ``Popen`` for the duration of a stream loop."""
    register(process)
    try:
        yield process
    finally:
        unregister(process)


def _handle_interrupt(signum: int, _frame: object) -> None:
    name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    terminate_all(reason=name, log=False)
    if signum == signal.SIGTERM:
        raise SystemExit(128 + signum)
    raise KeyboardInterrupt


def install_interrupt_handlers() -> None:
    """Ensure SIGINT/SIGTERM tear down registered subprocesses before exit."""
    global _handlers_installed
    if _handlers_installed:
        return
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    _handlers_installed = True
