"""Tests for benchmark.job_pool."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.job_pool import (  # noqa: E402
    job_pool_workers,
    run_job_pool,
    run_target_pipelined_job_pool,
)


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


@dataclass(frozen=True)
class FakeTargetJob:
    target_key: tuple[str, str]
    replicate_index: int
    job_id: str


def test_run_target_pipelined_job_pool_never_overlaps_same_target() -> None:
    active: dict[tuple[str, str], int] = {}
    overlap = threading.Event()
    active_lock = threading.Lock()
    ran: list[str] = []

    def run_job(job: FakeTargetJob) -> str:
        key = job.target_key
        with active_lock:
            active[key] = active.get(key, 0) + 1
            if active[key] > 1:
                overlap.set()
        time.sleep(0.05)
        with active_lock:
            active[key] -= 1
        ran.append(job.job_id)
        return job.job_id

    target_a = ("codex", "model_a")
    target_b = ("codex", "model_b")
    jobs = [
        FakeTargetJob(target_a, 1, "a1"),
        FakeTargetJob(target_a, 2, "a2"),
        FakeTargetJob(target_a, 3, "a3"),
        FakeTargetJob(target_b, 1, "b1"),
    ]

    results = run_target_pipelined_job_pool(
        jobs,
        workers=3,
        run_job=run_job,
        target_key=lambda j: j.target_key,
        replicate_index=lambda j: j.replicate_index,
    )

    assert not overlap.is_set(), "same target replicates overlapped"
    assert set(results) == {"a1", "a2", "a3", "b1"}
    assert set(ran) == {"a1", "a2", "a3", "b1"}
