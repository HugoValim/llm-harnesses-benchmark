"""Regression tests for audit coverage enforcement."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_coverage import (  # noqa: E402
    audit_dispatch_needed,
    find_audit_coverage_gaps,
)
from benchmark.audit_report import audit_report_is_complete  # noqa: E402
from benchmark.util import USAGE_LIMIT_REACHED  # noqa: E402


def test_audit_report_is_complete_requires_parseable_total(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("Total score: **88 / 100**\n")
    assert audit_report_is_complete(report)

    report.write_text("Total score: ~92 / 100 (A-tier)\n")
    assert not audit_report_is_complete(report)


def test_audit_dispatch_needed_retries_usage_limit_without_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"status": USAGE_LIMIT_REACHED}))
    assert audit_dispatch_needed(
        report_path=report, audit_result_path=result, force=False
    )


def test_audit_dispatch_needed_skips_complete_report(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("C. **Total score: 90 / 100**\n")
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"status": "completed"}))
    assert not audit_dispatch_needed(
        report_path=report, audit_result_path=result, force=False
    )


def test_find_audit_coverage_gaps_lists_missing_targets(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "results"
    audit_dir = tmp_path / "audit-reports"
    (benchmark_dir / "opencode-foo" / "project").mkdir(parents=True)
    (benchmark_dir / "claude-bar" / "project").mkdir(parents=True)
    done = audit_dir / "auditor" / "opencode-foo" / "report.md"
    done.parent.mkdir(parents=True)
    done.write_text("Total score: **80 / 100**\n")

    gaps = find_audit_coverage_gaps(
        benchmark_results_dir=benchmark_dir,
        audit_results_dir=audit_dir,
        auditor_slugs=["auditor"],
        required_targets=[
            {"slug": "opencode-foo"},
            {"slug": "claude-bar"},
        ],
    )
    assert len(gaps) == 1
    assert gaps[0].target_slug == "claude-bar"
    assert gaps[0].reason == "never audited"
