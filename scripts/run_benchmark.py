#!/usr/bin/env python3
"""Unified benchmark runner: opencode, codex, or Claude Code CLI."""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.backends import LocalModelBackend, OllamaBackend, create_backend  # noqa: E402
from benchmark.claude_code_report import build_variant_report, load_variant_results  # noqa: E402
from benchmark.claude_code_runner import run_variant  # noqa: E402
from benchmark.config import (  # noqa: E402
    BenchmarkConfig,
    load_ollama_warmup_payload,
    load_opencode_ollama_api_base,
    print_local_opencode_config_summary,
    write_local_opencode_config,
)
from benchmark.report import build_report, load_results  # noqa: E402
from benchmark.runner import _kill_stale_opencode_processes, run_model  # noqa: E402
from benchmark.util import load_json, model_matches_harness, print_line  # noqa: E402

DEFAULT_NO_PROGRESS_MINUTES = 6
HARNESS_CHOICES = frozenset({"opencode", "codex", "claude", "ollama"})


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
    if harness == "claude":
        return REPO_ROOT / "config" / "claude_code_models.json"
    if harness == "ollama":
        return REPO_ROOT / "config" / "codex_ollama_cloud_models.json"
    return REPO_ROOT / "config" / "models.json"


def _default_report_path(harness: str) -> Path:
    if harness == "claude":
        return REPO_ROOT / "docs" / "report.claude-code.md"
    if harness == "codex":
        return REPO_ROOT / "docs" / "report.codex.md"
    if harness == "ollama":
        return REPO_ROOT / "docs" / "report.ollama.md"
    return REPO_ROOT / "docs" / "report.md"


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified benchmark runner: opencode, codex, or Claude Code CLI."
    )
    parser.add_argument(
        "--harness",
        required=True,
        choices=sorted(HARNESS_CHOICES),
        help="Which agent runner to use (results go under results/<harness>-<slug>/).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Benchmark JSON. Default: config/models.json (opencode/codex) or "
        "config/claude_code_models.json (claude).",
    )
    parser.add_argument(
        "--opencode-config",
        default=str(REPO_ROOT / "config" / "opencode.benchmark.json"),
    )
    parser.add_argument("--prompt", default="prompts/benchmark_prompt.txt")
    parser.add_argument(
        "--followup-prompt",
        default=str(REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"),
        help="Optional second-phase prompt (opencode/codex only).",
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
    parser.add_argument("--timeout-minutes", type=int, default=90)
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
        help="Run only these slug(s) (opencode/codex: model slug; claude: variant slug). Repeatable.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=None,
        help="(Claude) Same as --model — filter variants by slug. Repeatable.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Cap how many models to execute this invocation (opencode/codex).",
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
        "--sync-ollama-contexts-only",
        action="store_true",
        help="Write the local benchmark opencode config from warmup results and exit (opencode only).",
    )
    parser.add_argument(
        "--no-followup",
        action="store_true",
        help="Disable the second-phase follow-up prompt (opencode/codex).",
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
    opencode_config_path = Path(args.opencode_config)
    prompt_path = Path(args.prompt)
    followup_prompt_path = Path(args.followup_prompt)
    results_dir = Path(args.results_dir)
    report_path = Path(args.report)
    warmup_path = Path(args.ollama_warmup_results)

    if args.sync_ollama_contexts_only and harness != "opencode":
        print(
            "--sync-ollama-contexts-only is only valid with --harness opencode",
            file=sys.stderr,
        )
        return 1

    config = load_json(config_path)
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
    if args.variant:
        slug_filter |= set(args.variant)
    if slug_filter:
        by_slug = {m["slug"]: m for m in config["models"]}
        for s in sorted(slug_filter):
            if s not in by_slug:
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
            "or pass --model/--variant.",
            file=sys.stderr,
        )
        return 1

    warmup_payload = load_ollama_warmup_payload(warmup_path)

    if args.sync_ollama_contexts_only:
        config_summary = write_local_opencode_config(
            opencode_config_path,
            selected_models,
            warmup_payload,
            local_api_base=args.local_api_base,
            local_backend_type=args.local_backend,
        )
        print_local_opencode_config_summary(config_summary)
        return 0

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
        opencode_models = [
            m for m in selected_models if m.get("runner_type", "opencode") == "opencode"
        ]
        config_summary = write_local_opencode_config(
            opencode_config_path,
            opencode_models,
            warmup_payload,
            local_api_base=args.local_api_base,
            local_backend_type=args.local_backend,
        )
        print_local_opencode_config_summary(config_summary)
        opencode_override = opencode_config_path if config_summary.get("path") else None

        bench = BenchmarkConfig(
            runner=config["runner"],
            config_path=config_path,
            results_dir=results_dir,
            harness=harness,
            opencode_config_path=opencode_override,
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
            run_model(model, bench, index, total_models)

        cloud_workers = max(1, min(jobs, len(cloud_jobs))) if cloud_jobs else 1

        def _run_cloud_item(item: tuple[int, dict]) -> tuple[str, dict | None, str | None]:
            index, model = item
            try:
                payload = run_model(
                    model, bench, index, total_models, skip_stale_kill=True
                )
                return model["slug"], payload, None
            except Exception:
                return model["slug"], None, traceback.format_exc()

        if cloud_workers == 1 or len(cloud_jobs) <= 1:
            for index, model in cloud_jobs:
                run_model(model, bench, index, total_models)
        else:
            if harness == "opencode":
                _kill_stale_opencode_processes()
            with ThreadPoolExecutor(max_workers=cloud_workers) as pool:
                futures = {
                    pool.submit(_run_cloud_item, item): item[1]["slug"]
                    for item in cloud_jobs
                }
                for fut in as_completed(futures):
                    slug, _, err = fut.result()
                    if err:
                        print_line(f"[{slug}] ERROR:\n{err}")
                    else:
                        print_line(f"[{slug}] worker done")

        _cleanup_backends(backend, args.local_api_base)

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


def _run_claude_harness(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    prompt_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    report_path = Path(args.report)

    if args.sync_ollama_contexts_only:
        print(
            "--sync-ollama-contexts-only is only valid with --harness opencode",
            file=sys.stderr,
        )
        return 1

    config = load_json(config_path)
    if "variants" not in config:
        print(f"Config {config_path} has no 'variants' key (expected Claude variants).", file=sys.stderr)
        return 1

    prompt = prompt_path.read_text().strip()
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    all_variants = config["variants"]
    wanted: set[str] = set()
    if args.models:
        wanted |= set(args.models)
    if args.variant:
        wanted |= set(args.variant)
    if wanted:
        variants = [v for v in all_variants if v["slug"] in wanted]
        missing = wanted - {v["slug"] for v in variants}
        if missing:
            print(
                f"Unknown variant slug(s): {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            return 1
    else:
        variants = [v for v in all_variants if not v.get("skip_by_default")]

    if args.max_runs is not None:
        print_line("Note: --max-runs applies only to opencode/codex; ignoring for claude.")

    if not args.report_only:
        if shutil.which("claude") is None:
            print(
                "claude (Claude Code CLI) is not available on PATH",
                file=sys.stderr,
            )
            return 1
        print_line(
            "Note: --harness claude uses variants JSON only; opencode/codex-only CLI flags "
            "(warmup, local backend, preview TPS gate, follow-up, …) are ignored."
        )
        timeout_seconds = args.timeout_minutes * 60
        no_progress_timeout_seconds = args.no_progress_minutes * 60
        runner = config.get("runner") or {}
        runner_command_prefix = runner.get("command_prefix")
        isolate_home = bool(runner.get("isolate_home", False))
        jobs = args.jobs if args.jobs > 0 else len(variants)
        jobs = max(1, min(jobs, len(variants))) if variants else 1
        print_line(
            f"Claude Code benchmark: {len(variants)} variants, jobs={jobs}, "
            f"timeout={timeout_seconds}s, isolate_home={isolate_home}"
        )

        def _run(v: dict) -> tuple[str, dict | None, str | None]:
            try:
                payload = run_variant(
                    variant=v,
                    prompt=prompt,
                    results_dir=results_dir,
                    timeout_seconds=timeout_seconds,
                    no_progress_timeout_seconds=no_progress_timeout_seconds,
                    force=args.force,
                    runner_command_prefix=runner_command_prefix,
                    isolate_home=isolate_home,
                    harness="claude",
                )
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
                    slug, _, err = fut.result()
                    if err:
                        print_line(f"[{slug}] ERROR:\n{err}")
                    else:
                        print_line(f"[{slug}] worker done")

    all_results = load_variant_results(config, results_dir, harness="claude")
    report_path.write_text(build_variant_report(config, all_results))
    print_line(f"Report updated: {report_path}")
    return 0


def main() -> int:
    args = parse_args()
    harness = args.harness

    if args.config is None:
        args.config = str(_default_config_path(harness))
    if args.report is None:
        args.report = str(_default_report_path(harness))

    if harness in {"opencode", "codex", "ollama"}:
        return _run_model_harness(args, harness)
    if harness == "claude":
        return _run_claude_harness(args)
    print(f"Unknown harness {harness!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
