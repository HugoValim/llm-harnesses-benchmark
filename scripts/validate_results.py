#!/usr/bin/env python3
"""Check benchmark results under ``results/`` for completed, usable runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.replicate_expectations import (  # noqa: E402
    ExpectedBenchmarkLeaf,
    ReplicateCoverageGap,
    filter_expected_leaves,
    find_replicate_coverage_gaps,
    format_replicate_gaps,
    expected_benchmark_leaves,
)
from benchmark.result_layout import (  # noqa: E402
    REPLICATE_DIR_PATTERN,
    add_run_id_arg,
    benchmark_target_slug_from_leaf,
    discover_benchmark_target_dirs,
    matches_benchmark_only_filter,
    resolve_default_run_id,
    resolve_run_layout,
)
from benchmark.result_validation import (  # noqa: E402
    ValidationResult,
    followup_expected,
    validate_replicate_leaf,
    wipe_result_dir,
)
from benchmark.util import load_json, print_line  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Benchmark output root (default: results/).",
    )
    add_run_id_arg(parser)
    parser.add_argument(
        "--only",
        help=(
            "Comma-separated target names: target group "
            "(e.g. opencode-qwen3_5_ollama_cloud), replicate slug "
            "(run_01), or full path (group/run_01)."
        ),
    )
    parser.add_argument(
        "--models-config",
        type=Path,
        default=REPO_ROOT / "config" / "models.json",
        help="Optional registry for follow-up expectations per slug.",
    )
    parser.add_argument(
        "--remove-on-fail",
        action="store_true",
        help="Delete the result directory when validation fails (same wipe as benchmark retries).",
    )
    parser.add_argument(
        "--enforce-replicates",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Require every configured replicate leaf from models.json num_runs "
            "(default: on when a run-scoped layout is used)."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full validation issue details for each leaf (default: PASS/FAIL only).",
    )
    return parser.parse_args()


def _registry_by_slug(models_config: Path) -> dict[str, dict]:
    payload = load_json(models_config)
    models = payload.get("models", [])
    if not isinstance(models, list):
        return {}
    return {
        str(m["slug"]): m for m in models if isinstance(m, dict) and m.get("slug")
    }


def _leaf_matches_only(leaf_dir: Path, only: set[str], projects_root: Path) -> bool:
    slug = benchmark_target_slug_from_leaf(leaf_dir, projects_root)
    if slug in only:
        return True
    if leaf_dir.name in only:
        return True
    if REPLICATE_DIR_PATTERN.match(leaf_dir.name):
        target_group = leaf_dir.parent.name
        full_slug = f"{target_group}/{leaf_dir.name}"
        return target_group in only or full_slug in only
    return leaf_dir.name in only


def _resolve_results_scope(
    args: argparse.Namespace,
) -> tuple[Path, str | None, bool]:
    """Return projects root, effective run id, and whether run id was auto-resolved."""
    results_base = args.results_dir.resolve()
    auto_resolved = args.run_id is None
    effective_run_id = args.run_id or resolve_default_run_id(results_base)
    if effective_run_id:
        layout = resolve_run_layout(effective_run_id, results_base)
        return layout.projects_root.resolve(), effective_run_id, auto_resolved
    return results_base, None, False


def _leaves_to_validate(
    *,
    projects_root: Path,
    effective_run_id: str | None,
    enforce_replicates: bool,
    models_config: Path,
    only: set[str] | None,
    registry: dict[str, dict],
) -> tuple[list[ExpectedBenchmarkLeaf], list[Path]]:
    """Return configured leaves and on-disk leaf dirs to validate."""
    if effective_run_id and enforce_replicates:
        expected = filter_expected_leaves(
            expected_benchmark_leaves(models_config.resolve()),
            only,
        )
        leaves_on_disk = [
            projects_root / leaf.slug
            for leaf in expected
            if (projects_root / leaf.slug).is_dir()
        ]
        return expected, leaves_on_disk

    if effective_run_id:
        leaf_dirs = discover_benchmark_target_dirs(projects_root)
        if only:
            leaf_dirs = [
                d for d in leaf_dirs if _leaf_matches_only(d, only, projects_root)
            ]
        return [], leaf_dirs

    if only:
        result_paths = [
            p
            for p in sorted(projects_root.glob("**/result.json"))
            if matches_benchmark_only_filter(p, only, projects_root)
        ]
    else:
        result_paths = sorted(projects_root.glob("**/result.json"))
    return [], [p.parent for p in result_paths]


def _format_leaf_line(
    status: str,
    label: str,
    vr: ValidationResult,
    *,
    verbose: bool,
) -> str:
    if verbose:
        return f"[{status}] {label}: {vr.summary()}"
    return f"[{status}] {label}"


def _print_coverage_gaps(
    gaps: list[ReplicateCoverageGap],
    *,
    verbose: bool,
) -> None:
    if not gaps:
        return
    if verbose:
        message = format_replicate_gaps(gaps)
        if message:
            print(message, file=sys.stderr)
        return
    for gap in gaps:
        print_line(f"[GAP] {gap.slug}")


def main() -> int:
    args = parse_args()
    results_dir, effective_run_id, auto_resolved = _resolve_results_scope(args)
    if auto_resolved and effective_run_id:
        print_line(f"Using run {effective_run_id} (latest under {args.results_dir})")
    only = None
    if args.only:
        only = {part.strip() for part in args.only.split(",") if part.strip()}

    registry = _registry_by_slug(args.models_config)
    followup_prompt_path = REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"
    followup_prompt = (
        followup_prompt_path.read_text().strip()
        if followup_prompt_path.is_file()
        else None
    )
    if not followup_prompt:
        print(
            f"Follow-up prompt missing or empty: {followup_prompt_path}",
            file=sys.stderr,
        )
        return 1

    enforce_replicates = (
        args.enforce_replicates
        if args.enforce_replicates is not None
        else bool(effective_run_id)
    )
    expect_followup = followup_expected(followup_prompt=followup_prompt)

    expected_leaves, leaf_dirs = _leaves_to_validate(
        projects_root=results_dir,
        effective_run_id=effective_run_id,
        enforce_replicates=enforce_replicates,
        models_config=args.models_config,
        only=only,
        registry=registry,
    )

    replicate_failures = 0
    gaps: list[ReplicateCoverageGap] = []
    if enforce_replicates and expected_leaves:
        gaps = find_replicate_coverage_gaps(results_dir, expected_leaves)
        _print_coverage_gaps(gaps, verbose=args.verbose)
        replicate_failures = len(gaps)

    if not leaf_dirs and not replicate_failures:
        print_line("No benchmark replicate leaves matched.")
        return 1

    failures = replicate_failures
    checked = 0
    for leaf_dir in sorted(leaf_dirs, key=lambda p: p.as_posix()):
        checked += 1
        leaf = next(
            (e for e in expected_leaves if (results_dir / e.slug) == leaf_dir),
            None,
        )
        harness = leaf.harness if leaf else None
        model_slug = leaf.model_slug if leaf else None
        if harness is None or model_slug is None:
            from benchmark.result_validation import (  # noqa: E402
                resolve_result_target_identity,
            )

            harness, model_slug = resolve_result_target_identity(leaf_dir)
        model = registry.get(model_slug or "", {})
        vr = validate_replicate_leaf(
            leaf_dir,
            harness=harness or "unknown",
            model=model or None,
            followup_expected_flag=expect_followup,
        )
        label = benchmark_target_slug_from_leaf(leaf_dir, results_dir)
        status = "PASS" if vr.ok else "FAIL"
        print_line(_format_leaf_line(status, label, vr, verbose=args.verbose))
        if not vr.ok:
            failures += 1
            if args.remove_on_fail:
                wipe_result_dir(leaf_dir, recreate=False)
                print_line(f"  removed {leaf_dir}")

    if replicate_failures:
        print_line(f"replicate_gaps={replicate_failures}")
    print_line(f"checked={checked} failed={failures}")
    if args.remove_on_fail and failures:
        print_line(f"removed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
