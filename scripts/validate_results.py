#!/usr/bin/env python3
"""Check benchmark results under ``results/`` for completed, usable runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.replicate_expectations import (  # noqa: E402
    filter_expected_leaves,
    find_replicate_coverage_gaps,
    format_replicate_gaps,
    expected_benchmark_leaves,
)
from benchmark.result_layout import (  # noqa: E402
    add_run_id_arg,
    benchmark_target_slug_from_leaf,
    discover_project_result_jsons,
    layout_from_repo,
    matches_benchmark_only_filter,
)
from benchmark.result_validation import (  # noqa: E402
    followup_expected,
    resolve_result_target_identity,
    validate_benchmark_result,
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
            "(default: on when --run-id is set)."
        ),
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


def _matches_only_filter(result_path: Path, only: set[str], projects_root: Path) -> bool:
    return matches_benchmark_only_filter(result_path, only, projects_root)


def main() -> int:
    args = parse_args()
    if args.run_id:
        layout = layout_from_repo(args.run_id, REPO_ROOT)
        results_dir = layout.projects_root.resolve()
    else:
        results_dir = args.results_dir.resolve()
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
        else bool(args.run_id)
    )

    replicate_failures = 0
    if enforce_replicates:
        expected = filter_expected_leaves(
            expected_benchmark_leaves(args.models_config.resolve()),
            only,
        )
        gaps = find_replicate_coverage_gaps(results_dir, expected)
        gap_message = format_replicate_gaps(gaps)
        if gap_message:
            print(gap_message, file=sys.stderr)
            replicate_failures = len(gaps)

    if args.run_id:
        result_paths = discover_project_result_jsons(results_dir)
    else:
        result_paths = sorted(results_dir.glob("**/result.json"))
    if only:
        result_paths = [
            p for p in result_paths if _matches_only_filter(p, only, results_dir)
        ]

    if not result_paths:
        if replicate_failures:
            print_line(f"replicate_gaps={replicate_failures} checked=0 failed=0")
            return 1
        print_line("No result.json files matched.")
        return 1

    failures = replicate_failures
    for result_path in result_paths:
        result_dir = result_path.parent
        _harness, slug = resolve_result_target_identity(result_dir)
        model = registry.get(slug, {})
        expect_followup = followup_expected(followup_prompt=followup_prompt)
        vr = validate_benchmark_result(
            result_dir,
            model=model or None,
            followup_expected_flag=expect_followup,
        )
        label = benchmark_target_slug_from_leaf(result_dir, results_dir)
        status = "PASS" if vr.ok else "FAIL"
        print_line(f"[{status}] {label}: {vr.summary()}")
        if not vr.ok:
            failures += 1
            if args.remove_on_fail:
                wipe_result_dir(result_dir, recreate=False)
                print_line(f"  removed {result_dir}")

    if replicate_failures:
        print_line(f"replicate_gaps={replicate_failures}")
    print_line(f"checked={len(result_paths)} failed={failures}")
    if args.remove_on_fail and failures:
        print_line(f"removed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
