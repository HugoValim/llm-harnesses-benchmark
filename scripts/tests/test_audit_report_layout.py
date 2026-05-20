"""Tests for audit report directory layout discovery."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    _iter_reports,
    build_comparison_table,
    build_statistical_summary,
)


def _write_report(target_dir: Path, total: int) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.joinpath("report.md").write_text(
        f"Total score: **{total} / 100**\n\nPractical tier: **A**\n"
    )


def test_iter_reports_auditor_scoped_tree(tmp_path: Path) -> None:
    auditor_dir = tmp_path / "kimi_k2_6_ollama_cloud"
    _write_report(auditor_dir / "claude-foo", 80)
    _write_report(auditor_dir / "codex-bar", 90)

    reports = list(_iter_reports(auditor_dir))
    assert len(reports) == 2
    assert {r.target for r in reports} == {"claude-foo", "codex-bar"}
    assert all(r.auditor == "kimi_k2_6_ollama_cloud" for r in reports)


def test_iter_reports_root_tree(tmp_path: Path) -> None:
    _write_report(tmp_path / "auditor_a" / "claude-foo", 70)
    _write_report(tmp_path / "auditor_b" / "codex-bar", 75)

    reports = list(_iter_reports(tmp_path))
    assert len(reports) == 2
    assert {r.auditor for r in reports} == {"auditor_a", "auditor_b"}


def test_build_comparison_from_source_dirs(tmp_path: Path) -> None:
    dir_a = tmp_path / "auditor_a"
    dir_b = tmp_path / "auditor_b"
    _write_report(dir_a / "claude-x", 60)
    _write_report(dir_b / "codex-y", 65)

    table = build_comparison_table(source_dirs=[dir_a, dir_b])
    assert "claude-x" in table
    assert "codex-y" in table
    summary = build_statistical_summary(source_dirs=[dir_a, dir_b])
    assert "Statistical summary" in summary
