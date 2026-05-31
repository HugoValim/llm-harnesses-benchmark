"""Concurrent job pool with backfill when workers finish."""

from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")
TargetKey = tuple[str, str]


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


def _group_jobs_by_target(
    jobs: list[T],
    *,
    target_key: Callable[[T], TargetKey],
    replicate_index: Callable[[T], int],
) -> dict[TargetKey, list[T]]:
    grouped: dict[TargetKey, list[T]] = defaultdict(list)
    for job in jobs:
        grouped[target_key(job)].append(job)
    for target_jobs in grouped.values():
        target_jobs.sort(key=replicate_index)
    return dict(grouped)


def run_target_pipelined_job_pool(
    jobs: list[T],
    workers: int,
    run_job: Callable[[T], R],
    *,
    target_key: Callable[[T], TargetKey],
    replicate_index: Callable[[T], int],
    initial_next_index: Callable[[TargetKey], int] | None = None,
    on_complete: Callable[[T, R], bool] | None = None,
) -> list[R]:
    """Run jobs with per-target replicate serialization and a global worker cap.

    Example:
        ``run_target_pipelined_job_pool(jobs, 3, process, target_key=..., ...)``
        keeps up to three targets in flight while each target runs replicates
        one at a time.
    """
    if not jobs:
        return []

    grouped = _group_jobs_by_target(
        jobs, target_key=target_key, replicate_index=replicate_index
    )
    target_order = list(grouped.keys())
    next_idx: dict[TargetKey, int] = {
        key: (initial_next_index(key) if initial_next_index else 0)
        for key in target_order
    }
    in_flight_targets: set[TargetKey] = set()
    results: list[R] = []

    def has_pending() -> bool:
        return any(
            next_idx[key] < len(grouped[key]) and key not in in_flight_targets
            for key in target_order
        )

    worker_count = job_pool_workers(len(jobs), workers)
    if worker_count == 1:
        for key in target_order:
            for job in grouped[key][next_idx[key] :]:
                result = run_job(job)
                results.append(result)
                if on_complete is not None and not on_complete(job, result):
                    break
        return results

    future_to_context: dict[Future[R], tuple[TargetKey, T]] = {}
    in_flight: set[Future[R]] = set()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        while has_pending() or in_flight:
            while has_pending() and len(in_flight) < worker_count:
                for key in target_order:
                    if len(in_flight) >= worker_count:
                        break
                    if key in in_flight_targets:
                        continue
                    idx = next_idx[key]
                    target_jobs = grouped[key]
                    if idx >= len(target_jobs):
                        continue
                    job = target_jobs[idx]
                    in_flight_targets.add(key)
                    fut = pool.submit(run_job, job)
                    future_to_context[fut] = (key, job)
                    in_flight.add(fut)

            if not in_flight:
                break

            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                key, job = future_to_context.pop(fut)
                in_flight_targets.discard(key)
                result = fut.result()
                results.append(result)
                advance = on_complete(job, result) if on_complete else True
                if advance:
                    next_idx[key] += 1
                else:
                    next_idx[key] = len(grouped[key])

    return results
