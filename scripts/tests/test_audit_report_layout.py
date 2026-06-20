"""Regression tests for audit report directory layout helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_layout import (  # noqa: E402
    auditor_dir_has_reports,
    iter_auditor_report_paths,
    iter_target_group_report_paths,
)
from run_audit import _auditor_dirs_for_comparison_rollup  # noqa: E402

_SAMPLE_REPORT = "C. **Total score / 100** — **80 / 100**\n"


def _write_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SAMPLE_REPORT, encoding="utf-8")


def test_iter_target_group_report_paths_flat_layout(tmp_path: Path) -> None:
    report = tmp_path / "opencode-foo" / "report.md"
    _write_report(report)

    assert list(iter_target_group_report_paths(tmp_path / "opencode-foo")) == [
        report
    ]


def test_iter_target_group_report_paths_replicate_layout(tmp_path: Path) -> None:
    report = tmp_path / "opencode-foo" / "run_01" / "report.md"
    _write_report(report)

    assert list(iter_target_group_report_paths(tmp_path / "opencode-foo")) == [
        report
    ]


def test_iter_target_group_report_paths_prefers_flat_over_replicate(
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "opencode-foo"
    flat = target_dir / "report.md"
    nested = target_dir / "run_01" / "report.md"
    _write_report(flat)
    _write_report(nested)

    assert list(iter_target_group_report_paths(target_dir)) == [flat]


def test_auditor_dir_has_reports_nested_replicate_layout(tmp_path: Path) -> None:
    auditor_dir = tmp_path / "composer_2_5"
    _write_report(auditor_dir / "opencode-foo" / "run_01" / "report.md")

    assert auditor_dir_has_reports(auditor_dir)


def test_auditor_dir_has_reports_empty_auditor_dir(tmp_path: Path) -> None:
    auditor_dir = tmp_path / "composer_2_5"
    auditor_dir.mkdir()

    assert not auditor_dir_has_reports(auditor_dir)


def test_iter_auditor_report_paths_collects_all_replicates(tmp_path: Path) -> None:
    auditor_dir = tmp_path / "composer_2_5"
    run_01 = auditor_dir / "opencode-foo" / "run_01" / "report.md"
    run_02 = auditor_dir / "opencode-foo" / "run_02" / "report.md"
    _write_report(run_01)
    _write_report(run_02)

    assert list(iter_auditor_report_paths(auditor_dir)) == [run_01, run_02]


def test_auditor_dirs_for_comparison_rollup_finds_nested_reports(
    tmp_path: Path,
) -> None:
    auditor_dir = tmp_path / "composer_2_5"
    _write_report(auditor_dir / "opencode-foo" / "run_01" / "report.md")
    auditors = [{"slug": "composer_2_5"}]

    rollup_dirs = _auditor_dirs_for_comparison_rollup(
        tmp_path,
        auditors,
        report_only=False,
        wanted_model="composer_2_5",
    )

    assert rollup_dirs == [auditor_dir]


@pytest.mark.parametrize(
    "auditor_root",
    [
        REPO_ROOT / "results" / "run_02" / "audit-reports" / "composer_2_5",
    ],
)
def test_run_02_composer_auditor_tree_has_reports(auditor_root: Path) -> None:
    if not auditor_root.is_dir():
        pytest.skip(f"{auditor_root} not present")
    assert auditor_dir_has_reports(auditor_root)
    assert list(iter_auditor_report_paths(auditor_root))
