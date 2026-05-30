#!/usr/bin/env python3
"""End-to-end benchmark + audit + meta-analysis pipeline.

Phase 1 runs every model in ``config/models.json`` on each harness it resolves for
(opencode, codex, claude, cursor per provider routing).

Phase 2 audits all benchmark results; Phase 3 runs cross-auditor meta-analysis.

All outputs land under ``results/<run_id>/`` (``--run-id`` required).

Environment (defaults: ``codex_gpt_5_5`` / codex harness for audit and meta):
  AUDITOR_SLUG, META_ANALYSIS_AUDITOR_SLUG, META_ANALYSIS_HARNESS, META_ANALYSIS_INPUT_DIR

Examples:
  python3 scripts/run_full_benchmark.py --run-id run_02
  python3 scripts/run_full_benchmark.py --run-id run_02 --force
  python3 scripts/run_full_benchmark.py --run-id run_02 --list-steps
  python3 scripts/run_full_benchmark.py --run-id run_02 -j 4  # override default -j 3
  AUDITOR_SLUG=kimi_k2_6_ollama_cloud python3 scripts/run_full_benchmark.py --run-id run_02
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.defaults import DEFAULT_AUDITOR_SLUG, DEFAULT_JOBS  # noqa: E402
from benchmark.full_pipeline import (  # noqa: E402
    REPO_ROOT,
    assert_no_stale_audit_reports,
    build_matrix,
    env_default,
    phase_audit,
    phase_build,
    phase_meta_analysis,
    reject_forwarded_model_flag,
    resolve_meta_config,
)
from benchmark.result_layout import add_run_id_arg, layout_from_repo  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-config",
        type=Path,
        default=REPO_ROOT / "config" / "models.json",
        help="Shared model registry (default: config/models.json).",
    )
    parser.add_argument(
        "--harnesses-config",
        type=Path,
        default=REPO_ROOT / "config" / "harnesses.json",
        help="Harness registry for meta-analyst routing.",
    )
    add_run_id_arg(parser, required=True)
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="Print the Phase 1 build matrix and exit.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help=f"Concurrency for build and audit phases (default: {DEFAULT_JOBS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print subprocess commands without running agents.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip Phase 1.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip Phase 2.",
    )
    parser.add_argument(
        "--skip-meta",
        action="store_true",
        help="Skip Phase 3.",
    )
    parser.add_argument(
        "forward_args",
        nargs=argparse.REMAINDER,
        help="Flags forwarded to each run_benchmark.py invocation (e.g. --force).",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    forward = list(args.forward_args)
    if forward and forward[0] == "--":
        forward = forward[1:]
    reject_forwarded_model_flag(forward)

    layout = layout_from_repo(args.run_id, REPO_ROOT)
    models_config = args.models_config.resolve()
    if args.list_steps:
        for step in build_matrix(models_config):
            print(f"{step.harness}\t{step.model_slug}")
        return 0

    auditor_slug = env_default("AUDITOR_SLUG", DEFAULT_AUDITOR_SLUG)
    meta_slug_env = os.environ.get("META_ANALYSIS_AUDITOR_SLUG") or None
    meta_harness_env = os.environ.get("META_ANALYSIS_HARNESS") or None
    meta_input_env = os.environ.get("META_ANALYSIS_INPUT_DIR") or None

    if not args.skip_build:
        phase_build(
            models_config,
            layout.projects_root,
            forward,
            jobs=args.jobs,
            run_id=args.run_id,
            dry_run=args.dry_run,
        )

    auditor_harness, meta_slug, meta_harness, meta_input = resolve_meta_config(
        args.harnesses_config.resolve(),
        models_config,
        auditor_slug,
        meta_slug_env,
        meta_harness_env,
        meta_input_env,
    )
    assert_no_stale_audit_reports(layout.audit_root, auditor_slug)

    if not args.skip_audit:
        phase_audit(
            models_config,
            layout.projects_root,
            layout.audit_root,
            auditor_slug,
            auditor_harness,
            jobs=args.jobs,
            run_id=args.run_id,
            dry_run=args.dry_run,
        )

    if not args.skip_meta:
        phase_meta_analysis(
            models_config,
            layout.audit_root,
            meta_slug,
            meta_harness,
            meta_input,
            run_id=args.run_id,
            meta_output_dir=layout.run_root,
            dry_run=args.dry_run,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
