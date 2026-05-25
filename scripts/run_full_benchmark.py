#!/usr/bin/env python3
"""End-to-end benchmark + audit + meta-analysis pipeline.

Phase 1 runs an explicit (harness, model) matrix:
  - Every ``ollama_cloud`` registry row on opencode, codex, and claude (not cursor)
  - Subscription baselines: ``claude_opus_4_7`` (claude), ``codex_gpt_5_5`` (codex)

Phase 2 audits all benchmark results; Phase 3 runs cross-auditor meta-analysis.

Environment:
  AUDITOR_SLUG, META_ANALYSIS_AUDITOR_SLUG, META_ANALYSIS_HARNESS, META_ANALYSIS_INPUT_DIR

Examples:
  python3 scripts/run_full_benchmark.py
  python3 scripts/run_full_benchmark.py --force
  python3 scripts/run_full_benchmark.py --list-steps
  python3 scripts/run_full_benchmark.py -j 4
  AUDITOR_SLUG=kimi_k2_6_ollama_cloud python3 scripts/run_full_benchmark.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

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
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Benchmark output directory.",
    )
    parser.add_argument(
        "--audit-reports-dir",
        type=Path,
        default=REPO_ROOT / "audit-reports",
        help="Audit output root.",
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="Print the Phase 1 build matrix and exit.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=2,
        help="Phase 1 concurrency passed to run_benchmark.py (default: 2).",
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

    models_config = args.models_config.resolve()
    if args.list_steps:
        for step in build_matrix(models_config):
            print(f"{step.harness}\t{step.model_slug}\t{step.report_path}")
        return 0

    auditor_slug = env_default("AUDITOR_SLUG", "deepseek_v4_pro_ollama_cloud")
    meta_slug_env = os.environ.get("META_ANALYSIS_AUDITOR_SLUG") or None
    meta_harness_env = os.environ.get("META_ANALYSIS_HARNESS") or None
    meta_input_env = os.environ.get("META_ANALYSIS_INPUT_DIR") or None

    if not args.skip_build:
        phase_build(
            models_config,
            args.results_dir,
            forward,
            jobs=args.jobs,
            dry_run=args.dry_run,
        )

    meta_slug, meta_harness, meta_input = resolve_meta_config(
        args.harnesses_config.resolve(),
        models_config,
        auditor_slug,
        meta_slug_env,
        meta_harness_env,
        meta_input_env,
    )
    assert_no_stale_audit_reports(args.audit_reports_dir, auditor_slug)

    if not args.skip_audit:
        phase_audit(
            models_config,
            args.results_dir,
            args.audit_reports_dir,
            auditor_slug,
            dry_run=args.dry_run,
        )

    if not args.skip_meta:
        phase_meta_analysis(
            models_config,
            args.audit_reports_dir,
            meta_slug,
            meta_harness,
            meta_input,
            dry_run=args.dry_run,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
