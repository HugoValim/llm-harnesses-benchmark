"""Validate audit outputs under ``audit-reports/<auditor>/<target>/``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.audit_coverage import AuditCoverageGap, find_audit_coverage_gaps
from benchmark.audit_finalize import INCOMPLETE_REPORT_STATUS
from benchmark.audit_report import NUM_DIMENSIONS, audit_report_is_complete, parse_report_scores
from benchmark.pricing import validate_section_h_cost
from benchmark.result_layout import (
    REPLICATE_DIR_PATTERN,
    audit_generation_metrics_json,
    audit_report_md,
    audit_result_json,
    benchmark_target_slug_from_leaf,
    discover_benchmark_target_dirs,
    parse_benchmark_target_path,
)
from benchmark.run_status import USAGE_LIMIT_REACHED
from benchmark.util import load_json


@dataclass(frozen=True)
class AuditValidationIssue:
    code: str
    message: str


@dataclass
class AuditValidationResult:
    ok: bool
    auditor_slug: str
    target_slug: str
    leaf_dir: Path
    issues: list[AuditValidationIssue] = field(default_factory=list)
    parsed_total: int | None = None
    parsed_tier: str | None = None
    dimension_count: int = 0
    audit_status: str | None = None

    def summary(self) -> str:
        if self.ok:
            parts = [f"total={self.parsed_total}"]
            if self.parsed_tier:
                parts.append(f"tier={self.parsed_tier}")
            if self.dimension_count < NUM_DIMENSIONS:
                parts.append(f"dims={self.dimension_count}/{NUM_DIMENSIONS}")
            return ", ".join(parts)
        return "; ".join(f"{i.code}: {i.message}" for i in self.issues)


def discover_benchmark_targets(projects_root: Path) -> list[dict[str, Any]]:
    """Return minimal target rows for every benchmark replicate leaf on disk."""
    targets: list[dict[str, Any]] = []
    for entry in discover_benchmark_target_dirs(projects_root):
        slug = benchmark_target_slug_from_leaf(entry, projects_root)
        parsed = parse_benchmark_target_path(slug)
        targets.append(
            {
                "slug": slug,
                "target_group": parsed.target_group,
                "replicate_id": parsed.replicate_id,
                "model_slug": parsed.model_slug,
                "harness": parsed.harness or "unknown",
                "project_dir": entry / "project",
            }
        )
    return targets


def discover_audit_leaves(audit_root: Path, auditor_slug: str) -> list[Path]:
    """Return audit replicate dirs that contain ``report.md`` or ``result.json``."""
    auditor_dir = audit_root / auditor_slug
    if not auditor_dir.is_dir():
        return []
    seen: set[Path] = set()
    leaves: list[Path] = []
    for pattern in ("**/report.md", "**/result.json"):
        for path in sorted(auditor_dir.glob(pattern)):
            leaf = path.parent.resolve()
            if leaf in seen:
                continue
            seen.add(leaf)
            leaves.append(leaf)
    return sorted(leaves, key=lambda p: p.as_posix())


def audit_target_slug_from_leaf(leaf_dir: Path, auditor_dir: Path) -> str:
    """Return ``target_group/run_XX`` or bare target dirname for one audit leaf."""
    return leaf_dir.relative_to(auditor_dir).as_posix()


def audit_leaf_matches_only(
    leaf_dir: Path,
    auditor_dir: Path,
    only: set[str],
) -> bool:
    """True when ``leaf_dir`` matches a ``--only`` target selector."""
    slug = audit_target_slug_from_leaf(leaf_dir, auditor_dir)
    if slug in only:
        return True
    if leaf_dir.name in only:
        return True
    if REPLICATE_DIR_PATTERN.match(leaf_dir.name):
        target_group = leaf_dir.parent.name
        full_slug = f"{target_group}/{leaf_dir.name}"
        return target_group in only or full_slug in only
    return leaf_dir.name in only


def validate_audit_leaf(
    *,
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    leaf_dir: Path | None = None,
    require_generation_metrics: bool = True,
    require_full_rubric: bool = False,
) -> AuditValidationResult:
    """Validate one (auditor, target) audit output directory."""
    report_path = audit_report_md(audit_root, auditor_slug, target_slug)
    result_path = audit_result_json(audit_root, auditor_slug, target_slug)
    metrics_path = audit_generation_metrics_json(
        audit_root, auditor_slug, target_slug
    )
    resolved_leaf = leaf_dir or report_path.parent
    result = AuditValidationResult(
        ok=False,
        auditor_slug=auditor_slug,
        target_slug=target_slug,
        leaf_dir=resolved_leaf,
    )

    payload: dict[str, Any] | None = None
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            status = payload.get("status")
            if isinstance(status, str):
                result.audit_status = status
        except (json.JSONDecodeError, OSError) as exc:
            result.issues.append(
                AuditValidationIssue("invalid_result_json", str(exc))
            )

    if not report_path.is_file():
        if payload and result.audit_status == USAGE_LIMIT_REACHED:
            result.issues.append(
                AuditValidationIssue(
                    USAGE_LIMIT_REACHED,
                    "no report.md (provider usage limit reached)",
                )
            )
        elif payload and result.audit_status == INCOMPLETE_REPORT_STATUS:
            result.issues.append(
                AuditValidationIssue(
                    INCOMPLETE_REPORT_STATUS,
                    "no report.md (auditor finished without a rubric report)",
                )
            )
        elif payload and result.audit_status:
            result.issues.append(
                AuditValidationIssue(
                    "missing_report",
                    f"no report.md (last audit status={result.audit_status})",
                )
            )
        else:
            result.issues.append(
                AuditValidationIssue("missing_report", "report.md not found")
            )
        return result

    if not audit_report_is_complete(report_path):
        result.issues.append(
            AuditValidationIssue(
                "unparseable_report",
                "report.md missing parseable total score",
            )
        )
        if result.audit_status == INCOMPLETE_REPORT_STATUS:
            result.issues.append(
                AuditValidationIssue(
                    INCOMPLETE_REPORT_STATUS,
                    "auditor run marked incomplete_report",
                )
            )
        return result

    try:
        parsed = parse_report_scores(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        result.issues.append(AuditValidationIssue("read_report", str(exc)))
        return result

    result.parsed_total = parsed.total
    result.parsed_tier = parsed.tier
    result.dimension_count = len(parsed.dimensions)

    if require_full_rubric and result.dimension_count < NUM_DIMENSIONS:
        result.issues.append(
            AuditValidationIssue(
                "incomplete_rubric",
                f"expected {NUM_DIMENSIONS} dimension rows, found "
                f"{result.dimension_count}",
            )
        )

    if require_generation_metrics and not metrics_path.is_file():
        result.issues.append(
            AuditValidationIssue(
                "missing_generation_metrics",
                "generation-metrics.json not found",
            )
        )
    elif metrics_path.is_file():
        try:
            metrics = load_json(metrics_path)
        except (json.JSONDecodeError, OSError) as exc:
            result.issues.append(
                AuditValidationIssue("invalid_generation_metrics", str(exc))
            )
            metrics = None
        if isinstance(metrics, dict):
            for message in validate_section_h_cost(
                report_path.read_text(encoding="utf-8"),
                metrics,
            ):
                result.issues.append(
                    AuditValidationIssue("section_h_mismatch", message)
                )

    result.ok = not result.issues
    return result


def coverage_gaps_for_auditors(
    *,
    projects_root: Path,
    audit_root: Path,
    auditor_slugs: list[str],
    required_targets: list[dict[str, Any]] | None = None,
) -> list[AuditCoverageGap]:
    """Return audit coverage gaps for the selected auditor slug(s)."""
    targets = required_targets or discover_benchmark_targets(projects_root)
    gaps: list[AuditCoverageGap] = []
    for auditor_slug in auditor_slugs:
        gaps.extend(
            find_audit_coverage_gaps(
                benchmark_results_dir=projects_root,
                audit_results_dir=audit_root,
                auditor_slugs=[auditor_slug],
                required_targets=targets,
            )
        )
    return gaps
