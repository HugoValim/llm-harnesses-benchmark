"""Regression tests for audit validation helpers and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

TEST_AUDITOR = "codex_gpt_5_5"

from benchmark.audit_validation import (  # noqa: E402
    coverage_gaps_for_auditors,
    validate_audit_leaf,
)
from benchmark.util import USAGE_LIMIT_REACHED  # noqa: E402


def _write_complete_report(report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "A. **Quick Summary**",
                "Looks good.",
                "",
                "B. **Scores Per Dimension**",
                "| # | Dimension | Score / Max | Justification |",
                "|---|---|---:|---|",
                "| 1 | D1 Deliverable completeness | 10 / 15 | ok |",
                "",
                "C. **Total score / 100** — **80 / 100**",
                "",
                "D. **Practical tier**",
                "B (61-80): close.",
            ]
        )
        + "\n"
    )


def test_validate_audit_leaf_passes_complete_report(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit-reports"
    auditor = "codex_gpt_5_5"
    target = "opencode-foo/run_01"
    report = audit_root / auditor / target / "report.md"
    _write_complete_report(report)
    metrics = audit_root / auditor / target / "generation-metrics.json"
    metrics.write_text(json.dumps({"estimated_cost_usd": None}))

    result = validate_audit_leaf(
        audit_root=audit_root,
        auditor_slug=auditor,
        target_slug=target,
    )
    assert result.ok
    assert result.parsed_total == 80


def test_validate_audit_leaf_fails_unparseable_report(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit-reports"
    auditor = "codex_gpt_5_5"
    target = "opencode-foo/run_01"
    report = audit_root / auditor / target / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("Thinking aloud about the project.\n")
    result_path = report.parent / "result.json"
    result_path.write_text(json.dumps({"status": "incomplete_report"}))

    result = validate_audit_leaf(
        audit_root=audit_root,
        auditor_slug=auditor,
        target_slug=target,
    )
    assert not result.ok
    assert any(issue.code == "unparseable_report" for issue in result.issues)


def test_validate_audit_leaf_flags_usage_limit_without_report(
    tmp_path: Path,
) -> None:
    audit_root = tmp_path / "audit-reports"
    auditor = "codex_gpt_5_5"
    target = "claude-bar/run_01"
    leaf = audit_root / auditor / target
    leaf.mkdir(parents=True)
    (leaf / "result.json").write_text(json.dumps({"status": USAGE_LIMIT_REACHED}))

    result = validate_audit_leaf(
        audit_root=audit_root,
        auditor_slug=auditor,
        target_slug=target,
    )
    assert not result.ok
    assert any(issue.code == USAGE_LIMIT_REACHED for issue in result.issues)


def test_coverage_gaps_for_auditors_lists_missing_targets(tmp_path: Path) -> None:
    projects_root = tmp_path / "results" / "run_02" / "projects"
    audit_root = tmp_path / "results" / "run_02" / "audit-reports"
    (projects_root / "opencode-foo" / "run_01" / "project").mkdir(parents=True)
    (projects_root / "claude-bar" / "run_01" / "project").mkdir(parents=True)
    _write_complete_report(audit_root / "auditor" / "opencode-foo" / "run_01" / "report.md")

    gaps = coverage_gaps_for_auditors(
        projects_root=projects_root,
        audit_root=audit_root,
        auditor_slugs=["auditor"],
        required_targets=[
            {"slug": "opencode-foo/run_01"},
            {"slug": "claude-bar/run_01"},
        ],
    )
    assert len(gaps) == 1
    assert gaps[0].target_slug == "claude-bar/run_01"


def test_validate_audits_cli_passes_complete_leaf(tmp_path: Path) -> None:
    results_base = tmp_path / "results"
    projects_root = results_base / "run_02" / "projects"
    audit_root = results_base / "run_02" / "audit-reports"
    (projects_root / "opencode-demo" / "run_01" / "project").mkdir(parents=True)
    _write_complete_report(
        audit_root / TEST_AUDITOR / "opencode-demo" / "run_01" / "report.md"
    )
    metrics = (
        audit_root / TEST_AUDITOR / "opencode-demo" / "run_01" / "generation-metrics.json"
    )
    metrics.write_text(json.dumps({"estimated_cost_usd": None}))

    script = REPO_ROOT / "scripts" / "validate_audits.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--run-id",
            "run_02",
            "--auditor",
            TEST_AUDITOR,
            "--no-enforce-coverage",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"[PASS] {TEST_AUDITOR}/opencode-demo/run_01" in completed.stdout


def test_validate_audits_cli_reports_coverage_gaps(tmp_path: Path) -> None:
    results_base = tmp_path / "results"
    projects_root = results_base / "run_02" / "projects"
    audit_root = results_base / "run_02" / "audit-reports"
    (projects_root / "opencode-demo" / "run_01" / "project").mkdir(parents=True)
    (projects_root / "claude-demo" / "run_01" / "project").mkdir(parents=True)
    _write_complete_report(
        audit_root / TEST_AUDITOR / "opencode-demo" / "run_01" / "report.md"
    )

    script = REPO_ROOT / "scripts" / "validate_audits.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--run-id",
            "run_02",
            "--auditor",
            TEST_AUDITOR,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert "coverage_gaps=" in completed.stdout
    assert f"[GAP] {TEST_AUDITOR}/claude-demo/run_01" in completed.stdout


def test_validate_audits_brief_output_omits_issue_details(tmp_path: Path) -> None:
    results_base = tmp_path / "results"
    projects_root = results_base / "run_02" / "projects"
    audit_root = results_base / "run_02" / "audit-reports"
    (projects_root / "opencode-demo" / "run_01" / "project").mkdir(parents=True)
    report = audit_root / TEST_AUDITOR / "opencode-demo" / "run_01" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("no score here\n")

    script = REPO_ROOT / "scripts" / "validate_audits.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--run-id",
            "run_02",
            "--auditor",
            TEST_AUDITOR,
            "--no-enforce-coverage",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert f"[FAIL] {TEST_AUDITOR}/opencode-demo/run_01" in completed.stdout
    assert "unparseable_report" not in completed.stdout


def test_validate_audits_failed_count_not_doubled(tmp_path: Path) -> None:
    results_base = tmp_path / "results"
    projects_root = results_base / "run_02" / "projects"
    audit_root = results_base / "run_02" / "audit-reports"
    (projects_root / "opencode-ok" / "run_01" / "project").mkdir(parents=True)
    (projects_root / "claude-bad" / "run_01" / "project").mkdir(parents=True)
    _write_complete_report(
        audit_root / TEST_AUDITOR / "opencode-ok" / "run_01" / "report.md"
    )
    metrics = (
        audit_root / TEST_AUDITOR / "opencode-ok" / "run_01" / "generation-metrics.json"
    )
    metrics.write_text(json.dumps({"estimated_cost_usd": None}))
    bad_report = audit_root / TEST_AUDITOR / "claude-bad" / "run_01" / "report.md"
    bad_report.parent.mkdir(parents=True)
    bad_report.write_text("Thinking aloud about the project.\n")

    script = REPO_ROOT / "scripts" / "validate_audits.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--run-id",
            "run_02",
            "--auditor",
            TEST_AUDITOR,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert "coverage_gaps=1" in completed.stdout
    assert "failed=1" in completed.stdout
    assert "failed=2" not in completed.stdout


def test_validate_audits_verbose_includes_issue_details(tmp_path: Path) -> None:
    results_base = tmp_path / "results"
    projects_root = results_base / "run_02" / "projects"
    audit_root = results_base / "run_02" / "audit-reports"
    (projects_root / "opencode-demo" / "run_01" / "project").mkdir(parents=True)
    report = audit_root / TEST_AUDITOR / "opencode-demo" / "run_01" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("no score here\n")

    script = REPO_ROOT / "scripts" / "validate_audits.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--run-id",
            "run_02",
            "--auditor",
            TEST_AUDITOR,
            "--no-enforce-coverage",
            "--verbose",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert "unparseable_report" in completed.stdout
