"""Audit job dispatch lifecycle."""

from __future__ import annotations

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.audit_coverage import (
    audit_dispatch_needed,
    find_audit_coverage_gaps,
    format_coverage_gaps,
)
from benchmark.audit_preflight import format_audit_preflight_block
from benchmark.audit_finalize import ensure_audit_report, mark_audit_result_incomplete
from benchmark.config import display_slug_for
from benchmark.harnesses import canonical_harness_name, get_harness
from benchmark.pricing import (
    build_generation_metrics,
    format_generation_metrics_block,
    pricing_path,
    validate_section_h_cost,
)
from benchmark.rate_limit import RateLimitWaitPolicy
from benchmark.result_layout import (
    audit_generation_metrics_json,
    audit_report_md,
    audit_result_json,
    audit_stream_ndjson,
    audit_target_dir,
)
from benchmark.run_status import USAGE_LIMIT_REACHED
from benchmark.util import load_json, print_line, save_json


@dataclass(frozen=True)
class AuditDispatchConfig:
    """Inputs needed to dispatch one audit matrix."""

    results_dir: Path
    prompt_template: str
    timeout_seconds: int
    no_progress_timeout_seconds: int
    force: bool
    runner_command_prefix: list[str] | None
    rate_limit_policy: RateLimitWaitPolicy
    model_registry: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class AuditDispatchSummary:
    """Dispatch result for an audit job matrix."""

    failures: int


def build_audit_prompt(
    template: str,
    project_dir: Path,
    model_slug: str,
    output_path: Path | None = None,
    *,
    benchmark_result_path: Path | None = None,
    generation_metrics_path: Path | None = None,
    generation_metrics_block: str | None = None,
    pricing_doc_path: Path | None = None,
) -> str:
    """Interpolate placeholders into the audit prompt template."""
    prompt = template.replace("{project_dir}", str(project_dir.resolve()))
    prompt = prompt.replace("{model_slug}", model_slug)
    prompt = _replace_optional_path(prompt, "output_path", output_path)
    prompt = _replace_optional_path(
        prompt, "benchmark_result_path", benchmark_result_path
    )
    prompt = _replace_optional_path(
        prompt, "generation_metrics_path", generation_metrics_path
    )
    prompt = prompt.replace(
        "{generation_metrics_block}", generation_metrics_block or "n/a"
    )
    prompt = prompt.replace(
        "{audit_preflight_block}",
        format_audit_preflight_block(project_dir),
    )
    pricing_path_value = pricing_doc_path if pricing_doc_path else pricing_path()
    return prompt.replace("{pricing_doc_path}", str(pricing_path_value.resolve()))


def run_audit_jobs(
    *,
    auditors: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    jobs_count: int,
    config: AuditDispatchConfig,
) -> AuditDispatchSummary:
    """Run auditor-target jobs and return failure count."""
    jobs = [(auditor, target) for auditor in auditors for target in targets]
    logger = _AuditJobLogger()
    if jobs_count == 1 or len(jobs) <= 1:
        for auditor, target in jobs:
            logger.log(_run_audit_job(auditor, target, config))
        return AuditDispatchSummary(failures=logger.failures)
    with ThreadPoolExecutor(max_workers=jobs_count) as pool:
        futures = [pool.submit(_run_audit_job, a, t, config) for a, t in jobs]
        for future in as_completed(futures):
            logger.log(future.result())
    return AuditDispatchSummary(failures=logger.failures)


def coverage_failure_message(
    *,
    benchmark_results_dir: Path,
    audit_results_dir: Path,
    auditor_slugs: list[str],
    required_targets: list[dict[str, Any]],
) -> str:
    """Return formatted audit coverage gaps, or an empty string when complete."""
    gaps = find_audit_coverage_gaps(
        benchmark_results_dir=benchmark_results_dir,
        audit_results_dir=audit_results_dir,
        auditor_slugs=auditor_slugs,
        required_targets=required_targets,
    )
    return format_coverage_gaps(gaps)


def _run_audit_job(
    auditor: dict[str, Any],
    target: dict[str, Any],
    config: AuditDispatchConfig,
) -> tuple[str, str, str | None]:
    auditor_slug = auditor["slug"]
    target_slug = target["slug"]
    job_slug = f"{auditor_slug}__auditing__{target_slug}"
    try:
        return _dispatch_audit_job(auditor, target, config, job_slug)
    except Exception:
        return job_slug, "error", traceback.format_exc()


def _dispatch_audit_job(
    auditor: dict[str, Any],
    target: dict[str, Any],
    config: AuditDispatchConfig,
    job_slug: str,
) -> tuple[str, str, str | None]:
    auditor_slug = auditor["slug"]
    target_slug = target["slug"]
    result_dir = audit_target_dir(config.results_dir, auditor_slug, target_slug)
    result_dir.mkdir(parents=True, exist_ok=True)
    report_path = audit_report_md(config.results_dir, auditor_slug, target_slug)
    audit_result_path = audit_result_json(config.results_dir, auditor_slug, target_slug)
    if not _should_dispatch(report_path, audit_result_path, config.force, job_slug):
        return job_slug, "cached", None
    prompt, metrics = _prepare_audit_prompt(auditor, target, config, job_slug)
    (result_dir / "prompt.txt").write_text(prompt)
    run_result = _run_auditor(auditor, config, result_dir, prompt)
    if run_result.get("status") == USAGE_LIMIT_REACHED:
        return job_slug, USAGE_LIMIT_REACHED, None
    return _finalize_audit_job(
        job_slug, run_result, report_path, audit_result_path, config, auditor, target, metrics
    )


def _should_dispatch(
    report_path: Path,
    audit_result_path: Path,
    force: bool,
    job_slug: str,
) -> bool:
    should_dispatch = audit_dispatch_needed(
        report_path=report_path,
        audit_result_path=audit_result_path,
        force=force,
    )
    if not should_dispatch:
        print_line(f"[{job_slug}] complete report cached; skipping dispatch")
    return should_dispatch


def _prepare_audit_prompt(
    auditor: dict[str, Any],
    target: dict[str, Any],
    config: AuditDispatchConfig,
    job_slug: str,
) -> tuple[str, dict[str, Any]]:
    auditor_slug = auditor["slug"]
    target_slug = target["slug"]
    project_dir = target["project_dir"]
    model_slug = target.get("model_slug", target_slug)
    metrics = _write_generation_metrics(
        target=target,
        audit_results_dir=config.results_dir,
        auditor_slug=auditor_slug,
        target_slug=target_slug,
        force=config.force,
        job_slug=job_slug,
        model_registry=config.model_registry,
    )
    prompt = build_audit_prompt(
        config.prompt_template,
        project_dir,
        _display_slug(config.model_registry, model_slug),
        output_path=audit_report_md(config.results_dir, auditor_slug, target_slug),
        benchmark_result_path=project_dir.parent / "result.json",
        generation_metrics_path=audit_generation_metrics_json(
            config.results_dir, auditor_slug, target_slug
        ),
        generation_metrics_block=format_generation_metrics_block(metrics),
        pricing_doc_path=pricing_path(),
    )
    return prompt, metrics


def _write_generation_metrics(
    *,
    target: dict[str, Any],
    audit_results_dir: Path,
    auditor_slug: str,
    target_slug: str,
    force: bool,
    job_slug: str,
    model_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metrics_path = audit_generation_metrics_json(
        audit_results_dir, auditor_slug, target_slug
    )
    if metrics_path.exists() and not force:
        print_line(f"[{job_slug}] generation metrics cached -> {metrics_path}")
        return load_json(metrics_path)
    model_slug = target.get("model_slug", target_slug)
    metrics = build_generation_metrics(
        target_slug=target_slug,
        model_slug=model_slug,
        harness=target.get("harness", "unknown"),
        benchmark_result_path=target["project_dir"].parent / "result.json",
        provider=target.get("provider"),
    )
    metrics["display_model_slug"] = _display_slug(model_registry, model_slug)
    save_json(metrics_path, metrics)
    print_line(
        f"[{job_slug}] generation metrics status={metrics.get('status')} "
        f"cost={metrics.get('estimated_cost_usd')} -> {metrics_path}"
    )
    return metrics


def _run_auditor(
    auditor: dict[str, Any],
    config: AuditDispatchConfig,
    result_dir: Path,
    prompt: str,
) -> dict[str, Any]:
    runner_type = auditor.get("runner_type", "claude")
    harness = get_harness(canonical_harness_name(runner_type))
    run_kwargs: dict[str, Any] = {
        "variant": auditor,
        "prompt": prompt,
        "results_dir": config.results_dir / auditor["slug"],
        "timeout_seconds": config.timeout_seconds,
        "no_progress_timeout_seconds": config.no_progress_timeout_seconds,
        "force": True,
        "harness": runner_type,
        "explicit_result_dir": result_dir,
        "rate_limit_policy": config.rate_limit_policy,
        "elapsed_field": "elapsed_minutes",
    }
    if harness.accepts_runner_command_prefix:
        run_kwargs["runner_command_prefix"] = config.runner_command_prefix
    if runner_type in ("claude", "cursor"):
        run_kwargs["wrap_primary_prompt"] = False
        run_kwargs["for_benchmark_build"] = False
    return harness.run_variant(**run_kwargs)


def _finalize_audit_job(
    job_slug: str,
    run_result: dict[str, Any],
    report_path: Path,
    audit_result_path: Path,
    config: AuditDispatchConfig,
    auditor: dict[str, Any],
    target: dict[str, Any],
    metrics: dict[str, Any],
) -> tuple[str, str, str | None]:
    stream_path = audit_stream_ndjson(
        config.results_dir, auditor["slug"], target["slug"]
    )
    report_ok, report_reason = ensure_audit_report(
        report_path=report_path,
        stream_path=stream_path if stream_path.is_file() else None,
    )
    if not report_ok:
        mark_audit_result_incomplete(audit_result_path)
        harness_status = run_result.get("status", "unknown")
        return (
            job_slug,
            "incomplete_report",
            f"Auditor run finished (harness status={harness_status}) but {report_reason}. Re-run with --force.",
        )
    _warn_section_h_cost(job_slug, report_path, metrics)
    return job_slug, "ok", None


def _warn_section_h_cost(
    job_slug: str,
    report_path: Path,
    metrics: dict[str, Any],
) -> None:
    if not report_path.exists():
        return
    issues = validate_section_h_cost(report_path.read_text(encoding="utf-8"), metrics)
    for issue in issues:
        print_line(f"[{job_slug}] WARN section H: {issue}")


def _replace_optional_path(prompt: str, field: str, path: Path | None) -> str:
    value = str(path.resolve()) if path is not None else "n/a"
    return prompt.replace("{" + field + "}", value)


def _display_slug(model_registry: dict[str, dict[str, Any]], slug: str) -> str:
    return display_slug_for(model_registry, slug)


class _AuditJobLogger:
    def __init__(self) -> None:
        self.failures = 0

    def log(self, result: tuple[str, str, str | None]) -> None:
        job_slug, status, err = result
        if status in ("ok", "cached"):
            print_line(f"[{job_slug}] {status}")
            return
        self.failures += 1
        if status == "error" and err:
            print_line(f"[{job_slug}] ERROR:\n{err}")
            return
        if err:
            print(f"[{job_slug}] {status}: {err}", file=sys.stderr, flush=True)
            return
        print(f"[{job_slug}] {status}", file=sys.stderr, flush=True)
