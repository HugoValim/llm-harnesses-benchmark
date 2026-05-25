"""Tests for the RubricResult public entry points."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    RubricResult,
    iter_rubric_results,
    load_rubric_result,
)


def _write_report(target_dir: Path, total: int, tier: str = "A") -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"Total score: **{total} / 100**", f"Practical tier: **{tier}**"]
    for i in range(1, 11):
        lines.append(f"| {i} | D{i} label | 5/10 | notes |")
    target_dir.joinpath("report.md").write_text("\n".join(lines))


def test_load_rubric_result(tmp_path: Path) -> None:
    auditor_dir = tmp_path / "auditor_x"
    target_dir = auditor_dir / "claude-foo"
    _write_report(target_dir, 75, "B")
    result = load_rubric_result(target_dir / "report.md")
    assert isinstance(result, RubricResult)
    assert result.total == 75
    assert result.tier == "B"
    assert result.harness == "claude"
    assert result.model_slug == "foo"
    assert len(result.dimensions) == 10


def test_iter_rubric_results(tmp_path: Path) -> None:
    _write_report(tmp_path / "claude-foo", 80)
    _write_report(tmp_path / "claude-bar", 90)
    results = list(iter_rubric_results(tmp_path))
    assert len(results) == 2
    assert all(isinstance(r, RubricResult) for r in results)
    assert {r.model_slug for r in results} == {"foo", "bar"}
