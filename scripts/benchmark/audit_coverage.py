"""Ensure every benchmark ``results/`` target has a complete audit report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from benchmark.audit_report import audit_report_is_complete
from benchmark.result_layout import audit_report_md, audit_result_json
from benchmark.util import USAGE_LIMIT_REACHED

_RETRYABLE_AUDIT_STATUSES = frozenset(
    {
        USAGE_LIMIT_REACHED,
        "timeout",
        "failed",
        "error",
        "stalled",
    }
)


@dataclass(frozen=True)
class AuditCoverageGap:
    """One benchmark target missing a scored audit for an auditor."""

    auditor_slug: str
    target_slug: str
    reason: str


def audit_dispatch_needed(
    *,
    report_path: Path,
    audit_result_path: Path,
    force: bool,
) -> bool:
    """True when the auditor LLM should run (or re-run) for this target."""
    if force:
        return True
    if not audit_report_is_complete(report_path):
        return True
    if not audit_result_path.is_file():
        return False
    try:
        payload = json.loads(audit_result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    status = payload.get("status")
    if status in _RETRYABLE_AUDIT_STATUSES:
        return True
    return False


def find_audit_coverage_gaps(
    *,
    benchmark_results_dir: Path,
    audit_results_dir: Path,
    auditor_slugs: list[str],
    required_targets: list[dict],
) -> list[AuditCoverageGap]:
    """List benchmark targets that lack a parseable ``report.md`` per auditor."""
    gaps: list[AuditCoverageGap] = []
    for auditor_slug in auditor_slugs:
        for target in required_targets:
            target_slug = str(target["slug"])
            report_path = audit_report_md(
                audit_results_dir, auditor_slug, target_slug
            )
            if audit_report_is_complete(report_path):
                continue
            result_path = audit_result_json(
                audit_results_dir, auditor_slug, target_slug
            )
            if report_path.is_file():
                reason = "report.md missing parseable total score"
            elif result_path.is_file():
                try:
                    status = json.loads(result_path.read_text(encoding="utf-8")).get(
                        "status", "unknown"
                    )
                except (json.JSONDecodeError, OSError):
                    status = "invalid result.json"
                reason = f"no report.md (last audit status={status})"
            else:
                reason = "never audited"
            gaps.append(
                AuditCoverageGap(
                    auditor_slug=auditor_slug,
                    target_slug=target_slug,
                    reason=reason,
                )
            )
    return gaps


def format_coverage_gaps(gaps: list[AuditCoverageGap]) -> str:
    if not gaps:
        return ""
    lines = [
        "Audit coverage incomplete — every results/ target needs a scored report.md:",
    ]
    for gap in gaps:
        lines.append(
            f"  - {gap.auditor_slug}/{gap.target_slug}: {gap.reason}"
        )
    lines.append(
        "Re-run: python scripts/run_audit.py --model <auditor> "
        "(add --force to redo finished audits)."
    )
    return "\n".join(lines)
