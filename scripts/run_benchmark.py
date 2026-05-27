#!/usr/bin/env python3
"""Unified benchmark runner: opencode, codex, Claude Code CLI, or Cursor CLI."""

from __future__ import annotations

import argparse
import shutil
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.backends import LocalModelBackend, OllamaBackend, create_backend  # noqa: E402
from benchmark.config import (  # noqa: E402
    BenchmarkConfig,
    load_ollama_warmup_payload,
    load_opencode_ollama_api_base,
    resolve_build_harness_config,
)
from benchmark.harnesses import get_harness, list_harnesses  # noqa: E402
from benchmark.report import build_report, load_results  # noqa: E402
from benchmark.rate_limit import add_rate_limit_cli_args, rate_limit_policy_from_args  # noqa: E402
from benchmark.result_validation import (  # noqa: E402
    MAX_VALIDATION_RETRIES,
    followup_expected,
    validate_benchmark_result,
    validation_retryable,
    wipe_result_dir,
)
from benchmark.result_layout import target_dir as layout_target_dir  # noqa: E402
from benchmark.runner import _kill_stale_opencode_processes, run_model  # noqa: E402
from benchmark.util import (  # noqa: E402
    USAGE_LIMIT_REACHED,
    load_json,
    model_matches_harness,
    normalize_path_fields,
    print_line,
)

from benchmark.timeouts import (  # noqa: E402
    DEFAULT_NO_PROGRESS_MINUTES,
    DEFAULT_TIMEOUT_MINUTES,
)
HARNESS_CHOICES = frozenset(list_harnesses())


def _run_with_result_validation(
    slug: str,
    result_dir: Path,
    model: dict[str, Any],
    *,
    expect_followup: bool,
    max_retries: int,
    run_once: Callable[[], dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Run ``run_once`` up to ``max_retries + 1`` times until validation passes."""
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    last_payload: dict[str, Any] | None = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            if _previous_attempt_stalled(last_payload):
                print_line(
                    f"[{slug}] cooldown {STALL_RETRY_COOLDOWN_SECONDS}s before retry "
                    f"(prior attempt stalled)"
                )
                time.sleep(STALL_RETRY_COOLDOWN_SECONDS)
            print_line(
                f"[{slug}] validation retry {attempt}/{max_retries}: "
                f"wiping {result_dir}"
            )
            wipe_result_dir(result_dir)

        last_payload = run_once()
        if last_payload is None:
            return None
        if not validation_retryable(last_payload):
            return last_payload

        vr = validate_benchmark_result(
            result_dir,
            model=model,
            followup_expected_flag=expect_followup,
        )
        if vr.ok:
            if attempt > 0:
                print_line(f"[{slug}] validation passed after retry {attempt}")
            return last_payload

        print_line(f"[{slug}] validation failed: {vr.summary()}")
        for issue in vr.issues:
            print_line(f"  - {issue.code}: {issue.message}")

        if attempt >= max_retries:
            print_line(
                f"[{slug}] validation still failing after {max_retries} retries"
            )
            return last_payload

    return last_payload


def _benchmark_job_workers(total_models: int, jobs: int) -> int:
    """Cap thread-pool size for a model batch (``jobs=0`` => one worker per model)."""
    if total_models <= 0:
        return 1
    if jobs <= 0:
        return total_models
    return max(1, min(jobs, total_models))


def _needs_local_gpu_lock(models: list[dict[str, Any]]) -> bool:
    return any(m.get("provider") == "ollama" for m in models)


class _DispatchModelFn(Protocol):
    def __call__(
        self, model: dict[str, Any], index: int, *, skip_stale_kill: bool = False
    ) -> dict[str, Any] | None: ...


def _run_model_job_batch(
    *,
    job_items: list[tuple[int, dict[str, Any]]],
    workers: int,
    harness: str,
    abort_flag: threading.Event,
    local_gpu_lock: threading.Lock | None,
    dispatch_model: _DispatchModelFn,
) -> None:
    """Run all benchmark models with up to ``workers`` concurrent agent sessions.

  ``provider: ollama`` rows share ``local_gpu_lock`` so only one local model
  preflight/load runs at a time; other providers can run in parallel.
    """
    parallel = workers > 1 and len(job_items) > 1
    skip_stale_kill = parallel

    def _run_item(
        item: tuple[int, dict[str, Any]],
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        index, model = item
        slug = str(model["slug"])
        if abort_flag.is_set():
            print_line(f"[{slug}] skipped — usage limit active")
            return slug, None, None
        gpu_lock = local_gpu_lock if model.get("provider") == "ollama" else None
        acquired = False
        try:
            if gpu_lock is not None:
                gpu_lock.acquire()
                acquired = True
            payload = dispatch_model(model, index, skip_stale_kill=skip_stale_kill)
            if payload and _phase_hit_usage_limit(payload):
                abort_flag.set()
            return slug, payload, None
        except Exception:
            return slug, None, traceback.format_exc()
        finally:
            if acquired and gpu_lock is not None:
                gpu_lock.release()

    if parallel:
        if harness == "opencode":
            _kill_stale_opencode_processes()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run_item, item): item[1]["slug"] for item in job_items
            }
            for fut in as_completed(futures):
                slug, payload, err = fut.result()
                if err:
                    print_line(f"[{slug}] ERROR:\n{err}")
                elif payload is not None:
                    print_line(f"[{slug}] worker done")
    else:
        for item in job_items:
            slug, payload, err = _run_item(item)
            if err:
                print_line(f"[{slug}] ERROR:\n{err}")
            if payload and _phase_hit_usage_limit(payload):
                break


def _phase_hit_usage_limit(payload: dict[str, Any] | None) -> bool:
    """True when a benchmark result indicates provider quota / throttle exhaustion."""
    if not payload:
        return False
    if payload.get("status") == USAGE_LIMIT_REACHED:
        return True
    phases = payload.get("phases")
    if isinstance(phases, list):
        for ph in phases:
            if isinstance(ph, dict) and ph.get("status") == USAGE_LIMIT_REACHED:
                return True
    return False


STALL_RETRY_COOLDOWN_SECONDS = 60


def _previous_attempt_stalled(payload: dict[str, Any] | None) -> bool:
    """True when the prior run's payload (top-level or any phase) is marked stalled.

    Used to insert a short cooldown before the next retry — back-to-back retries
    against an upstream that just dropped a stream usually hit the same stuck
    path; a 60s breather lets the connection recover.
    """
    if not payload:
        return False
    if payload.get("stalled"):
        return True
    phases = payload.get("phases")
    if isinstance(phases, list):
        for ph in phases:
            if isinstance(ph, dict) and ph.get("stalled"):
                return True
    return False


def _cleanup_backends(
    backend: LocalModelBackend | None, local_api_base: str | None
) -> None:
    """Unload models from both Ollama and llama-swap to free GPU after the benchmark."""
    if backend is not None:
        active = backend.list_active()
        if active:
            print_line(
                f"Cleanup: unloading {backend.backend_name} models: {', '.join(active)}"
            )
            backend.unload_all()

    if backend is not None and not isinstance(backend, OllamaBackend):
        ollama_base = load_opencode_ollama_api_base()
        if ollama_base:
            ollama = OllamaBackend(ollama_base)
            active = ollama.list_active()
            if active:
                print_line(f"Cleanup: unloading Ollama models: {', '.join(active)}")
                ollama.unload_all()


def _default_config_path(harness: str) -> Path:
    return REPO_ROOT / "config" / "models.json"


def _default_report_path(harness: str) -> Path:
    if harness == "claude":
        return REPO_ROOT / "docs" / "report.claude-code.md"
    if harness == "cursor":
        return REPO_ROOT / "docs" / "report.cursor.md"
    if harness == "codex":
        return REPO_ROOT / "docs" / "report.codex.md"
    return REPO_ROOT / "docs" / "report.md"


_BENCHMARK_PATH_FIELDS = (
    "config",
    "followup_prompt",
    "ollama_warmup_results",
    "prompt",
    "report",
    "results_dir",
)


def _load_followup_prompt(followup_prompt_path: Path) -> str:
    """Load the mandatory phase-2 prompt; every benchmark run uses it."""
    if not followup_prompt_path.is_file():
        raise FileNotFoundError(
            f"Follow-up prompt not found: {followup_prompt_path}. "
            "Phase 2 is required for all models."
        )
    text = followup_prompt_path.read_text().strip()
    if not text:
        raise ValueError(f"Follow-up prompt is empty: {followup_prompt_path}")
    return text


def normalize_benchmark_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve CLI filesystem paths before runner dispatch.

    Example:
        ``--results-dir results`` becomes ``<repo>/results``.
    """
    return normalize_path_fields(args, REPO_ROOT, _BENCHMARK_PATH_FIELDS)


def _verify_codex_binaries(models: list[dict]) -> tuple[bool, str]:
    for m in models:
        cp = m.get("command_prefix") or []
        runner_type = m.get("runner_type", "opencode")
        uses_ollama_launch = (
            len(cp) >= 2 and cp[0] == "ollama" and cp[1] == "launch"
        ) or (runner_type == "ollama" and not cp)
        if uses_ollama_launch:
            if shutil.which("ollama") is None:
                return False, "ollama is not available on PATH (needed for ollama launch codex)"
        elif shutil.which("codex") is None:
            return False, "codex is not available on PATH"
    return True, ""


def _model_row_to_cli_variant(model: dict[str, Any]) -> dict[str, Any]:
    variant = dict(model)
    main_model = variant.get("main_model") or variant.get("id")
    if not isinstance(main_model, str) or not main_model:
        raise ValueError(
            f"model row {variant.get('slug')!r} needs string id or main_model"
        )
    variant["main_model"] = main_model
    return variant


def _ensure_cli_variant_config(config: dict[str, Any]) -> dict[str, Any]:
    variants = [_model_row_to_cli_variant(m) for m in config.get("models", [])]
    return {**config, "variants": variants}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified benchmark runner: opencode, codex, Claude Code, or Cursor CLI."
    )
    parser.add_argument(
        "--harness",
        required=True,
        choices=sorted(HARNESS_CHOICES),
        help="Which agent runner to use (results go under results/<harness>-<slug>/).",
    )
    parser.add_argument(
        "--models-config",
        dest="config",
        default=None,
        help="Path to models.json (shared model registry).",
    )
    parser.add_argument("--prompt", default="prompts/benchmark_prompt.txt")
    parser.add_argument(
        "--followup-prompt",
        default=str(REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"),
        help="Optional second-phase prompt.",
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument(
        "--report",
        default=None,
        help="Markdown report output path (default depends on --harness).",
    )
    parser.add_argument(
        "--ollama-warmup-results",
        default=str(REPO_ROOT / "results" / "ollama_warmup.json"),
    )
    parser.add_argument(
        "--timeout-minutes", type=int, default=DEFAULT_TIMEOUT_MINUTES
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=DEFAULT_NO_PROGRESS_MINUTES,
        help="Fail a run if stdout, stderr, and project files stay idle for this many minutes.",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Run only these model slug(s). Repeatable.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Cap how many models to execute this invocation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if a terminal result.json already exists.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip execution and only rebuild the report from saved result.json files.",
    )
    parser.add_argument(
        "--min-preview-output-tps",
        type=float,
        default=5.0,
        help="Abort a model early if preview output tok/s stays below this (opencode/codex).",
    )
    parser.add_argument(
        "--min-preview-samples",
        type=int,
        default=3,
        help="Samples before enforcing preview output tok/s threshold (opencode/codex).",
    )
    parser.add_argument(
        "--auto-skip-slow-preview",
        action="store_true",
        help="When preview tok/s fails, set skip_by_default in config (opencode/codex).",
    )
    parser.add_argument(
        "--local-backend",
        choices=["ollama", "llama-swap"],
        default="ollama",
        help="Backend for local model serving (opencode/codex).",
    )
    parser.add_argument(
        "--local-api-base",
        default=None,
        help="API base URL for the local backend (opencode/codex).",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=2,
        help="Max concurrent model runs (default: 2). Pass 1 for sequential. Pass 0 for "
        "one worker per selected model. Local GPU models (provider=ollama) share one "
        "lock so only one loads at a time; other models can run in parallel.",
    )
    parser.add_argument(
        "--max-validation-retries",
        type=int,
        default=MAX_VALIDATION_RETRIES,
        help=(
            "After a run, re-run from scratch when validation fails (wipes the result dir). "
            f"Default: {MAX_VALIDATION_RETRIES} retries ({MAX_VALIDATION_RETRIES + 1} attempts)."
        ),
    )
    parser.add_argument(
        "--no-result-validation",
        action="store_true",
        help="Skip post-run validation and automatic retries.",
    )
    add_rate_limit_cli_args(parser)
    args = parser.parse_args()
    if args.max_validation_retries < 0:
        parser.error("--max-validation-retries must be >= 0")
    if args.rate_limit_wait_cap_hours < 0:
        parser.error("--rate-limit-wait-cap-hours must be >= 0")
    if args.rate_limit_backoff_initial_seconds <= 0:
        parser.error("--rate-limit-backoff-initial-seconds must be > 0")
    if args.rate_limit_backoff_max_seconds < args.rate_limit_backoff_initial_seconds:
        parser.error(
            "--rate-limit-backoff-max-seconds must be >= "
            "--rate-limit-backoff-initial-seconds"
        )
    return args


def _run_model_harness(args: argparse.Namespace, harness: str) -> int:
    """Opencode or codex path (models.json-style config)."""
    config_path = Path(args.config)
    prompt_path = Path(args.prompt)
    followup_prompt_path = Path(args.followup_prompt)
    results_dir = Path(args.results_dir)
    report_path = Path(args.report)
    warmup_path = Path(args.ollama_warmup_results)

    config = load_json(config_path)
    config = resolve_build_harness_config(config, config_path, harness)
    prompt = prompt_path.read_text().strip()
    followup_prompt = _load_followup_prompt(followup_prompt_path)
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    selected_models = [
        m for m in config["models"] if not m.get("skip_by_default")
    ]
    selected_models = [
        m for m in selected_models if model_matches_harness(m, harness)
    ]

    slug_filter: set[str] = set()
    if args.models:
        slug_filter |= set(args.models)
    if slug_filter:
        registry_models = config.get("_registry_models", config["models"])
        by_slug = {m["slug"]: m for m in config["models"]}
        for s in sorted(slug_filter):
            if s not in by_slug:
                if any(m.get("slug") == s for m in registry_models):
                    print(
                        f"Slug `{s}` is not a {harness} model (check harness in config).",
                        file=sys.stderr,
                    )
                    return 1
                print(f"Unknown model slug: {s}", file=sys.stderr)
                return 1
            if not model_matches_harness(by_slug[s], harness):
                print(
                    f"Slug `{s}` is not a {harness} model (check runner_type in config).",
                    file=sys.stderr,
                )
                return 1
        selected_models = [m for m in selected_models if m["slug"] in slug_filter]

    if args.max_runs is not None:
        selected_models = selected_models[: args.max_runs]

    if not selected_models:
        print(
            f"No models selected for harness={harness!r}. Check runner_type in {config_path} "
            "or pass --model.",
            file=sys.stderr,
        )
        return 1

    warmup_payload = load_ollama_warmup_payload(warmup_path)

    if not args.report_only:
        if harness == "opencode" and shutil.which("opencode") is None:
            print("opencode is not available on PATH", file=sys.stderr)
            return 1
        if harness in {"codex", "ollama"}:
            ok, err = _verify_codex_binaries(selected_models)
            if not ok:
                print(err, file=sys.stderr)
                return 1

    api_base = args.local_api_base or load_opencode_ollama_api_base()
    backend = None
    has_local_models = any(m["provider"] == "ollama" for m in selected_models)
    if has_local_models and api_base:
        backend = create_backend(args.local_backend, api_base)
        print_line(f"Local backend: {backend.backend_name} at {api_base}")

    if not args.report_only:
        rate_limit_policy = rate_limit_policy_from_args(args)
        bench = BenchmarkConfig(
            runner=config["runner"],
            config_path=config_path,
            results_dir=results_dir,
            harness=harness,
            timeout_seconds=args.timeout_minutes * 60,
            no_progress_timeout_seconds=args.no_progress_minutes * 60,
            min_preview_output_tps=args.min_preview_output_tps,
            min_preview_samples=args.min_preview_samples,
            auto_skip_slow_preview=args.auto_skip_slow_preview,
            force=args.force,
            backend=backend,
            selected_models=selected_models,
            prompt=prompt,
            followup_prompt=followup_prompt,
            rate_limit_policy=rate_limit_policy,
        )

        abort_flag = threading.Event()

        total_models = len(selected_models)
        workers = _benchmark_job_workers(total_models, args.jobs)
        job_items = list(enumerate(selected_models, start=1))
        local_count = sum(1 for m in selected_models if m.get("provider") == "ollama")
        local_gpu_lock = (
            threading.Lock() if _needs_local_gpu_lock(selected_models) else None
        )
        print_line(
            f"Benchmark run starting ({harness}): models={total_models} "
            f"workers={workers} local_gpu={local_count} "
            f"timeout={bench.timeout_seconds}s "
            f"no_progress_timeout={bench.no_progress_timeout_seconds}s force={bench.force}"
        )

        validate_runs = not args.no_result_validation
        max_validation_retries = args.max_validation_retries

        def _dispatch_model(
            model: dict[str, Any], index: int, *, skip_stale_kill: bool = False
        ) -> dict[str, Any] | None:
            if not validate_runs:
                return run_model(
                    model,
                    bench,
                    index,
                    total_models,
                    skip_stale_kill=skip_stale_kill,
                )
            result_dir = layout_target_dir(
                bench.results_dir, bench.harness, model["slug"]
            )
            attempt = {"n": 0}

            def _run_once() -> dict[str, Any] | None:
                active_bench = (
                    replace(bench, force=True) if attempt["n"] > 0 else bench
                )
                attempt["n"] += 1
                return run_model(
                    model,
                    active_bench,
                    index,
                    total_models,
                    skip_stale_kill=skip_stale_kill,
                )

            expect_followup = followup_expected(followup_prompt=bench.followup_prompt)
            return _run_with_result_validation(
                model["slug"],
                result_dir,
                model,
                expect_followup=expect_followup,
                max_retries=max_validation_retries,
                run_once=_run_once,
            )

        if not abort_flag.is_set():
            _run_model_job_batch(
                job_items=job_items,
                workers=workers,
                harness=harness,
                abort_flag=abort_flag,
                local_gpu_lock=local_gpu_lock,
                dispatch_model=_dispatch_model,
            )

        _cleanup_backends(backend, args.local_api_base)

        if abort_flag.is_set():
            print_line(
                "Aborting: usage limit persisted after wait cap. "
                "Retry later or increase --rate-limit-wait-cap-hours."
            )
            return 1

    results = load_results(
        config, results_dir, warmup_payload, harness=harness
    )
    report_path.write_text(
        build_report(
            config,
            results,
            prompt,
            warmup_payload,
            warmup_path,
            harness=harness,
        )
    )
    completed = sum(1 for result in results if result["status"] != "not_run")
    print_line(f"Report updated: {report_path}")
    print_line(f"Progress snapshot: completed_or_attempted={completed}/{len(results)}")
    return 0


def _run_variant_harness(args: argparse.Namespace, harness_name: str) -> int:
    """Variant-driven benchmark for Claude Code and Cursor CLIs.

    Unified dispatch routed through the Harness registry. Adding a fifth
    variant-style harness is one ``register()`` call in
    ``benchmark.harnesses._adapters``, not a third copy of this function.
    """
    harness = get_harness(harness_name)
    config_path = Path(args.config)
    prompt_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    report_path = Path(args.report)

    config = load_json(config_path)
    config = resolve_build_harness_config(config, config_path, harness_name)
    config = _ensure_cli_variant_config(config)
    if "variants" not in config:
        print(
            f"Config {config_path} has no models for harness={harness_name!r}.",
            file=sys.stderr,
        )
        return 1

    prompt = prompt_path.read_text().strip()
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    all_variants = config["variants"]
    wanted: set[str] = set()
    if args.models:
        wanted |= set(args.models)
    if wanted:
        variants = [v for v in all_variants if v["slug"] in wanted]
        missing = wanted - {v["slug"] for v in variants}
        if missing:
            print(
                f"Unknown model slug(s): {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            return 1
    else:
        variants = [v for v in all_variants if not v.get("skip_by_default")]

    if args.max_runs is not None:
        print_line(
            f"Note: --max-runs applies only to opencode/codex; ignoring for {harness_name}."
        )

    if not args.report_only:
        if harness.cli_binary and shutil.which(harness.cli_binary) is None:
            print(harness.cli_install_hint or f"{harness.cli_binary} not on PATH",
                  file=sys.stderr)
            return 1
        print_line(
            f"Note: --harness {harness_name} uses {harness_name} runner semantics; "
            "opencode/codex-only flags "
            "(warmup, local backend, preview TPS gate, …) are ignored."
        )
        timeout_seconds = args.timeout_minutes * 60
        no_progress_timeout_seconds = args.no_progress_minutes * 60
        runner = config.get("runner") or {}
        runner_command_prefix = runner.get("command_prefix")
        isolate_home = bool(runner.get("isolate_home", False))
        jobs = args.jobs if args.jobs > 0 else len(variants)
        jobs = max(1, min(jobs, len(variants))) if variants else 1
        followup_text = _load_followup_prompt(Path(args.followup_prompt))
        extra_banner = (
            f", isolate_home={isolate_home}" if harness.accepts_isolate_home else ""
        )
        print_line(
            f"{harness_name} benchmark: {len(variants)} models, jobs={jobs}, "
            f"timeout={timeout_seconds}s{extra_banner}"
        )

        abort_flag = threading.Event()
        rate_limit_policy = rate_limit_policy_from_args(args)

        validate_runs = not args.no_result_validation
        max_validation_retries = args.max_validation_retries

        def _run(v: dict) -> tuple[str, dict | None, str | None]:
            if abort_flag.is_set():
                print_line(f"[{v['slug']}] skipped — usage limit active")
                return v["slug"], None, None
            try:
                result_dir = layout_target_dir(results_dir, harness_name, v["slug"])
                followup_for_variant = followup_text
                attempt = {"n": 0}

                def _run_once() -> dict[str, Any] | None:
                    run_kwargs: dict[str, Any] = dict(
                        variant=v,
                        prompt=prompt,
                        results_dir=results_dir,
                        timeout_seconds=timeout_seconds,
                        no_progress_timeout_seconds=no_progress_timeout_seconds,
                        force=args.force or attempt["n"] > 0,
                        runner_command_prefix=runner_command_prefix,
                        harness=harness_name,
                        followup_prompt=followup_for_variant,
                        rate_limit_policy=rate_limit_policy,
                    )
                    if harness.accepts_isolate_home:
                        run_kwargs["isolate_home"] = isolate_home
                    attempt["n"] += 1
                    return harness.run_variant(**run_kwargs)

                if validate_runs:
                    model_row = {
                        "slug": v["slug"],
                        "provider": v.get("provider", ""),
                    }
                    expect_followup = followup_expected(followup_prompt=followup_text)
                    payload = _run_with_result_validation(
                        v["slug"],
                        result_dir,
                        model_row,
                        expect_followup=expect_followup,
                        max_retries=max_validation_retries,
                        run_once=_run_once,
                    )
                else:
                    payload = _run_once()

                if payload and _phase_hit_usage_limit(payload):
                    abort_flag.set()
                return v["slug"], payload, None
            except Exception:
                return v["slug"], None, traceback.format_exc()

        if jobs == 1 or len(variants) <= 1:
            for v in variants:
                slug, _, err = _run(v)
                if err:
                    print_line(f"[{slug}] ERROR:\n{err}")
        else:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futures = {pool.submit(_run, v): v["slug"] for v in variants}
                for fut in as_completed(futures):
                    slug, payload, err = fut.result()
                    if err:
                        print_line(f"[{slug}] ERROR:\n{err}")
                    elif payload is not None:
                        print_line(f"[{slug}] worker done")

        if abort_flag.is_set():
            print_line(
                "Aborting: usage limit persisted after wait cap. "
                "Retry later or increase --rate-limit-wait-cap-hours."
            )
            return 1

    all_results = load_results(config, results_dir, harness=harness_name)
    report_path.write_text(build_report(config, all_results, harness=harness_name))
    print_line(f"Report updated: {report_path}")
    return 0


def main() -> int:
    args = parse_args()
    harness = args.harness

    if args.config is None:
        args.config = str(_default_config_path(harness))
    if args.report is None:
        args.report = str(_default_report_path(harness))

    args = normalize_benchmark_paths(args)

    if harness in {"opencode", "codex"}:
        return _run_model_harness(args, harness)
    if harness in {"claude", "cursor"}:
        return _run_variant_harness(args, harness)
    print(f"Unknown harness {harness!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
