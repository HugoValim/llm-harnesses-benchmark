#!/usr/bin/env python3
"""Unified benchmark runner: opencode, codex, Claude Code CLI, or Cursor CLI."""

from __future__ import annotations

import argparse
import shutil
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

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
        "--no-followup",
        action="store_true",
        help="Disable the second-phase follow-up prompt.",
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
        default=1,
        help="Concurrency across model runs (default: one worker per slug). Pass an integer N "
        "to cap to N concurrent runs, or 1 to force sequential. Local-served (provider=ollama) "
        "models always run sequentially regardless of this flag.",
    )
    return parser.parse_args()


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
    followup_prompt = None
    if not args.no_followup and followup_prompt_path.exists():
        followup_prompt = followup_prompt_path.read_text().strip()
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
        )

        abort_flag = threading.Event()

        total_models = len(selected_models)
        jobs = args.jobs if args.jobs > 0 else total_models
        jobs = max(1, min(jobs, total_models)) if total_models else 1
        local_jobs = [
            (i, m)
            for i, m in enumerate(selected_models, start=1)
            if m["provider"] == "ollama"
        ]
        cloud_jobs = [
            (i, m)
            for i, m in enumerate(selected_models, start=1)
            if m["provider"] != "ollama"
        ]
        print_line(
            f"Benchmark run starting ({harness}): models={total_models} "
            f"jobs={jobs} (cloud={len(cloud_jobs)} local={len(local_jobs)}) "
            f"timeout={bench.timeout_seconds}s "
            f"no_progress_timeout={bench.no_progress_timeout_seconds}s force={bench.force}"
        )

        for index, model in local_jobs:
            result_payload = run_model(model, bench, index, total_models)
            if _phase_hit_usage_limit(result_payload):
                abort_flag.set()
                break

        cloud_workers = max(1, min(jobs, len(cloud_jobs))) if cloud_jobs else 1

        def _run_cloud_item(item: tuple[int, dict]) -> tuple[str, dict | None, str | None]:
            index, model = item
            if abort_flag.is_set():
                print_line(f"[{model['slug']}] skipped — usage limit active")
                return model["slug"], None, None
            try:
                payload = run_model(
                    model, bench, index, total_models, skip_stale_kill=True
                )
                if _phase_hit_usage_limit(payload):
                    abort_flag.set()
                return model["slug"], payload, None
            except Exception:
                return model["slug"], None, traceback.format_exc()

        if not abort_flag.is_set():
            if cloud_workers == 1 or len(cloud_jobs) <= 1:
                for index, model in cloud_jobs:
                    result_payload = run_model(
                        model, bench, index, total_models
                    )
                    if _phase_hit_usage_limit(result_payload):
                        abort_flag.set()
                        break
            else:
                if harness == "opencode":
                    _kill_stale_opencode_processes()
                with ThreadPoolExecutor(max_workers=cloud_workers) as pool:
                    futures = {
                        pool.submit(_run_cloud_item, item): item[1]["slug"]
                        for item in cloud_jobs
                    }
                    for fut in as_completed(futures):
                        slug, payload, err = fut.result()
                        if err:
                            print_line(f"[{slug}] ERROR:\n{err}")
                        elif payload is not None:
                            print_line(f"[{slug}] worker done")

        _cleanup_backends(backend, args.local_api_base)

        if abort_flag.is_set():
            print_line(
                "Aborting: usage limit reached. Retry after limit resets."
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
        followup_path = Path(args.followup_prompt)
        followup_text = (
            followup_path.read_text().strip() if followup_path.exists() else None
        )
        extra_banner = (
            f", isolate_home={isolate_home}" if harness.accepts_isolate_home else ""
        )
        print_line(
            f"{harness_name} benchmark: {len(variants)} models, jobs={jobs}, "
            f"timeout={timeout_seconds}s{extra_banner}"
        )

        def _variant_enables_followup(v: dict) -> bool:
            return bool(v.get("enable_followup", False))

        abort_flag = threading.Event()

        def _run(v: dict) -> tuple[str, dict | None, str | None]:
            if abort_flag.is_set():
                print_line(f"[{v['slug']}] skipped — usage limit active")
                return v["slug"], None, None
            try:
                run_kwargs: dict[str, Any] = dict(
                    variant=v,
                    prompt=prompt,
                    results_dir=results_dir,
                    timeout_seconds=timeout_seconds,
                    no_progress_timeout_seconds=no_progress_timeout_seconds,
                    force=args.force,
                    runner_command_prefix=runner_command_prefix,
                    harness=harness_name,
                    followup_prompt=(
                        followup_text if _variant_enables_followup(v) else None
                    ),
                )
                if harness.accepts_isolate_home:
                    run_kwargs["isolate_home"] = isolate_home
                payload = harness.run_variant(**run_kwargs)
                if _phase_hit_usage_limit(payload):
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
                "Aborting: usage limit reached. Retry after limit resets."
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
