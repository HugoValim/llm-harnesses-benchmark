"""Tests for interrupt-driven subprocess cleanup."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.active_processes import (  # noqa: E402
    register,
    run_tracked_subprocess,
    terminate_all,
    unregister,
)
from benchmark.job_pool import run_job_pool  # noqa: E402


def test_terminate_all_kills_registered_subprocess() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        start_new_session=True,
    )
    register(process)
    try:
        stopped = terminate_all(reason="test")
        assert stopped == 1
        assert process.poll() is not None
    finally:
        unregister(process)


def test_run_tracked_subprocess_registers_until_complete() -> None:
    completed = run_tracked_subprocess(
        [sys.executable, "-c", "print('ok')"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert completed.returncode == 0


def test_run_job_pool_calls_terminate_all_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_terminate_all(*, reason: str = "interrupt") -> int:
        calls.append(reason)
        return 0

    monkeypatch.setattr("benchmark.job_pool.terminate_all", fake_terminate_all)

    def run_job(_job: int) -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_job_pool([1], 1, run_job)

    assert calls == ["Ctrl+C"]
