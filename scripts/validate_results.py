#!/usr/bin/env python3
"""Check benchmark results under ``results/`` for completed, usable runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.result_layout import (  # noqa: E402
    add_run_id_arg,
    discover_project_result_jsons,
    layout_from_repo,
    split_target_slug,
)
from benchmark.result_validation import (  # noqa: E402
    followup_expected,
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
        help="Comma-separated result directory names (e.g. opencode-qwen3_5_ollama_cloud).",
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
    return parser.parse_args()


def _registry_by_slug(models_config: Path) -> dict[str, dict]:
    payload = load_json(models_config)
    models = payload.get("models", [])
    if not isinstance(models, list):
        return {}
    return {
        str(m["slug"]): m for m in models if isinstance(m, dict) and m.get("slug")
    }


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

    if args.run_id:
        result_paths = discover_project_result_jsons(results_dir)
    else:
        result_paths = sorted(results_dir.glob("*/result.json"))
    if only:
        result_paths = [p for p in result_paths if p.parent.name in only]

    if not result_paths:
        print_line("No result.json files matched.")
        return 1

    failures = 0
    for result_path in result_paths:
        result_dir = result_path.parent
        harness, slug = split_target_slug(result_dir.name)
        model = registry.get(slug, {})
        expect_followup = followup_expected(followup_prompt=followup_prompt)
        vr = validate_benchmark_result(
            result_dir,
            model=model or None,
            followup_expected_flag=expect_followup,
        )
        status = "PASS" if vr.ok else "FAIL"
        print_line(f"[{status}] {result_dir.name}: {vr.summary()}")
        if not vr.ok:
            failures += 1
            if args.remove_on_fail:
                wipe_result_dir(result_dir, recreate=False)
                print_line(f"  removed {result_dir}")

    print_line(f"checked={len(result_paths)} failed={failures}")
    if args.remove_on_fail and failures:
        print_line(f"removed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
