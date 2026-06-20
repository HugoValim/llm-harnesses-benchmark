#!/usr/bin/env python3
"""Role 1: per-project AI audit dispatch.

Reads benchmark outputs under ``results/<run_id>/projects/<harness>-<slug>/project``
(or legacy ``results/<harness>-<slug>/project``) and dispatches an LLM auditor
registry row against each, using the rubric template at
``prompts/audit_prompt_template.txt``. Audit outputs land in
``results/<run_id>/audit-reports/<auditor_slug>/<target_slug>/`` (one
``report.md`` per (auditor, target) pair).

After dispatch, rebuilds ``audit-reports/<auditor_slug>/comparison.md`` per
auditor from that auditor's ``report.md`` files via
:func:`benchmark.audit_report.build_comparison_table` and
:func:`build_statistical_summary`.

This script is the per-project leg of the audit pipeline. The cross-auditor
meta-analysis is its own entry point: ``scripts/run_meta_analysis.py``.

Auth:
  - Anthropic auditors use Claude subscription auth (``claude login``).
  - Non-Anthropic auditors are routed via ``ollama launch claude --model <tag>``
    using the row's ``command_prefix`` field in config/models.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_layout import (  # noqa: E402
    auditor_dir_has_reports,
    iter_auditor_report_paths,
)
from benchmark.audit_report import (  # noqa: E402
    build_comparison_table,
    build_statistical_summary,
    load_rubric_result,
)
from benchmark.audit_rollup import saturated_dimension_warnings  # noqa: E402
from benchmark.harnesses import check_harness_cli_requirements  # noqa: E402
from benchmark.audit_dispatch import (  # noqa: E402
    AuditDispatchConfig,
    build_audit_prompt,
    coverage_failure_message,
    run_audit_jobs,
)
from benchmark.audit_meta import discover_auditor_subdirs  # noqa: E402
from benchmark.timeouts import (  # noqa: E402
    DEFAULT_NO_PROGRESS_MINUTES,
    DEFAULT_TIMEOUT_MINUTES,
)
from benchmark.config import (  # noqa: E402
    build_display_slug_map,
    registry_by_slug,
    resolve_audit_harness_config,
)
from benchmark.defaults import DEFAULT_AUDITOR_SLUG, DEFAULT_AUDIT_HARNESS, DEFAULT_JOBS  # noqa: E402
from benchmark.rate_limit import add_rate_limit_cli_args, rate_limit_policy_from_args  # noqa: E402

# Runner imports go through the Harness registry; no direct imports needed.
from benchmark.util import (  # noqa: E402
    load_json,
    normalize_path_fields,
    print_line,
)


def _verify_auditor_binaries(auditors: list[dict]) -> tuple[bool, str]:
    """Check PATH binaries required by selected auditor harnesses."""
    for auditor in auditors:
        runner_type = auditor.get("runner_type", "claude")
        ok, err = check_harness_cli_requirements(runner_type, [auditor])
        if not ok:
            return ok, err
    return True, ""


# Config paths ----------------------------------------------------------------
AUDIT_CONFIG_PATH = REPO_ROOT / "config" / "models.json"
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "models.json"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_prompt_template.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"
DEFAULT_BENCHMARK_RESULTS_DIR = REPO_ROOT / "results"


from benchmark.result_layout import (  # noqa: E402
    add_run_id_arg,
    audit_report_md,
    benchmark_target_slug_from_leaf,
    discover_benchmark_target_dirs,
    layout_from_repo,
    parse_benchmark_target_path,
)


def discover_project_dirs(
    benchmark_results_dir: Path,
    config_targets_by_slug: dict[str, dict] | None = None,
) -> list[dict]:
    """Scan ``benchmark_results_dir`` for every ``<name>/project`` subdir.

    This is the authoritative audit target set: ``run_audit.py`` audits every
    discovered row by default and exits non-zero when any lack a scored
    ``report.md`` (see ``--no-enforce-coverage``).

    Returns one target dict per discovered project, sorted by dir name:

    - ``slug``: the directory name (e.g. ``claude-kimi_k2_6_ollama_cloud``).
      Used as the audit output dir name; unique by construction.
    - ``model_slug``: the slug with the harness prefix stripped, or the dir
      name itself when no harness prefix is recognised.
    - ``harness``: ``"claude" | "cursor" | "codex" | "ollama" | "opencode" | "unknown"``.
    - ``project_dir``: absolute Path to ``<name>/project``.
    - ``label`` / ``main_model`` / ``selection_reason`` from
      ``config_targets_by_slug[model_slug]`` when available (optional metadata).
    """
    config_targets_by_slug = config_targets_by_slug or {}
    out: list[dict] = []
    for entry in discover_benchmark_target_dirs(benchmark_results_dir):
        project_dir = entry / "project"
        slug = benchmark_target_slug_from_leaf(entry, benchmark_results_dir)
        parsed = parse_benchmark_target_path(slug)
        harness = parsed.harness or "unknown"
        target: dict = {
            "slug": slug,
            "target_group": parsed.target_group,
            "replicate_id": parsed.replicate_id,
            "model_slug": parsed.model_slug,
            "harness": harness,
            "project_dir": project_dir,
        }
        extra = config_targets_by_slug.get(parsed.model_slug)
        if extra:
            for k in ("label", "main_model", "selection_reason", "provider"):
                if k in extra:
                    target[k] = extra[k]
        out.append(target)
    return out


def _filter_discovered(discovered: list[dict], wanted: set[str]) -> list[dict]:
    """Filter discovered targets by full dirname OR by model_slug.

    ``"all"`` selects every discovered project. A bare model_slug that matches
    multiple harness prefixes (e.g. ``kimi_k2_6_ollama_cloud`` exists under
    ``claude-``, ``codex-``, and ``opencode-``) selects ALL matching dirs —
    callers wanting a single harness must pass the full dirname.
    """
    if "all" in wanted:
        return list(discovered)
    out: list[dict] = []
    for t in discovered:
        if (
            t["slug"] in wanted
            or t.get("target_group") in wanted
            or t["model_slug"] in wanted
        ):
            out.append(t)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Role 1: dispatch an LLM auditor against every benchmark-generated "
            "project and write a per-target rubric report. Cross-model "
            "meta-analysis is a separate script: scripts/run_meta_analysis.py."
        )
    )
    parser.add_argument(
        "--models-config",
        default=str(AUDIT_CONFIG_PATH),
        help="Path to models.json (shared model registry).",
    )
    parser.add_argument(
        "--harness",
        default=DEFAULT_AUDIT_HARNESS,
        help=(
            "Audit dispatch harness slug from harnesses.json "
            f"(default: {DEFAULT_AUDIT_HARNESS})."
        ),
    )
    add_run_id_arg(parser)
    parser.add_argument(
        "--model",
        default=DEFAULT_AUDITOR_SLUG,
        help=(
            f"Select one audit model slug from models.json "
            f"(default: {DEFAULT_AUDITOR_SLUG}). Omit with --all-auditors."
        ),
    )
    parser.add_argument(
        "--all-auditors",
        action="store_true",
        help=(
            "Audit with every non-skipped model for --harness instead of --model."
        ),
    )
    parser.add_argument(
        "--benchmark-config",
        default=str(BENCHMARK_CONFIG_PATH),
        help=(
            "Optional metadata source for discovered targets (label, main_model, "
            "selection_reason matched by model_slug). Targets themselves come "
            "from disk discovery; this flag is no longer used to filter the set."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=str(PROMPT_TEMPLATE_PATH),
        help="Path to audit prompt template (must contain {project_dir} and {model_slug} placeholders).",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory where audit reports are written.",
    )
    parser.add_argument(
        "--benchmark-results-dir",
        default=str(DEFAULT_BENCHMARK_RESULTS_DIR),
        help=(
            "Directory where benchmark results live. Every subdir that contains "
            "a project/ child is treated as a target. Recognised harness "
            "prefixes (claude-, codex-, opencode-) are stripped to derive the "
            "model slug; other dir names are used as-is."
        ),
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Select target(s) by full dirname (e.g. claude-kimi_k2_6_ollama_cloud) "
            "or by bare model slug (matches every harness that has that slug). "
            "Repeatable. Use 'all' to select every discovered project. "
            "Default: every discovered project."
        ),
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help=f"Per-audit timeout (default: {DEFAULT_TIMEOUT_MINUTES}).",
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=DEFAULT_NO_PROGRESS_MINUTES,
        help=f"Stall detection threshold (default: {DEFAULT_NO_PROGRESS_MINUTES}).",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if cached.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Rebuild each auditor's comparison.md from existing reports "
            "without running audits."
        ),
    )
    parser.add_argument(
        "--no-enforce-coverage",
        action="store_true",
        help=(
            "Do not require a scored report.md for every results/ target after "
            "dispatch. Default: exit 1 when any benchmark project lacks a "
            "complete audit for the selected auditor(s)."
        ),
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=DEFAULT_JOBS,
        help=f"Number of concurrent audits (default: {DEFAULT_JOBS}). Use 0 for one worker per job.",
    )
    add_rate_limit_cli_args(parser)
    return parser.parse_args()


def _audit_row_to_variant(model: dict[str, Any]) -> dict[str, Any]:
    auditor = dict(model)
    main_model = auditor.get("main_model") or auditor.get("id")
    if not isinstance(main_model, str) or not main_model:
        raise ValueError(
            f"audit model row {auditor.get('slug')!r} needs string id or main_model"
        )
    auditor["main_model"] = main_model
    auditor.setdefault("runner_type", auditor.get("harness", "claude"))
    return auditor


def _audit_config_auditors(
    audit_config: dict[str, Any], harness: str | None
) -> list[dict[str, Any]]:
    return [
        _audit_row_to_variant(model)
        for model in audit_config.get("models", [])
        if not model.get("skip_by_default")
        and (harness is None or model.get("harness", harness) == harness)
    ]


def _all_audit_slugs(audit_config: dict[str, Any]) -> set[str]:
    registry_models = audit_config.get("_registry_models", audit_config.get("models"))
    if registry_models is not None:
        return {str(model["slug"]) for model in registry_models if "slug" in model}
    return set()


def _target_metadata_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("models", []))


def _write_auditor_comparison(
    auditor_dir: Path,
    *,
    display_slug_map: dict[str, str] | None = None,
) -> Path:
    """Rebuild ``comparison.md`` for one auditor tree; returns the output path."""
    comparison_md = build_comparison_table(
        auditor_dir, display_slug_map=display_slug_map
    )
    statistical_md = build_statistical_summary(
        auditor_dir, display_slug_map=display_slug_map
    )
    comparison_path = auditor_dir / "comparison.md"
    comparison_path.write_text(comparison_md.rstrip() + "\n\n" + statistical_md)
    return comparison_path


def _auditor_dirs_for_comparison_rollup(
    results_dir: Path,
    auditors: list[dict[str, Any]],
    *,
    report_only: bool,
    wanted_model: str | None,
) -> list[Path]:
    """Return auditor dirs that should get a comparison.md rebuild.

    ``--report-only`` without ``--model`` rolls up every on-disk auditor tree
    that already has reports. Otherwise only the selected auditor slug(s) are
    considered, and trees without any ``report.md`` are skipped.
    """
    if report_only and wanted_model is None:
        return discover_auditor_subdirs(results_dir)
    dirs: list[Path] = []
    for auditor in auditors:
        auditor_dir = results_dir / auditor["slug"]
        if auditor_dir_has_reports(auditor_dir):
            dirs.append(auditor_dir)
    return dirs


def resolve_auditors_and_targets(
    wanted_model: str | None,
    wanted_targets: set[str] | None,
    audit_config: dict[str, Any],
    benchmark_config: dict[str, Any],
    benchmark_results_dir: Path,
    harness: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Resolve auditor and target lists from CLI flags.

    Auditors come from ``audit_config``. Targets are discovered on disk via
    :func:`discover_project_dirs` and optionally enriched with metadata from
    ``benchmark_config`` when a model_slug matches.

    Default (both wanted sets are None): all non-skipped auditors × every
    discovered project.
    """
    all_auditors = _audit_config_auditors(audit_config, harness)
    audit_slugs = {v["slug"] for v in all_auditors}
    all_audit_slugs = _all_audit_slugs(audit_config)

    config_target_rows = _target_metadata_rows(benchmark_config)
    config_targets_by_slug = {v["slug"]: v for v in config_target_rows}
    discovered = discover_project_dirs(benchmark_results_dir, config_targets_by_slug)
    discovered_dirnames = {t["slug"] for t in discovered}
    discovered_model_slugs = {t["model_slug"] for t in discovered}
    known_target_keys = discovered_dirnames | discovered_model_slugs

    def _emit_unknown_targets(missing: set[str]) -> None:
        print(
            f"Unknown target(s): {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        print(
            "Available dirnames:    " + ", ".join(sorted(discovered_dirnames)),
            file=sys.stderr,
        )
        print(
            "Available model slugs: " + ", ".join(sorted(discovered_model_slugs)),
            file=sys.stderr,
        )

    if wanted_model is not None or wanted_targets is not None:
        auditors = [v for v in all_auditors if v["slug"] == wanted_model]
        targets = _filter_discovered(discovered, wanted_targets or set())

        missing_auditors = {wanted_model} - audit_slugs if wanted_model else set()
        missing_targets = (wanted_targets or set()) - known_target_keys - {"all"}
        if missing_auditors:
            incompatible = missing_auditors & all_audit_slugs
            if incompatible and harness is not None:
                print(
                    f"Slug `{sorted(incompatible)[0]}` is not a {harness} audit model.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"Unknown auditor slug(s): {', '.join(sorted(missing_auditors))}",
                file=sys.stderr,
            )
            print(
                "Available auditors:  " + ", ".join(sorted(audit_slugs)),
                file=sys.stderr,
            )
            sys.exit(1)
        if missing_targets:
            _emit_unknown_targets(missing_targets)
            sys.exit(1)
        if wanted_model is None:
            auditors = all_auditors
        if wanted_targets is None:
            targets = discovered
        if wanted_model is not None and len(auditors) != 1:
            print(
                f"Expected exactly one audit model for slug={wanted_model!r}; "
                f"found {len(auditors)}.",
                file=sys.stderr,
            )
            sys.exit(1)
        return auditors, targets

    return all_auditors, discovered


_AUDIT_PATH_FIELDS = (
    "benchmark_config",
    "benchmark_results_dir",
    "models_config",
    "prompt",
    "results_dir",
)


def normalize_audit_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve relative CLI filesystem paths against the harness checkout."""
    args = normalize_path_fields(args, REPO_ROOT, _AUDIT_PATH_FIELDS)
    if args.run_id:
        layout = layout_from_repo(args.run_id, REPO_ROOT)
        args.benchmark_results_dir = str(layout.projects_root)
        args.results_dir = str(layout.audit_root)
        layout.projects_root.mkdir(parents=True, exist_ok=True)
        layout.audit_root.mkdir(parents=True, exist_ok=True)
    return args


def _print_calibration_warnings(auditor_dir: Path) -> None:
    """Warn when parsed cohort scores suggest rubric saturation."""
    reports = [
        load_rubric_result(p) for p in iter_auditor_report_paths(auditor_dir)
    ]
    totals = [r.total for r in reports if r.total is not None]
    if not totals:
        return
    totals.sort()
    median = totals[len(totals) // 2]
    if median > 85:
        print_line(
            f"WARN calibration: median total={median} > 85 for {auditor_dir.name} "
            "(rubric may be too lenient — see meta-analysis Check 1)"
        )
    for index, full_count, scored_count, max_score in saturated_dimension_warnings(
        reports
    ):
        max_display = max_score if max_score is not None else "?"
        print_line(
            f"WARN calibration: D{index} saturated "
            f"({full_count}/{scored_count} at {max_display}/{max_display}) "
            f"for {auditor_dir.name}"
        )


def main() -> int:
    args = normalize_audit_paths(parse_args())
    audit_config_path = Path(args.models_config)
    benchmark_config_path = Path(args.benchmark_config)
    prompt_template_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    benchmark_results_dir = Path(args.benchmark_results_dir)

    audit_config = load_json(audit_config_path)
    audit_config = resolve_audit_harness_config(
        audit_config, audit_config_path, args.harness
    )
    benchmark_config = load_json(benchmark_config_path)
    prompt_template = prompt_template_path.read_text()
    display_slug_map = build_display_slug_map(benchmark_config_path)

    if args.report_only or args.all_auditors:
        wanted_model = None
    else:
        wanted_model = args.model
    wanted_targets = set(args.target) if args.target else None

    if args.report_only and wanted_model is None:
        results_dir.mkdir(parents=True, exist_ok=True)
        rollup_dirs = discover_auditor_subdirs(results_dir)
        if not rollup_dirs:
            print(
                f"No auditor trees with reports under {results_dir}.",
                file=sys.stderr,
            )
            return 1
        for auditor_dir in rollup_dirs:
            comparison_path = _write_auditor_comparison(
                auditor_dir, display_slug_map=display_slug_map
            )
            print_line(
                f"Comparison table + statistical summary written: {comparison_path}"
            )
        print_line(
            "Next: run scripts/run_meta_analysis.py to dispatch the cross-auditor "
            "AI meta-analysis."
        )
        return 0

    auditors, targets = resolve_auditors_and_targets(
        wanted_model,
        wanted_targets,
        audit_config,
        benchmark_config,
        benchmark_results_dir,
        args.harness,
    )

    if not auditors:
        print("No auditors selected.", file=sys.stderr)
        return 1
    if not targets and not args.report_only:
        print("No targets selected.", file=sys.stderr)
        return 1

    if not args.report_only:
        ok, err = _verify_auditor_binaries(auditors)
        if not ok:
            print(err, file=sys.stderr)
            return 1

    config_targets_by_slug = {
        v["slug"]: v for v in _target_metadata_rows(benchmark_config)
    }
    model_registry = registry_by_slug(
        list(benchmark_config.get("models", []))
        if isinstance(benchmark_config.get("models"), list)
        else []
    )
    all_benchmark_targets = discover_project_dirs(
        benchmark_results_dir, config_targets_by_slug
    )
    if wanted_targets is None:
        targets = all_benchmark_targets

    jobs: list[tuple[dict, dict]] = [
        (auditor, target) for auditor in auditors for target in targets
    ]
    jobs_count = args.jobs if args.jobs > 0 else len(jobs)
    jobs_count = max(1, min(jobs_count, len(jobs))) if jobs else 1

    print_line(
        f"Audit benchmark: {len(auditors)} auditors × {len(targets)} targets = "
        f"{len(jobs)} runs, jobs={jobs_count}"
    )
    print_line(
        f"Benchmark results: {len(all_benchmark_targets)} project(s) under "
        f"{benchmark_results_dir}"
    )
    enforce_coverage = not args.no_enforce_coverage

    if not args.report_only:
        timeout_seconds = args.timeout_minutes * 60
        no_progress_timeout_seconds = args.no_progress_minutes * 60
        rate_limit_policy = rate_limit_policy_from_args(args)
        runner = audit_config.get("runner") or {}
        dispatch = run_audit_jobs(
            auditors=auditors,
            targets=targets,
            jobs_count=jobs_count,
            config=AuditDispatchConfig(
                results_dir=results_dir,
                prompt_template=prompt_template,
                timeout_seconds=timeout_seconds,
                no_progress_timeout_seconds=no_progress_timeout_seconds,
                force=args.force,
                runner_command_prefix=runner.get("command_prefix"),
                rate_limit_policy=rate_limit_policy,
                model_registry=model_registry,
            ),
        )
        if dispatch.failures:
            return 1

    if enforce_coverage and not args.report_only:
        message = coverage_failure_message(
            benchmark_results_dir=benchmark_results_dir,
            audit_results_dir=results_dir,
            auditor_slugs=[a["slug"] for a in auditors],
            required_targets=all_benchmark_targets,
        )
        if message:
            print(message, file=sys.stderr)
            return 1

    # Per-auditor comparison + regex rollup (including --report-only). Only
    # auditor trees that contain at least one report.md are touched.
    results_dir.mkdir(parents=True, exist_ok=True)
    rollup_dirs = _auditor_dirs_for_comparison_rollup(
        results_dir,
        auditors,
        report_only=args.report_only,
        wanted_model=wanted_model,
    )
    if not rollup_dirs:
        print(
            "No audit reports found to roll up. Run audits first or pass "
            "--model to select an auditor tree.",
            file=sys.stderr,
        )
        return 1
    for auditor_dir in rollup_dirs:
        comparison_path = _write_auditor_comparison(
            auditor_dir, display_slug_map=display_slug_map
        )
        print_line(f"Comparison table + statistical summary written: {comparison_path}")
        _print_calibration_warnings(auditor_dir)

    print_line(
        "Next: run scripts/run_meta_analysis.py to dispatch the cross-auditor "
        "AI meta-analysis."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
