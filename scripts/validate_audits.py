#!/usr/bin/env python3
"""Check audit outputs under ``audit-reports/`` for scored rubric reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_coverage import AuditCoverageGap, format_coverage_gaps  # noqa: E402
from benchmark.audit_meta import discover_auditor_subdirs  # noqa: E402
from benchmark.audit_validation import (  # noqa: E402
    AuditValidationResult,
    audit_leaf_matches_only,
    audit_target_slug_from_leaf,
    coverage_gaps_for_auditors,
    discover_audit_leaves,
    discover_benchmark_targets,
    validate_audit_leaf,
)
from benchmark.defaults import DEFAULT_AUDIT_HARNESS, DEFAULT_AUDITOR_SLUG  # noqa: E402
from benchmark.result_layout import (  # noqa: E402
    add_run_id_arg,
    audit_target_dir,
    resolve_default_run_id,
    resolve_run_layout,
)
from benchmark.result_validation import wipe_result_dir  # noqa: E402
from benchmark.util import print_line  # noqa: E402


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
        "--audit-reports-dir",
        type=Path,
        default=None,
        help=(
            "Audit output root (default: results/<run_id>/audit-reports or "
            "audit-reports/ when --run-id is omitted)."
        ),
    )
    parser.add_argument(
        "--only",
        help=(
            "Comma-separated target names: target group "
            "(e.g. opencode-qwen3_5), replicate slug (run_01), or full path "
            "(group/run_01)."
        ),
    )
    parser.add_argument(
        "--models-config",
        type=Path,
        default=REPO_ROOT / "config" / "models.json",
        help="Shared model registry (auditor rows and benchmark metadata).",
    )
    parser.add_argument(
        "--harness",
        default=DEFAULT_AUDIT_HARNESS,
        help=(
            "Audit harness slug from harnesses.json when resolving auditors "
            f"(default: {DEFAULT_AUDIT_HARNESS})."
        ),
    )
    parser.add_argument(
        "--model",
        "--auditor",
        dest="auditor",
        default=DEFAULT_AUDITOR_SLUG,
        help=(
            f"Validate one auditor slug from models.json "
            f"(default: {DEFAULT_AUDITOR_SLUG}). Omit with --all-auditors."
        ),
    )
    parser.add_argument(
        "--all-auditors",
        action="store_true",
        help="Validate every auditor tree under the audit reports root.",
    )
    parser.add_argument(
        "--enforce-coverage",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Require a scored report.md for every benchmark target per selected "
            "auditor (default: on when a run-scoped layout is used)."
        ),
    )
    parser.add_argument(
        "--require-full-rubric",
        action="store_true",
        help="Fail when report.md parses fewer than ten dimension rows.",
    )
    parser.add_argument(
        "--remove-on-fail",
        action="store_true",
        help="Delete the audit leaf directory when validation or coverage fails.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full validation issue details for each leaf (default: PASS/FAIL only).",
    )
    return parser.parse_args()


def _resolve_scope(
    args: argparse.Namespace,
) -> tuple[Path, Path, str | None, bool]:
    """Return projects root, audit root, effective run id, auto-resolved flag."""
    results_base = args.results_dir.resolve()
    auto_resolved = args.run_id is None
    effective_run_id = args.run_id or resolve_default_run_id(results_base)
    if effective_run_id:
        layout = resolve_run_layout(effective_run_id, results_base)
        projects_root = layout.projects_root.resolve()
        audit_root = (
            args.audit_reports_dir.resolve()
            if args.audit_reports_dir
            else layout.audit_root.resolve()
        )
        return projects_root, audit_root, effective_run_id, auto_resolved

    projects_root = results_base
    audit_root = (
        args.audit_reports_dir.resolve()
        if args.audit_reports_dir
        else (REPO_ROOT / "audit-reports").resolve()
    )
    return projects_root, audit_root, None, False


def _auditors_to_validate(args: argparse.Namespace, audit_root: Path) -> list[str]:
    if args.all_auditors:
        return [path.name for path in discover_auditor_subdirs(audit_root)]
    return [args.auditor]


def _target_matches_only(target: dict[str, object], only: set[str]) -> bool:
    slug = str(target["slug"])
    if slug in only:
        return True
    if target.get("target_group") in only:
        return True
    if target.get("model_slug") in only:
        return True
    return slug.split("/", 1)[0] in only


def _format_leaf_line(
    status: str,
    label: str,
    vr: AuditValidationResult,
    *,
    verbose: bool,
) -> str:
    if verbose:
        return f"[{status}] {label}: {vr.summary()}"
    return f"[{status}] {label}"


def _print_coverage_gaps(
    gaps: list[AuditCoverageGap],
    *,
    verbose: bool,
) -> None:
    if not gaps:
        return
    if verbose:
        message = format_coverage_gaps(gaps)
        if message:
            print(message, file=sys.stderr)
        return
    for gap in gaps:
        print_line(f"[GAP] {gap.auditor_slug}/{gap.target_slug}: {gap.reason}")


def _remove_coverage_gap_leaves(
    gaps: list[AuditCoverageGap],
    audit_root: Path,
    *,
    remove_on_fail: bool,
) -> int:
    if not remove_on_fail:
        return 0
    removed = 0
    for gap in gaps:
        leaf_dir = audit_target_dir(audit_root, gap.auditor_slug, gap.target_slug)
        if leaf_dir.exists():
            wipe_result_dir(leaf_dir, recreate=False)
            removed += 1
            print_line(f"  removed {leaf_dir}")
    return removed


def main() -> int:
    args = parse_args()
    projects_root, audit_root, effective_run_id, auto_resolved = _resolve_scope(args)
    if auto_resolved and effective_run_id:
        print_line(f"Using run {effective_run_id} (latest under {args.results_dir})")

    only: set[str] | None = None
    if args.only:
        only = {part.strip() for part in args.only.split(",") if part.strip()}

    auditor_slugs = _auditors_to_validate(args, audit_root)
    if not auditor_slugs:
        print("No auditor trees matched.", file=sys.stderr)
        return 1

    enforce_coverage = (
        args.enforce_coverage
        if args.enforce_coverage is not None
        else bool(effective_run_id)
    )
    required_targets = discover_benchmark_targets(projects_root)
    if only:
        required_targets = [
            target for target in required_targets if _target_matches_only(target, only)
        ]

    coverage_failures = 0
    gaps: list[AuditCoverageGap] = []
    if enforce_coverage and required_targets:
        gaps = coverage_gaps_for_auditors(
            projects_root=projects_root,
            audit_root=audit_root,
            auditor_slugs=auditor_slugs,
            required_targets=required_targets,
        )
        _print_coverage_gaps(gaps, verbose=args.verbose)
        coverage_failures = len(gaps)

    removed = _remove_coverage_gap_leaves(
        gaps,
        audit_root,
        remove_on_fail=args.remove_on_fail,
    )

    leaves_to_check: list[tuple[str, Path]] = []
    if enforce_coverage and required_targets:
        for auditor_slug in auditor_slugs:
            for target in required_targets:
                target_slug = str(target["slug"])
                leaf_dir = audit_target_dir(audit_root, auditor_slug, target_slug)
                leaves_to_check.append((auditor_slug, leaf_dir))
    else:
        for auditor_slug in auditor_slugs:
            auditor_dir = audit_root / auditor_slug
            for leaf_dir in discover_audit_leaves(audit_root, auditor_slug):
                if only and not audit_leaf_matches_only(leaf_dir, auditor_dir, only):
                    continue
                leaves_to_check.append((auditor_slug, leaf_dir))

    if not leaves_to_check and not coverage_failures:
        print_line("No audit leaves matched.")
        return 1

    failures = 0
    checked = 0
    for auditor_slug, leaf_dir in sorted(
        leaves_to_check, key=lambda pair: (pair[0], pair[1].as_posix())
    ):
        checked += 1
        auditor_dir = audit_root / auditor_slug
        target_slug = audit_target_slug_from_leaf(leaf_dir, auditor_dir)
        vr = validate_audit_leaf(
            audit_root=audit_root,
            auditor_slug=auditor_slug,
            target_slug=target_slug,
            leaf_dir=leaf_dir,
            require_full_rubric=args.require_full_rubric,
        )
        label = f"{auditor_slug}/{target_slug}"
        status = "PASS" if vr.ok else "FAIL"
        print_line(_format_leaf_line(status, label, vr, verbose=args.verbose))
        if not vr.ok:
            failures += 1
            if args.remove_on_fail and leaf_dir.exists():
                wipe_result_dir(leaf_dir, recreate=False)
                removed += 1
                print_line(f"  removed {leaf_dir}")

    if coverage_failures:
        print_line(f"coverage_gaps={coverage_failures}")
    print_line(f"checked={checked} failed={failures}")
    if args.remove_on_fail and removed:
        print_line(f"removed={removed}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
