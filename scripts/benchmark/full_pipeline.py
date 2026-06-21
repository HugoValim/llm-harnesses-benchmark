"""Full benchmark pipeline: build matrix, audit, and meta-analysis orchestration."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from benchmark.audit_meta import audit_model_harness
from benchmark.audit_layout import iter_auditor_report_paths
from benchmark.campaign_dispatch import kill_stale_opencode_processes
from benchmark.config import (
    _normalize_registry_models,
    existing_acceptable_result,
    registry_by_slug,
    registry_harness_values,
)
from benchmark.result_validation import followup_expected
from benchmark.defaults import DEFAULT_JOBS
from benchmark.docker_cleanup import prune_docker_after_benchmark
from benchmark.harnesses import dispatch_harness
from benchmark.job_pool import run_job_pool, run_target_pipelined_job_pool
from benchmark.replicates import expand_replicate_first, model_num_runs
from benchmark.result_layout import format_replicate_dir, replicate_result_dir
from benchmark.timeouts import meta_timeout_cli_flags, timeout_cli_flags
from benchmark.util import load_json, print_line

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

STALE_AUDIT_PROMPT_MARKER = "Prompt-Version: audit-v3.10"

_AUDIT_DISPATCH_HARNESSES = frozenset({"claude", "codex", "cursor"})


@dataclass(frozen=True)
class BuildStep:
    """One matrix row (harness + model)."""

    harness: str
    model_slug: str

    def key(self) -> tuple[str, str]:
        return (self.harness, self.model_slug)


@dataclass(frozen=True)
class BuildBatch:
    """One Phase 1 ``run_benchmark.py`` invocation (possibly many models)."""

    harness: str
    model_slugs: tuple[str, ...]


@dataclass(frozen=True)
class BuildJob:
    """One global pool work item: a single harness/model/replicate attempt."""

    harness: str
    model_slug: str
    replicate_index: int
    num_runs: int

    def label(self) -> str:
        """Stable log label for one build job."""
        replicate = format_replicate_dir(self.replicate_index)
        if self.num_runs <= 1:
            return f"{self.harness}:{self.model_slug}"
        return f"{self.harness}:{self.model_slug}/{replicate}"

    def target_key(self) -> tuple[str, str]:
        return (self.harness, self.model_slug)


def build_matrix(models_config_path: Path) -> list[BuildStep]:
    """Every registry model row expanded per harness entry."""
    config = load_json(models_config_path)
    registry = _normalize_registry_models(config.get("models"))
    if not registry and config.get("models") is not None:
        raise ValueError(f"{models_config_path} must contain a models array")

    steps: list[BuildStep] = []
    for model in registry:
        slug = model.get("slug")
        if not slug:
            continue
        for registry_harness in registry_harness_values(model):
            steps.append(
                BuildStep(dispatch_harness(registry_harness), str(slug))
            )
    return steps


def reject_forwarded_model_flag(extra_args: Sequence[str]) -> None:
    if "--model" in extra_args:
        raise SystemExit(
            "ERROR: Do not pass --model on the command line; "
            "the build matrix is defined in benchmark.full_pipeline.build_matrix()."
        )


def group_build_batches(steps: Sequence[BuildStep]) -> list[BuildBatch]:
    """Group matrix rows by harness so ``run_benchmark.py -j`` can parallelize."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for step in steps:
        if step.harness not in groups:
            groups[step.harness] = []
            order.append(step.harness)
        groups[step.harness].append(step.model_slug)
    return [
        BuildBatch(
            harness=harness,
            model_slugs=tuple(groups[harness]),
        )
        for harness in order
    ]


def _group_steps_by_harness(
    steps: Sequence[BuildStep],
) -> tuple[dict[str, list[BuildStep]], list[str]]:
    """Group matrix rows by harness while preserving first-seen harness order."""
    groups: dict[str, list[BuildStep]] = {}
    order: list[str] = []
    for step in steps:
        if step.harness not in groups:
            groups[step.harness] = []
            order.append(step.harness)
        groups[step.harness].append(step)
    return groups, order


def expand_build_matrix_to_jobs(
    steps: Sequence[BuildStep],
    *,
    models_config: Path,
) -> list[BuildJob]:
    """Return one job per configured (harness, model, replicate) leaf."""
    registry = registry_by_slug(
        _normalize_registry_models(load_json(models_config).get("models"))
    )
    groups, harness_order = _group_steps_by_harness(steps)
    jobs: list[BuildJob] = []
    for harness in harness_order:
        harness_steps = groups[harness]

        def num_runs_for_step(step: BuildStep) -> int:
            model_row = registry.get(step.model_slug, {})
            return model_num_runs(model_row) if model_row else 1

        for step, replicate_index, num_runs in expand_replicate_first(
            harness_steps,
            num_runs=num_runs_for_step,
        ):
            jobs.append(
                BuildJob(
                    harness=step.harness,
                    model_slug=step.model_slug,
                    replicate_index=replicate_index,
                    num_runs=num_runs,
                )
            )
    return jobs


def _build_extra_args(
    extra_args: Sequence[str],
    *,
    defer_docker_prune: bool,
) -> list[str]:
    args = list(extra_args)
    if defer_docker_prune and "--no-docker-prune" not in args:
        args.append("--no-docker-prune")
    return args


def build_job_argv(
    job: BuildJob,
    *,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    run_id: str | None = None,
) -> list[str]:
    """Argv for one single-replicate ``run_benchmark.py`` subprocess."""
    argv = [
        sys.executable,
        str(SCRIPTS_DIR / "run_benchmark.py"),
        "--harness",
        job.harness,
        "--models-config",
        str(models_config),
        *timeout_cli_flags(),
        "--model",
        job.model_slug,
        "--replicate-index",
        str(job.replicate_index),
        "-j",
        "1",
    ]
    if run_id:
        argv.extend(["--run-id", run_id])
    else:
        argv.extend(["--results-dir", str(results_dir)])
    if job.harness == "opencode":
        argv.append("--skip-stale-opencode-kill")
    argv.extend(extra_args)
    return argv


def execute_build_job(
    job: BuildJob,
    *,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    run_id: str | None = None,
    dry_run: bool = False,
    run_cmd: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> tuple[str, int]:
    """Run one build job subprocess; return ``(label, exit_code)``."""
    print_line(f"==> Phase 1 build: {job.label()}")
    cmd = build_job_argv(
        job,
        models_config=models_config,
        results_dir=results_dir,
        extra_args=extra_args,
        run_id=run_id,
    )
    if dry_run:
        print_line(" ".join(cmd))
        return job.label(), 0
    runner = run_cmd or subprocess.run
    completed = runner(cmd, cwd=REPO_ROOT, check=False, text=True)
    return job.label(), int(completed.returncode)


def dispatch_build_jobs(
    jobs: Sequence[BuildJob],
    *,
    workers: int,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    run_id: str | None = None,
    dry_run: bool = False,
    run_cmd: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[tuple[str, int]]:
    """Run build jobs through a global worker pool."""
    if dry_run:
        return [
            execute_build_job(
                job,
                models_config=models_config,
                results_dir=results_dir,
                extra_args=extra_args,
                run_id=run_id,
                dry_run=True,
                run_cmd=run_cmd,
            )
            for job in jobs
        ]

    def run_one(job: BuildJob) -> tuple[str, int]:
        return execute_build_job(
            job,
            models_config=models_config,
            results_dir=results_dir,
            extra_args=extra_args,
            run_id=run_id,
            dry_run=False,
            run_cmd=run_cmd,
        )

    return run_job_pool(list(jobs), workers, run_one)


def dispatch_build_jobs_by_replicate_wave(
    jobs: Sequence[BuildJob],
    *,
    workers: int,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    run_id: str | None = None,
    dry_run: bool = False,
    run_cmd: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[tuple[str, int]]:
    """Run build jobs in replicate waves so one target never overlaps replicates.

    Deprecated: default Phase 1 uses :func:`dispatch_build_jobs_pipelined` instead.
    """
    if not jobs:
        return []
    max_replicate = max(job.replicate_index for job in jobs)
    all_results: list[tuple[str, int]] = []
    for replicate_index in range(1, max_replicate + 1):
        wave = [job for job in jobs if job.replicate_index == replicate_index]
        if not wave:
            continue
        all_results.extend(
            dispatch_build_jobs(
                wave,
                workers=workers,
                models_config=models_config,
                results_dir=results_dir,
                extra_args=extra_args,
                run_id=run_id,
                dry_run=dry_run,
                run_cmd=run_cmd,
            )
        )
    return all_results


def _initial_replicate_index_for_target(
    target_jobs: Sequence[BuildJob],
    results_dir: Path,
    *,
    force: bool,
    model_row: dict[str, Any] | None = None,
    followup_expected_flag: bool = False,
) -> int:
    """Return the next job-list index for one target (skip validation-passed results)."""
    if force:
        return 0
    completed = 0
    for job in target_jobs:
        result_path = (
            replicate_result_dir(
                results_dir, job.harness, job.model_slug, job.replicate_index
            )
            / "result.json"
        )
        if existing_acceptable_result(
            result_path,
            model=model_row,
            followup_expected_flag=followup_expected_flag,
        ):
            completed += 1
        else:
            break
    return completed


def _group_build_jobs_by_target(
    jobs: Sequence[BuildJob],
) -> dict[tuple[str, str], list[BuildJob]]:
    grouped: dict[tuple[str, str], list[BuildJob]] = {}
    for job in jobs:
        key = job.target_key()
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(job)
    for target_jobs in grouped.values():
        target_jobs.sort(key=lambda j: j.replicate_index)
    return grouped


def dispatch_build_jobs_pipelined(
    jobs: Sequence[BuildJob],
    *,
    workers: int,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    run_id: str | None = None,
    dry_run: bool = False,
    run_cmd: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[tuple[str, int]]:
    """Run build jobs with per-target replicate pipelining and a global worker cap."""
    if not jobs:
        return []

    force = "--force" in extra_args
    models_payload = load_json(models_config)
    models_list = models_payload.get("models", [])
    registry = registry_by_slug(models_list if isinstance(models_list, list) else [])
    followup_prompt_path = REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"
    followup_prompt = (
        followup_prompt_path.read_text(encoding="utf-8").strip()
        if followup_prompt_path.is_file()
        else None
    )
    expect_followup = followup_expected(followup_prompt=followup_prompt)

    if any(job.harness == "opencode" for job in jobs):
        kill_stale_opencode_processes()

    opencode_lock = threading.Lock()

    def run_one(job: BuildJob) -> tuple[str, int]:
        if job.harness == "opencode":
            with opencode_lock:
                return execute_build_job(
                    job,
                    models_config=models_config,
                    results_dir=results_dir,
                    extra_args=extra_args,
                    run_id=run_id,
                    dry_run=dry_run,
                    run_cmd=run_cmd,
                )
        return execute_build_job(
            job,
            models_config=models_config,
            results_dir=results_dir,
            extra_args=extra_args,
            run_id=run_id,
            dry_run=dry_run,
            run_cmd=run_cmd,
        )

    grouped = _group_build_jobs_by_target(jobs)

    def initial_next_index(key: tuple[str, str]) -> int:
        harness, model_slug = key
        model_row = registry.get(model_slug, {"slug": model_slug, "harness": harness})
        return _initial_replicate_index_for_target(
            grouped[key],
            results_dir,
            force=force,
            model_row=model_row,
            followup_expected_flag=expect_followup,
        )

    def on_complete(_job: BuildJob, result: tuple[str, int]) -> bool:
        _label, exit_code = result
        return exit_code == 0

    return run_target_pipelined_job_pool(
        list(jobs),
        workers,
        run_one,
        target_key=lambda job: job.target_key(),
        replicate_index=lambda job: job.replicate_index,
        initial_next_index=initial_next_index,
        on_complete=on_complete,
    )


def _cleanup_docker_after_phase_build(extra_args: Sequence[str]) -> None:
    if "--no-docker-prune" in extra_args:
        return
    result = prune_docker_after_benchmark()
    if result.get("skipped"):
        print_line(f"Docker cleanup skipped: {result.get('reason', 'unknown')}")
        return
    for step in result.get("steps") or []:
        label = step.get("label", "docker")
        if step.get("ok"):
            reclaimed = step.get("reclaimed")
            suffix = f" ({reclaimed} reclaimed)" if reclaimed else ""
            print_line(f"Docker cleanup: {label} prune complete{suffix}")
        else:
            rc = step.get("returncode")
            err = step.get("stderr") or step.get("stdout") or "unknown error"
            print_line(f"Docker cleanup: {label} prune failed (exit {rc}): {err}")


def _raise_build_failures(results: list[tuple[str, int]]) -> None:
    failures = [label for label, exit_code in results if exit_code != 0]
    if failures:
        raise SystemExit(
            f"ERROR: build failed for job(s): {', '.join(failures)}"
        )


def build_benchmark_argv(
    batch: BuildBatch,
    *,
    models_config: Path,
    results_dir: Path,
    jobs: int,
    extra_args: Sequence[str],
    run_id: str | None = None,
) -> list[str]:
    """Argv for one Phase 1 ``run_benchmark.py`` subprocess."""
    if jobs < 1:
        raise ValueError(f"jobs must be >= 1 (got {jobs})")
    argv = [
        sys.executable,
        str(SCRIPTS_DIR / "run_benchmark.py"),
        "--harness",
        batch.harness,
        "--models-config",
        str(models_config),
        *timeout_cli_flags(),
    ]
    if run_id:
        argv.extend(["--run-id", run_id])
    else:
        argv.extend(["--results-dir", str(results_dir)])
    for slug in batch.model_slugs:
        argv.extend(["--model", slug])
    if "-j" not in extra_args and "--jobs" not in extra_args:
        argv.extend(["-j", str(jobs)])
    argv.extend(extra_args)
    return argv


def run_build_batch(
    batch: BuildBatch,
    *,
    models_config: Path,
    results_dir: Path,
    jobs: int,
    extra_args: Sequence[str],
    run_id: str | None = None,
    dry_run: bool = False,
) -> int:
    slugs = ", ".join(batch.model_slugs)
    print_line(
        f"==> Phase 1 build: harness={batch.harness} "
        f"models={len(batch.model_slugs)} ({slugs})"
    )
    cmd = build_benchmark_argv(
        batch,
        models_config=models_config,
        results_dir=results_dir,
        jobs=jobs,
        extra_args=extra_args,
        run_id=run_id,
    )
    if dry_run:
        print_line(" ".join(cmd))
        return 0
    completed = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return int(completed.returncode)


def phase_build(
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    *,
    jobs: int = DEFAULT_JOBS,
    run_id: str | None = None,
    dry_run: bool = False,
    sequential_build: bool = False,
) -> list[BuildStep]:
    steps = build_matrix(models_config)
    if sequential_build:
        batches = group_build_batches(steps)
        print_line(
            f"==> Phase 1 — build matrix ({len(steps)} models, "
            f"{len(batches)} harness batches, jobs={jobs}, sequential)"
        )
        for batch in batches:
            exit_code = run_build_batch(
                batch,
                models_config=models_config,
                results_dir=results_dir,
                jobs=jobs,
                extra_args=extra_args,
                run_id=run_id,
                dry_run=dry_run,
            )
            if exit_code != 0:
                raise SystemExit(
                    f"ERROR: build failed for harness={batch.harness!r} (exit {exit_code})"
                )
        return steps

    jobs_list = expand_build_matrix_to_jobs(steps, models_config=models_config)
    child_extra = _build_extra_args(extra_args, defer_docker_prune=True)
    print_line(
        f"==> Phase 1 — build matrix ({len(steps)} models, "
        f"{len(jobs_list)} jobs, pipelined replicates, global jobs={jobs})"
    )
    results = dispatch_build_jobs_pipelined(
        jobs_list,
        workers=jobs,
        models_config=models_config,
        results_dir=results_dir,
        extra_args=child_extra,
        run_id=run_id,
        dry_run=dry_run,
    )
    _raise_build_failures(results)
    if not dry_run:
        _cleanup_docker_after_phase_build(extra_args)
    return steps


def resolve_auditor_harness(
    harnesses_config: Path,
    models_config: Path,
    auditor_slug: str,
) -> str:
    """Return the audit dispatch harness for ``auditor_slug``."""
    harnesses = load_json(harnesses_config)
    registry = load_json(models_config)
    harness = audit_model_harness(harnesses, auditor_slug, models_config=registry)
    if harness not in _AUDIT_DISPATCH_HARNESSES:
        raise SystemExit(
            f"ERROR: auditor {auditor_slug!r} routes to harness={harness!r}; "
            f"full pipeline audit/meta supports only "
            f"{sorted(_AUDIT_DISPATCH_HARNESSES)}"
        )
    return harness


def resolve_meta_config(
    harnesses_config: Path,
    models_config: Path,
    auditor_slug: str,
    meta_auditor_slug: str | None,
    meta_harness: str | None,
    meta_input_dir: str | None,
) -> tuple[str, str, str, str]:
    """Return (auditor_harness, meta_auditor_slug, meta_harness, meta_input_dir)."""
    auditor_harness = resolve_auditor_harness(
        harnesses_config, models_config, auditor_slug
    )
    meta_slug = meta_auditor_slug or auditor_slug
    meta_input = meta_input_dir or auditor_slug
    harnesses = load_json(harnesses_config)
    registry = load_json(models_config)
    expected = audit_model_harness(harnesses, meta_slug, models_config=registry)

    resolved_harness = meta_harness or expected
    if resolved_harness != expected:
        raise SystemExit(
            f"ERROR: META_ANALYSIS_HARNESS={resolved_harness} but model {meta_slug} "
            f"defaults to harness={expected} in {harnesses_config}"
        )
    if resolved_harness not in _AUDIT_DISPATCH_HARNESSES:
        raise SystemExit(
            f"ERROR: META_ANALYSIS_HARNESS must be claude, codex, or cursor "
            f"(got {resolved_harness})"
        )

    print_line(
        f"Phase 2 auditor: {auditor_slug} harness={auditor_harness}"
    )
    print_line(
        f"Phase 3 meta: slug={meta_slug} harness={resolved_harness} "
        f"input={meta_input}"
    )
    return auditor_harness, meta_slug, resolved_harness, meta_input


def assert_no_stale_audit_reports(audit_reports_dir: Path, auditor_slug: str) -> None:
    auditor_dir = audit_reports_dir / auditor_slug
    if not auditor_dir.is_dir():
        return

    stale = [
        path
        for path in iter_auditor_report_paths(auditor_dir)
        if STALE_AUDIT_PROMPT_MARKER in path.read_text(encoding="utf-8", errors="replace")
    ]
    if not stale:
        return

    lines = "\n".join(str(p) for p in stale)
    raise SystemExit(
        f"ERROR: stale audit-v3.0 reports under {auditor_dir}:\n{lines}\n\n"
        "The meta-analysis meta-v3.1 excludes audit-v3.0 reports. Remove them "
        "and re-run."
    )


def phase_audit(
    models_config: Path,
    results_dir: Path,
    audit_reports_dir: Path,
    auditor_slug: str,
    auditor_harness: str,
    *,
    jobs: int = DEFAULT_JOBS,
    run_id: str | None = None,
    dry_run: bool = False,
) -> None:
    print_line("==> Phase 2 — audit (Role 1)")
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "run_audit.py"),
        "--models-config",
        str(models_config),
        "--harness",
        auditor_harness,
        "--model",
        auditor_slug,
        "--target",
        "all",
        "-j",
        str(jobs),
        *timeout_cli_flags(),
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])
    else:
        cmd.extend(
            [
                "--benchmark-results-dir",
                str(results_dir),
                "--results-dir",
                str(audit_reports_dir),
            ]
        )
    if dry_run:
        print_line(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def phase_meta_analysis(
    models_config: Path,
    audit_reports_dir: Path,
    meta_slug: str,
    meta_harness: str,
    meta_input_dir: str,
    *,
    run_id: str | None = None,
    meta_output_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    print_line("==> Phase 3 — meta-analysis (Role 2)")
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "run_meta_analysis.py"),
        *meta_timeout_cli_flags(),
        "--models-config",
        str(models_config),
        "--harness",
        meta_harness,
        "--model",
        meta_slug,
        "--meta-input-dir",
        meta_input_dir,
        "--force",
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])
    else:
        cmd.extend(["--results-dir", str(audit_reports_dir)])
    if meta_output_dir is not None:
        cmd.extend(["--meta-output-dir", str(meta_output_dir)])
    if dry_run:
        print_line(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)
