#!/usr/bin/env python3
"""Publish a benchmark campaign for git tracking.

Strips ephemeral artifacts from generated projects, writes a campaign manifest,
updates .gitignore allowlists, and refreshes latest symlinks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.publish_campaign import (  # noqa: E402
    build_manifest,
    discover_targets_from_auditor,
    load_manifest,
    publish_campaign,
)
from benchmark.result_layout import add_run_id_arg, layout_from_repo  # noqa: E402
from benchmark.util import print_line  # noqa: E402

DEFAULT_AUDIT_ROOT = REPO_ROOT / "audit-reports"
DEFAULT_RESULTS_ROOT = "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign-id",
        required=True,
        help="Campaign identifier (e.g. 2026-05-ollama-cloud-v3.2).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Human-readable campaign label (default: derived from campaign-id).",
    )
    parser.add_argument(
        "--auditor",
        required=True,
        help="Auditor slug directory under audit-reports/ (e.g. codex_gpt_5_5).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Use an existing manifest.json instead of building one.",
    )
    parser.add_argument(
        "--auto-discover-targets",
        action="store_true",
        help="Discover targets from audit-reports/<auditor>/*/report.md.",
    )
    add_run_id_arg(parser)
    parser.add_argument(
        "--audit-root",
        type=Path,
        default=DEFAULT_AUDIT_ROOT,
        help="Audit reports root (legacy layout; ignored with --run-id).",
    )
    parser.add_argument(
        "--results-root",
        default=DEFAULT_RESULTS_ROOT,
        help="Benchmark results root relative to repo (legacy layout; ignored with --run-id).",
    )
    parser.add_argument(
        "--campaign-date",
        default=None,
        help="ISO date for the campaign manifest (default: today).",
    )
    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Skip stripping ephemeral project directories.",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Skip updating .gitignore published-campaign block.",
    )
    parser.add_argument(
        "--no-symlinks",
        action="store_true",
        help="Skip updating data/campaigns/latest and results/latest.",
    )
    parser.add_argument(
        "--fail-on-secrets",
        action="store_true",
        help="Exit non-zero when secret-shaped patterns are found.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    label = args.label or args.campaign_id.replace("-", " ").title()

    if args.manifest:
        manifest = load_manifest(args.manifest.resolve())
    else:
        if not args.auto_discover_targets:
            print(
                "Provide --auto-discover-targets or --manifest.",
                file=sys.stderr,
            )
            return 1
        if args.run_id:
            layout = layout_from_repo(args.run_id, REPO_ROOT)
            audit_root = layout.audit_root
        else:
            audit_root = args.audit_root
        targets = discover_targets_from_auditor(audit_root, args.auditor)
        manifest = build_manifest(
            campaign_id=args.campaign_id,
            label=label,
            auditor_slug=args.auditor,
            targets=targets,
            repo_root=REPO_ROOT,
            campaign_date=args.campaign_date,
            benchmark_results_root=args.results_root,
            run_id=args.run_id,
        )

    result = publish_campaign(
        repo_root=REPO_ROOT,
        manifest=manifest,
        strip_results=not args.no_strip,
        update_gitignore_file=not args.no_gitignore,
        update_symlinks=not args.no_symlinks,
    )

    manifest_path = result["manifest_path"]
    print_line(f"Wrote manifest: {manifest_path}")

    stripped = result["stripped"]
    if stripped:
        total = sum(len(v) for v in stripped.values())
        print_line(f"Stripped ephemeral paths from {len(stripped)} targets ({total} paths)")

    publish_paths = result["publish_paths"]
    print_line(f"Publishable files: {len(publish_paths)}")

    secret_errors = result["secret_errors"]
    if secret_errors:
        print_line("Secret-pattern warnings:")
        for err in secret_errors:
            print(f"  - {err}", file=sys.stderr)
        if args.fail_on_secrets:
            return 1

    print_line("Latest symlinks:")
    print_line(f"  data/campaigns/latest -> {manifest.id}")
    if manifest.run_id:
        print_line(f"  results/latest -> {manifest.run_id}")
    else:
        print_line(f"  audit-reports/latest -> {manifest.auditor_slug}")
    print_line(f"  meta-analysis: {manifest.meta_analysis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
