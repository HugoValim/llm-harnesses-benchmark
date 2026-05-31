#!/usr/bin/env python3
"""Unified benchmark runner: opencode, codex, Claude Code CLI, or Cursor CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.backends import LocalModelBackend, OllamaBackend, create_backend  # noqa: E402
from benchmark.campaign_dispatch import (  # noqa: E402
    VariantCampaignConfig,
    run_model_campaign,
    run_variant_campaign,
)
from benchmark.docker_cleanup import prune_docker_after_benchmark  # noqa: E402
from benchmark.config import (  # noqa: E402
    BenchmarkConfig,
    load_opencode_ollama_api_base,
    resolve_build_harness_config,
)
from benchmark.harnesses import (  # noqa: E402
    check_harness_cli_requirements,
    get_harness,
    list_harnesses,
    model_matches_harness,
)
from benchmark.rate_limit import add_rate_limit_cli_args, rate_limit_policy_from_args  # noqa: E402
from benchmark.result_validation import MAX_VALIDATION_RETRIES  # noqa: E402
from benchmark.result_layout import (  # noqa: E402
    add_run_id_arg,
    layout_from_repo,
)
from benchmark.util import (  # noqa: E402
    load_json,
    normalize_path_fields,
    print_line,
)

from benchmark.defaults import DEFAULT_JOBS  # noqa: E402
from benchmark.timeouts import (  # noqa: E402
    DEFAULT_NO_PROGRESS_MINUTES,
    DEFAULT_TIMEOUT_MINUTES,
)
HARNESS_CHOICES = frozenset(list_harnesses())


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


def _cleanup_docker_after_benchmark(args: argparse.Namespace) -> None:
    """Reclaim Docker build cache and unused images after a benchmark batch."""
    if args.no_docker_prune:
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


def _default_config_path(harness: str) -> Path:
    return REPO_ROOT / "config" / "models.json"


_BENCHMARK_PATH_FIELDS = (
    "config",
    "followup_prompt",
    "ollama_warmup_results",
    "prompt",
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
        ``--run-id run_02`` sets ``results_dir`` to ``<repo>/results/run_02/projects``.
    """
    args = normalize_path_fields(args, REPO_ROOT, _BENCHMARK_PATH_FIELDS)
    if args.run_id:
        layout = layout_from_repo(args.run_id, REPO_ROOT)
        args.results_dir = str(layout.projects_root)
        args.ollama_warmup_results = str(layout.ollama_warmup_json)
        layout.projects_root.mkdir(parents=True, exist_ok=True)
        layout.run_root.mkdir(parents=True, exist_ok=True)
    return args


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
        help=(
            "Which agent runner to use (results go under "
            "results/<run_id>/projects/<harness>-<slug>/ with --run-id)."
        ),
    )
    add_run_id_arg(parser)
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
        "--replicate-index",
        type=int,
        default=None,
        help="Run only this 1-based replicate attempt (run_01, run_02, …).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if a terminal result.json already exists.",
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
        default=DEFAULT_JOBS,
        help=f"Max concurrent model runs (default: {DEFAULT_JOBS}). Pass 1 for sequential. Pass 0 for "
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
    parser.add_argument(
        "--no-docker-prune",
        action="store_true",
        help="Skip post-run docker builder/system prune (default: prune after a run batch).",
    )
    parser.add_argument(
        "--no-agent-coding-rules",
        action="store_true",
        help="Omit prompts/agent_coding_rules.md from project CLAUDE.md/AGENTS.md.",
    )
    add_rate_limit_cli_args(parser)
    args = parser.parse_args()
    if args.max_validation_retries < 0:
        parser.error("--max-validation-retries must be >= 0")
    if args.replicate_index is not None and args.replicate_index < 1:
        parser.error("--replicate-index must be >= 1")
    if args.rate_limit_wait_cap_hours < 0:
        parser.error("--rate-limit-wait-cap-hours must be >= 0")
    if args.rate_limit_backoff_initial_seconds <= 0:
        parser.error("--rate-limit-backoff-initial-seconds must be > 0")
    if args.rate_limit_backoff_max_seconds < args.rate_limit_backoff_initial_seconds:
        parser.error(
            "--rate-limit-backoff-max-seconds must be >= "
            "--rate-limit-backoff-initial-seconds"
        )
    if args.rate_limit_poll_interval_seconds <= 0:
        parser.error("--rate-limit-poll-interval-seconds must be > 0")
    return args


def _run_model_harness(args: argparse.Namespace, harness: str) -> int:
    """Opencode or codex path (models.json-style config)."""
    config_path = Path(args.config)
    prompt_path = Path(args.prompt)
    followup_prompt_path = Path(args.followup_prompt)
    results_dir = Path(args.results_dir)

    config = load_json(config_path)
    config = resolve_build_harness_config(config, config_path, harness)
    prompt = prompt_path.read_text().strip()
    followup_prompt = _load_followup_prompt(followup_prompt_path)
    results_dir.mkdir(parents=True, exist_ok=True)

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

    ok, err = check_harness_cli_requirements(harness, selected_models)
    if not ok:
        print(err, file=sys.stderr)
        return 1

    api_base = args.local_api_base or load_opencode_ollama_api_base()
    backend = None
    has_local_models = any(m["provider"] == "ollama" for m in selected_models)
    if has_local_models and api_base:
        backend = create_backend(args.local_backend, api_base)
        print_line(f"Local backend: {backend.backend_name} at {api_base}")

    rate_limit_policy = rate_limit_policy_from_args(args)
    include_agent_rules = not args.no_agent_coding_rules
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
        include_agent_rules=include_agent_rules,
        rate_limit_policy=rate_limit_policy,
        replicate_index=args.replicate_index,
    )

    dispatch_result = run_model_campaign(
        bench,
        jobs=args.jobs,
        validate_results=not args.no_result_validation,
        max_validation_retries=args.max_validation_retries,
    )
    _cleanup_backends(backend, args.local_api_base)
    _cleanup_docker_after_benchmark(args)

    if dispatch_result.usage_limit_aborted:
        print_line(
            "Aborting: usage limit persisted after wait cap. "
            "Retry later or increase --rate-limit-wait-cap-hours."
        )
        return 1

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

    ok, err = check_harness_cli_requirements(harness_name)
    if not ok:
        print(err, file=sys.stderr)
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

    rate_limit_policy = rate_limit_policy_from_args(args)
    include_agent_rules = not args.no_agent_coding_rules
    dispatch_result = run_variant_campaign(
        VariantCampaignConfig(
            variants=variants,
            jobs=jobs,
            harness_name=harness_name,
            run_variant=harness.run_variant,
            accepts_isolate_home=harness.accepts_isolate_home,
            prompt=prompt,
            results_dir=results_dir,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            force=args.force,
            runner_command_prefix=runner_command_prefix,
            isolate_home=isolate_home,
            followup_prompt=followup_text,
            include_agent_rules=include_agent_rules,
            rate_limit_policy=rate_limit_policy,
            validate_results=not args.no_result_validation,
            max_validation_retries=args.max_validation_retries,
            replicate_index=args.replicate_index,
        )
    )

    _cleanup_docker_after_benchmark(args)

    if dispatch_result.usage_limit_aborted:
        print_line(
            "Aborting: usage limit persisted after wait cap. "
            "Retry later or increase --rate-limit-wait-cap-hours."
        )
        return 1

    return 0


def main() -> int:
    args = parse_args()
    harness = args.harness

    if args.config is None:
        args.config = str(_default_config_path(harness))

    args = normalize_benchmark_paths(args)

    if harness in {"opencode", "codex"}:
        return _run_model_harness(args, harness)
    if harness in {"claude", "cursor"}:
        return _run_variant_harness(args, harness)
    print(f"Unknown harness {harness!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
