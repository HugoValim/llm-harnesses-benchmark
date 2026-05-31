"""Tests for benchmark.job_pool."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.job_pool import job_pool_workers, run_job_pool  # noqa: E402


def test_job_pool_workers_caps_at_jobs() -> None:
    assert job_pool_workers(9, 2) == 2


def test_job_pool_workers_zero_means_all_jobs() -> None:
    assert job_pool_workers(5, 0) == 5


def test_run_job_pool_keeps_workers_busy_until_queue_empty() -> None:
    max_in_flight = 0
    in_flight = 0
    lock = threading.Lock()
    slow_release = threading.Event()
    slow_started = threading.Event()
    second_started = threading.Event()

    def run_job(job_id: int) -> int:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        if job_id == 1:
            slow_started.set()
            slow_release.wait(timeout=5.0)
        elif job_id == 2:
            second_started.set()
        with lock:
            in_flight -= 1
        return job_id

    results: list[int] = []

    def runner() -> None:
        results.extend(run_job_pool([1, 2, 3, 4, 5], 3, run_job))

    thread = threading.Thread(target=runner)
    thread.start()
    assert slow_started.wait(timeout=2.0)
    assert second_started.wait(timeout=2.0), "expected job 2 to start while job 1 blocked"
    slow_release.set()
    thread.join(timeout=10.0)

    assert not thread.is_alive()
    assert max_in_flight <= 3
    assert set(results) == {1, 2, 3, 4, 5}
