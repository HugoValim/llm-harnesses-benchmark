"""Concurrent job pool with backfill when workers finish."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from typing import TypeVar

from benchmark.active_processes import terminate_all

T = TypeVar("T")
R = TypeVar("R")
TargetKey = tuple[str, str]
ConcurrencyKeysFn = Callable[[T], frozenset[str]]


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


def _keys_blocked(keys: frozenset[str], in_flight_keys: set[str]) -> bool:
    return bool(keys & in_flight_keys)


@contextmanager
def _interruptible_executor(max_workers: int) -> Iterator[ThreadPoolExecutor]:
    """Shut down worker threads and kill tracked subprocesses on Ctrl+C."""
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield pool
    except KeyboardInterrupt:
        terminate_all(reason="Ctrl+C")
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _pop_runnable_job(
    pending: deque[T],
    deferred: deque[T],
    *,
    concurrency_keys: ConcurrencyKeysFn[T] | None,
    in_flight_keys: set[str],
) -> T | None:
    """Return the next pending job whose concurrency keys are free."""
    scanned: list[T] = []
    while pending:
        job = pending.popleft()
        keys = concurrency_keys(job) if concurrency_keys is not None else frozenset()
        if concurrency_keys is None or not _keys_blocked(keys, in_flight_keys):
            pending.extendleft(reversed(scanned))
            return job
        scanned.append(job)
    pending.extendleft(reversed(scanned))

    scanned.clear()
    while deferred:
        job = deferred.popleft()
        keys = concurrency_keys(job) if concurrency_keys is not None else frozenset()
        if concurrency_keys is None or not _keys_blocked(keys, in_flight_keys):
            deferred.extend(scanned)
            return job
        scanned.append(job)
    deferred.extend(scanned)
    return None


def run_job_pool(
    jobs: list[T],
    workers: int,
    run_job: Callable[[T], R],
    *,
    concurrency_keys: ConcurrencyKeysFn[T] | None = None,
) -> list[R]:
    """Keep up to ``workers`` jobs running; backfill on completion.

    When ``concurrency_keys`` is set, jobs that share a key are not started
    until earlier jobs with the same key finish, but other jobs still backfill
    idle workers.
    """
    if not jobs:
        return []
    worker_count = job_pool_workers(len(jobs), workers)
    if worker_count == 1:
        try:
            return [run_job(job) for job in jobs]
        except KeyboardInterrupt:
            terminate_all(reason="Ctrl+C")
            raise

    pending: deque[T] = deque(jobs)
    deferred: deque[T] = deque()
    in_flight: set[Future[R]] = set()
    in_flight_keys: set[str] = set()
    results: list[R] = []

    with _interruptible_executor(worker_count) as pool:
        while pending or deferred or in_flight:
            while len(in_flight) < worker_count:
                job = _pop_runnable_job(
                    pending,
                    deferred,
                    concurrency_keys=concurrency_keys,
                    in_flight_keys=in_flight_keys,
                )
                if job is None:
                    break
                keys = (
                    concurrency_keys(job)
                    if concurrency_keys is not None
                    else frozenset()
                )
                in_flight_keys.update(keys)

                def run_with_release(
                    runnable_job: T,
                    runnable_keys: frozenset[str] = keys,
                ) -> R:
                    try:
                        return run_job(runnable_job)
                    finally:
                        in_flight_keys.difference_update(runnable_keys)

                in_flight.add(pool.submit(run_with_release, job))

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
    concurrency_keys: ConcurrencyKeysFn[T] | None = None,
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
    in_flight_concurrency_keys: set[str] = set()
    results: list[R] = []

    def has_pending() -> bool:
        return any(
            next_idx[key] < len(grouped[key]) and key not in in_flight_targets
            for key in target_order
        )

    worker_count = job_pool_workers(len(jobs), workers)
    if worker_count == 1:
        try:
            for key in target_order:
                for job in grouped[key][next_idx[key] :]:
                    result = run_job(job)
                    results.append(result)
                    if on_complete is not None and not on_complete(job, result):
                        break
            return results
        except KeyboardInterrupt:
            terminate_all(reason="Ctrl+C")
            raise

    future_to_context: dict[Future[R], tuple[TargetKey, T, frozenset[str]]] = {}
    in_flight: set[Future[R]] = set()

    with _interruptible_executor(worker_count) as pool:
        while has_pending() or in_flight:
            while has_pending() and len(in_flight) < worker_count:
                scheduled = False
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
                    keys = (
                        concurrency_keys(job)
                        if concurrency_keys is not None
                        else frozenset()
                    )
                    if concurrency_keys is not None and _keys_blocked(
                        keys, in_flight_concurrency_keys
                    ):
                        continue
                    in_flight_targets.add(key)
                    in_flight_concurrency_keys.update(keys)
                    fut = pool.submit(run_job, job)
                    future_to_context[fut] = (key, job, keys)
                    in_flight.add(fut)
                    scheduled = True
                if not scheduled:
                    break

            if not in_flight:
                break

            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                key, job, keys = future_to_context.pop(fut)
                in_flight_targets.discard(key)
                in_flight_concurrency_keys.difference_update(keys)
                result = fut.result()
                results.append(result)
                advance = on_complete(job, result) if on_complete else True
                if advance:
                    next_idx[key] += 1
                else:
                    next_idx[key] = len(grouped[key])

    return results
