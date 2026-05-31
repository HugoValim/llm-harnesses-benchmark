"""Benchmark campaign dispatch helpers."""

from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Protocol

from benchmark.config import BenchmarkConfig
from benchmark.rate_limit import RateLimitWaitPolicy
from benchmark.replicates import model_num_runs, replicate_log_suffix, run_replicate_attempts
from benchmark.result_validation import (
    followup_expected,
    validate_benchmark_result,
    validation_retryable,
    wipe_result_dir,
)
from benchmark.result_layout import replicate_result_dir
from benchmark.runner import _kill_stale_opencode_processes, run_model
from benchmark.run_status import payload_hit_usage_limit, payload_was_stalled
from benchmark.util import print_line

STALL_RETRY_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class CampaignDispatchResult:
    """Summary from one benchmark campaign dispatch.

    Example:
        ``CampaignDispatchResult(usage_limit_aborted=False)`` means dispatch finished.
    """

    usage_limit_aborted: bool


class RunVariantFn(Protocol):
    """Callable shape for variant-style harness execution.

    Example:
        ``run_variant(variant=v, prompt=prompt, results_dir=results_dir)``.
    """

    def __call__(self, **kwargs: Any) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class VariantCampaignConfig:
    """Settings needed to dispatch a variant-style benchmark campaign.

    Example:
        ``VariantCampaignConfig(..., harness_name="claude", jobs=2)``.
    """

    variants: list[dict[str, Any]]
    jobs: int
    harness_name: str
    run_variant: RunVariantFn
    accepts_isolate_home: bool
    prompt: str
    results_dir: Path
    timeout_seconds: int
    no_progress_timeout_seconds: int
    force: bool
    runner_command_prefix: list[str] | None
    isolate_home: bool
    followup_prompt: str
    rate_limit_policy: RateLimitWaitPolicy
    validate_results: bool
    max_validation_retries: int
    include_agent_rules: bool = True


class DispatchModelFn(Protocol):
    """Callable used by campaign dispatch to run one model.

    Example:
        ``dispatch(model, 1, skip_stale_kill=True)`` returns a result payload.
    """

    def __call__(
        self, model: dict[str, Any], index: int, *, skip_stale_kill: bool = False
    ) -> dict[str, Any] | None: ...


class DispatchReplicateFn(Protocol):
    """Callable used by parallel dispatch to run one replicate attempt.

    Example:
        ``dispatch(model, 1, replicate_index=2, num_runs=3)`` returns a payload.
    """

    def __call__(
        self,
        model: dict[str, Any],
        index: int,
        replicate_index: int,
        num_runs: int,
        *,
        skip_stale_kill: bool = False,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ModelReplicateJob:
    """One parallel work item: a single replicate attempt for one model."""

    model_index: int
    model: dict[str, Any]
    replicate_index: int
    num_runs: int


@dataclass(frozen=True)
class VariantReplicateJob:
    """One parallel work item: a single replicate attempt for one variant."""

    variant: dict[str, Any]
    replicate_index: int
    num_runs: int


class RunModelFn(Protocol):
    """Callable shape for opencode/codex model execution.

    Example:
        ``run_model_fn(model, bench, 1, 3, replicate_index=1, num_runs=2)``.
    """

    def __call__(
        self,
        model: dict[str, Any],
        bench: BenchmarkConfig,
        index: int,
        total: int,
        *,
        skip_stale_kill: bool = False,
        replicate_index: int = 1,
        num_runs: int | None = None,
    ) -> dict[str, Any] | None: ...


def kill_stale_opencode_processes() -> None:
    """Remove stale opencode processes before a parallel opencode campaign.

    Example:
        ``kill_stale_opencode_processes()`` runs runner cleanup once.
    """
    _kill_stale_opencode_processes()


def benchmark_job_workers(total_models: int, jobs: int) -> int:
    """Return worker count for one benchmark campaign.

    Example:
        ``benchmark_job_workers(5, 0)`` returns ``5``.
    """
    if total_models <= 0:
        return 1
    if jobs <= 0:
        return total_models
    return max(1, min(jobs, total_models))


def expand_model_jobs_to_replicate_jobs(
    job_items: list[tuple[int, dict[str, Any]]],
) -> list[ModelReplicateJob]:
    """Expand model-level jobs into one queue item per replicate attempt."""
    expanded: list[ModelReplicateJob] = []
    for model_index, model in job_items:
        num_runs = model_num_runs(model)
        for replicate_index in range(1, num_runs + 1):
            expanded.append(
                ModelReplicateJob(
                    model_index=model_index,
                    model=model,
                    replicate_index=replicate_index,
                    num_runs=num_runs,
                )
            )
    return expanded


def expand_variants_to_replicate_jobs(
    variants: list[dict[str, Any]],
) -> list[VariantReplicateJob]:
    """Expand variant jobs into one queue item per replicate attempt."""
    expanded: list[VariantReplicateJob] = []
    for variant in variants:
        num_runs = model_num_runs(variant)
        for replicate_index in range(1, num_runs + 1):
            expanded.append(
                VariantReplicateJob(
                    variant=variant,
                    replicate_index=replicate_index,
                    num_runs=num_runs,
                )
            )
    return expanded


def needs_local_gpu_lock(models: list[dict[str, Any]]) -> bool:
    """True when selected campaign models include local Ollama.

    Example:
        ``needs_local_gpu_lock([{"provider": "ollama"}])`` returns ``True``.
    """
    return any(model.get("provider") == "ollama" for model in models)


def phase_hit_usage_limit(payload: dict[str, Any] | None) -> bool:
    """True when a result payload indicates provider quota exhaustion.

    Example:
        ``phase_hit_usage_limit({"status": "usage_limit_reached"})`` is ``True``.
    """
    return payload_hit_usage_limit(payload)


def run_model_job_batch(
    *,
    job_items: list[tuple[int, dict[str, Any]]],
    workers: int,
    harness: str,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_model: DispatchModelFn,
    dispatch_replicate: DispatchReplicateFn,
) -> None:
    """Run model jobs with local GPU serialization and usage-limit aborts.

    Parallel mode schedules individual replicate attempts so a finishing run
    immediately backfills a worker up to ``workers`` concurrent jobs.

    Example:
        ``run_model_job_batch(..., workers=2, harness="codex")`` runs up to two jobs.
    """
    parallel = workers > 1 and len(job_items) > 1
    skip_stale_kill = parallel
    if parallel:
        _run_parallel_model_jobs(
            job_items,
            workers,
            harness,
            abort_flag,
            local_gpu_lock,
            dispatch_replicate,
        )
        return
    _run_sequential_model_jobs(
        job_items, skip_stale_kill, abort_flag, local_gpu_lock, dispatch_model
    )


def run_model_campaign(
    bench: BenchmarkConfig,
    *,
    jobs: int,
    validate_results: bool,
    max_validation_retries: int,
    run_model_fn: RunModelFn = run_model,
) -> CampaignDispatchResult:
    """Dispatch all selected opencode/codex models for one campaign.

    Example:
        ``run_model_campaign(bench, jobs=2, validate_results=True, ...)``.
    """
    abort_flag = threading.Event()
    total_models = len(bench.selected_models)
    workers = benchmark_job_workers(total_models, jobs)
    local_gpu_lock = _local_gpu_lock_for(bench.selected_models)
    _print_model_campaign_start(bench, total_models, workers)
    run_model_job_batch(
        job_items=list(enumerate(bench.selected_models, start=1)),
        workers=workers,
        harness=bench.harness,
        abort_flag=abort_flag,
        local_gpu_lock=local_gpu_lock,
        dispatch_model=lambda model, index, skip_stale_kill=False: _run_model_replicates(
            model,
            bench,
            index,
            total_models,
            skip_stale_kill,
            validate_results,
            max_validation_retries,
            run_model_fn,
        ),
        dispatch_replicate=lambda model,
        index,
        replicate_index,
        num_runs,
        skip_stale_kill=False: _run_model_replicate(
            model,
            bench,
            index,
            total_models,
            skip_stale_kill,
            validate_results,
            max_validation_retries,
            run_model_fn,
            replicate_index,
            num_runs,
        ),
    )
    return CampaignDispatchResult(usage_limit_aborted=abort_flag.is_set())


def run_variant_campaign(config: VariantCampaignConfig) -> CampaignDispatchResult:
    """Dispatch all selected variant-style models for one campaign.

    Example:
        ``run_variant_campaign(config)`` runs Claude/Cursor variants.
    """
    abort_flag = threading.Event()
    jobs = benchmark_job_workers(len(config.variants), config.jobs)
    if jobs == 1 or len(config.variants) <= 1:
        _run_sequential_variant_jobs(config, abort_flag)
    else:
        _run_parallel_variant_jobs(config, jobs, abort_flag)
    return CampaignDispatchResult(usage_limit_aborted=abort_flag.is_set())


def run_with_result_validation(
    slug: str,
    result_dir: Path,
    model: dict[str, Any],
    *,
    expect_followup: bool,
    max_retries: int,
    run_once: Callable[[], dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Run one benchmark attempt until validation passes or retries are spent.

    Example:
        ``run_with_result_validation("m", result_dir, model, max_retries=1, ...)``.
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    last_payload: dict[str, Any] | None = None
    for attempt in range(max_retries + 1):
        _prepare_validation_retry(slug, result_dir, attempt, max_retries, last_payload)
        last_payload = run_once()
        if _validation_retry_should_stop(last_payload):
            return last_payload
        if _result_validation_passed(result_dir, model, expect_followup, attempt):
            return last_payload
        if attempt >= max_retries:
            print_line(f"[{slug}] validation still failing after {max_retries} retries")
            return last_payload
    return last_payload


def previous_attempt_stalled(payload: dict[str, Any] | None) -> bool:
    """True when a previous attempt payload reports a stalled run or phase.

    Example:
        ``previous_attempt_stalled({"stalled": True})`` returns ``True``.
    """
    return payload_was_stalled(payload)


def _local_gpu_lock_for(
    models: list[dict[str, Any]]
) -> threading.Lock | None:
    if needs_local_gpu_lock(models):
        return threading.Lock()
    return None


def _print_model_campaign_start(
    bench: BenchmarkConfig, total_models: int, workers: int
) -> None:
    local_count = sum(1 for model in bench.selected_models if model.get("provider") == "ollama")
    print_line(
        f"Benchmark run starting ({bench.harness}): models={total_models} "
        f"workers={workers} local_gpu={local_count} "
        f"timeout={bench.timeout_seconds}s "
        f"no_progress_timeout={bench.no_progress_timeout_seconds}s force={bench.force}"
    )


def _run_model_replicates(
    model: dict[str, Any],
    bench: BenchmarkConfig,
    index: int,
    total_models: int,
    skip_stale_kill: bool,
    validate_results: bool,
    max_validation_retries: int,
    run_model_fn: RunModelFn,
) -> dict[str, Any] | None:
    return run_replicate_attempts(
        model,
        lambda replicate_index, num_runs: _run_model_replicate(
            model,
            bench,
            index,
            total_models,
            skip_stale_kill,
            validate_results,
            max_validation_retries,
            run_model_fn,
            replicate_index,
            num_runs,
        ),
    )


def _run_model_replicate(
    model: dict[str, Any],
    bench: BenchmarkConfig,
    index: int,
    total_models: int,
    skip_stale_kill: bool,
    validate_results: bool,
    max_validation_retries: int,
    run_model_fn: RunModelFn,
    replicate_index: int,
    num_runs: int,
) -> dict[str, Any] | None:
    run_once = _model_replicate_attempt_fn(
        model, bench, index, total_models, skip_stale_kill, replicate_index, num_runs, run_model_fn
    )
    if not validate_results:
        return run_once()
    result_dir = replicate_result_dir(bench.results_dir, bench.harness, model["slug"], replicate_index)
    return run_with_result_validation(
        model["slug"],
        result_dir,
        model,
        expect_followup=followup_expected(followup_prompt=bench.followup_prompt),
        max_retries=max_validation_retries,
        run_once=run_once,
    )


def _model_replicate_attempt_fn(
    model: dict[str, Any],
    bench: BenchmarkConfig,
    index: int,
    total_models: int,
    skip_stale_kill: bool,
    replicate_index: int,
    num_runs: int,
    run_model_fn: RunModelFn,
) -> Callable[[], dict[str, Any] | None]:
    attempt_count = 0

    def _run_once() -> dict[str, Any] | None:
        nonlocal attempt_count
        active_bench = replace(bench, force=True) if attempt_count > 0 else bench
        attempt_count += 1
        return run_model_fn(
            model,
            active_bench,
            index,
            total_models,
            skip_stale_kill=skip_stale_kill,
            replicate_index=replicate_index,
            num_runs=num_runs,
        )

    return _run_once


def _run_sequential_variant_jobs(
    config: VariantCampaignConfig, abort_flag: threading.Event
) -> None:
    for variant in config.variants:
        slug, _, err = _run_variant_job(config, variant, abort_flag)
        if err:
            print_line(f"[{slug}] ERROR:\n{err}")


def _run_parallel_variant_jobs(
    config: VariantCampaignConfig, jobs: int, abort_flag: threading.Event
) -> None:
    replicate_jobs = expand_variants_to_replicate_jobs(config.variants)

    def run_job(job: VariantReplicateJob) -> tuple[str, dict[str, Any] | None, str | None]:
        return _run_variant_replicate_job(
            config,
            job.variant,
            job.replicate_index,
            job.num_runs,
            abort_flag,
        )

    _run_job_pool(replicate_jobs, jobs, run_job)


def _run_variant_replicate_job(
    config: VariantCampaignConfig,
    variant: dict[str, Any],
    replicate_index: int,
    num_runs: int,
    abort_flag: threading.Event,
) -> tuple[str, dict[str, Any] | None, str | None]:
    slug = str(variant["slug"])
    suffix = replicate_log_suffix(replicate_index, num_runs)
    if suffix:
        print_line(f"[{slug}] starting replicate{suffix}")
    if abort_flag.is_set():
        print_line(f"[{slug}] skipped - usage limit active")
        return slug, None, None
    try:
        payload = _run_variant_replicate(
            config, variant, replicate_index, num_runs
        )
        if phase_hit_usage_limit(payload):
            abort_flag.set()
        return slug, payload, None
    except Exception:
        return slug, None, traceback.format_exc()


def _run_variant_job(
    config: VariantCampaignConfig,
    variant: dict[str, Any],
    abort_flag: threading.Event,
) -> tuple[str, dict[str, Any] | None, str | None]:
    slug = str(variant["slug"])
    if abort_flag.is_set():
        print_line(f"[{slug}] skipped - usage limit active")
        return slug, None, None
    try:
        payload = run_replicate_attempts(
            variant,
            lambda replicate_index, num_runs: _run_variant_replicate(
                config, variant, replicate_index, num_runs
            ),
        )
        if phase_hit_usage_limit(payload):
            abort_flag.set()
        return slug, payload, None
    except Exception:
        return slug, None, traceback.format_exc()


def _run_variant_replicate(
    config: VariantCampaignConfig,
    variant: dict[str, Any],
    replicate_index: int,
    num_runs: int,
) -> dict[str, Any] | None:
    run_once = _variant_replicate_attempt_fn(
        config, variant, replicate_index, num_runs
    )
    if not config.validate_results:
        return run_once()
    result_dir = replicate_result_dir(
        config.results_dir, config.harness_name, variant["slug"], replicate_index
    )
    model_row = _variant_validation_model_row(variant, num_runs)
    return run_with_result_validation(
        variant["slug"],
        result_dir,
        model_row,
        expect_followup=followup_expected(followup_prompt=config.followup_prompt),
        max_retries=config.max_validation_retries,
        run_once=run_once,
    )


def _variant_replicate_attempt_fn(
    config: VariantCampaignConfig,
    variant: dict[str, Any],
    replicate_index: int,
    num_runs: int,
) -> Callable[[], dict[str, Any] | None]:
    attempt_count = 0

    def _run_once() -> dict[str, Any] | None:
        nonlocal attempt_count
        run_kwargs = _variant_run_kwargs(
            config, variant, replicate_index, num_runs, attempt_count
        )
        attempt_count += 1
        return config.run_variant(**run_kwargs)

    return _run_once


def _variant_run_kwargs(
    config: VariantCampaignConfig,
    variant: dict[str, Any],
    replicate_index: int,
    num_runs: int,
    attempt_count: int,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "variant": variant,
        "prompt": config.prompt,
        "results_dir": config.results_dir,
        "timeout_seconds": config.timeout_seconds,
        "no_progress_timeout_seconds": config.no_progress_timeout_seconds,
        "force": config.force or attempt_count > 0,
        "runner_command_prefix": config.runner_command_prefix,
        "harness": config.harness_name,
        "followup_prompt": config.followup_prompt,
        "rate_limit_policy": config.rate_limit_policy,
        "replicate_index": replicate_index,
        "num_runs": num_runs,
        "include_agent_rules": config.include_agent_rules,
    }
    if config.accepts_isolate_home:
        kwargs["isolate_home"] = config.isolate_home
    return kwargs


def _variant_validation_model_row(
    variant: dict[str, Any], num_runs: int
) -> dict[str, Any]:
    return {
        "slug": variant["slug"],
        "provider": variant.get("provider", ""),
        "num_runs": num_runs,
    }


def _prepare_validation_retry(
    slug: str,
    result_dir: Path,
    attempt: int,
    max_retries: int,
    last_payload: dict[str, Any] | None,
) -> None:
    if attempt == 0:
        return
    if previous_attempt_stalled(last_payload):
        print_line(
            f"[{slug}] cooldown {STALL_RETRY_COOLDOWN_SECONDS}s before retry "
            "(prior attempt stalled)"
        )
        time.sleep(STALL_RETRY_COOLDOWN_SECONDS)
    print_line(f"[{slug}] validation retry {attempt}/{max_retries}: wiping {result_dir}")
    wipe_result_dir(result_dir)


def _validation_retry_should_stop(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return True
    return not validation_retryable(payload)


def _result_validation_passed(
    result_dir: Path,
    model: dict[str, Any],
    expect_followup: bool,
    attempt: int,
) -> bool:
    result = validate_benchmark_result(
        result_dir,
        model=model,
        followup_expected_flag=expect_followup,
    )
    if result.ok:
        if attempt > 0:
            print_line(f"[{result.slug}] validation passed after retry {attempt}")
        return True
    _print_validation_failure(result.slug, result.summary(), result.issues)
    return False


def _print_validation_failure(slug: str, summary: str, issues: list[Any]) -> None:
    print_line(f"[{slug}] validation failed: {summary}")
    for issue in issues:
        print_line(f"  - {issue.code}: {issue.message}")


def _run_job_pool(
    jobs: list[Any],
    workers: int,
    run_job: Callable[[Any], tuple[str, dict[str, Any] | None, str | None]],
) -> None:
    """Keep up to ``workers`` replicate/model jobs running until the queue is empty."""
    if not jobs:
        return
    worker_count = benchmark_job_workers(len(jobs), workers)
    if worker_count == 1:
        for job in jobs:
            _print_model_job_result(*run_job(job))
        return

    pending: deque[Any] = deque(jobs)
    in_flight: set[Future[tuple[str, dict[str, Any] | None, str | None]]] = set()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        while pending or in_flight:
            while pending and len(in_flight) < worker_count:
                in_flight.add(pool.submit(run_job, pending.popleft()))

            if not in_flight:
                break

            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                _print_model_job_result(*fut.result())


def _run_parallel_model_jobs(
    job_items: list[tuple[int, dict[str, Any]]],
    workers: int,
    harness: str,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_replicate: DispatchReplicateFn,
) -> None:
    if harness == "opencode":
        kill_stale_opencode_processes()

    replicate_jobs = expand_model_jobs_to_replicate_jobs(job_items)

    def run_job(job: ModelReplicateJob) -> tuple[str, dict[str, Any] | None, str | None]:
        suffix = replicate_log_suffix(job.replicate_index, job.num_runs)
        if suffix:
            print_line(f"[{job.model['slug']}] starting replicate{suffix}")

        def dispatch_one(
            model: dict[str, Any], index: int, *, skip_stale_kill: bool = False
        ) -> dict[str, Any] | None:
            return dispatch_replicate(
                model,
                index,
                job.replicate_index,
                job.num_runs,
                skip_stale_kill=skip_stale_kill,
            )

        return _run_model_job_item(
            (job.model_index, job.model),
            True,
            abort_flag,
            local_gpu_lock,
            dispatch_one,
        )

    _run_job_pool(replicate_jobs, workers, run_job)


def _run_sequential_model_jobs(
    job_items: list[tuple[int, dict[str, Any]]],
    skip_stale_kill: bool,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_model: DispatchModelFn,
) -> None:
    for item in job_items:
        slug, payload, err = _run_model_job_item(
            item, skip_stale_kill, abort_flag, local_gpu_lock, dispatch_model
        )
        _print_model_job_result(slug, payload, err)
        if payload and phase_hit_usage_limit(payload):
            break


def _run_model_job_item(
    item: tuple[int, dict[str, Any]],
    skip_stale_kill: bool,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_model: DispatchModelFn,
) -> tuple[str, dict[str, Any] | None, str | None]:
    index, model = item
    slug = str(model["slug"])
    if abort_flag.is_set():
        print_line(f"[{slug}] skipped - usage limit active")
        return slug, None, None
    try:
        return _dispatch_model_job(
            model, index, skip_stale_kill, abort_flag, local_gpu_lock, dispatch_model
        )
    except Exception:
        return slug, None, traceback.format_exc()


def _dispatch_model_job(
    model: dict[str, Any],
    index: int,
    skip_stale_kill: bool,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_model: DispatchModelFn,
) -> tuple[str, dict[str, Any] | None, str | None]:
    gpu_lock = local_gpu_lock if model.get("provider") == "ollama" else None
    with _optional_lock(gpu_lock):
        payload = dispatch_model(model, index, skip_stale_kill=skip_stale_kill)
    if phase_hit_usage_limit(payload):
        abort_flag.set()
    return str(model["slug"]), payload, None


class _optional_lock:
    def __init__(self, lock: threading.Lock | None) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        if self._lock is not None:
            self._lock.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._lock is not None:
            self._lock.release()


def _print_model_job_result(
    slug: str, payload: dict[str, Any] | None, err: str | None
) -> None:
    if err:
        print_line(f"[{slug}] ERROR:\n{err}")
    elif payload is not None:
        print_line(f"[{slug}] worker done")
