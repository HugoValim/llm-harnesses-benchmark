"""Concurrent job pool with backfill when workers finish."""

from __future__ import annotations

from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def job_pool_workers(total_jobs: int, workers: int) -> int:
    """Return worker count for one job pool.

    Example:
        ``job_pool_workers(5, 0)`` returns ``5``.
    """
    if total_jobs <= 0:
        return 1
    if workers <= 0:
        return total_jobs
    return max(1, min(workers, total_jobs))


def run_job_pool(
    jobs: list[T],
    workers: int,
    run_job: Callable[[T], R],
) -> list[R]:
    """Keep up to ``workers`` jobs running; backfill on completion.

    Example:
        ``run_job_pool(items, 3, process)`` runs at most three ``process`` calls
        concurrently until ``items`` is exhausted.
    """
    if not jobs:
        return []
    worker_count = job_pool_workers(len(jobs), workers)
    if worker_count == 1:
        return [run_job(job) for job in jobs]

    pending: deque[T] = deque(jobs)
    in_flight: set[Future[R]] = set()
    results: list[R] = []

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        while pending or in_flight:
            while pending and len(in_flight) < worker_count:
                in_flight.add(pool.submit(run_job, pending.popleft()))

            if not in_flight:
                break

            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                results.append(fut.result())

    return results
