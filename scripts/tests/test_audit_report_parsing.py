"""Regression tests for audit report total and D10 parsing."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import parse_report_scores  # noqa: E402


def test_parse_section_c_multiline_total() -> None:
    text = """
## C. Total score / 100

**95 / 100**
"""
    report = parse_report_scores(text, target="codex-foo")
    assert report.total == 95


def test_parse_section_c_inline_total() -> None:
    text = "C. **Total score / 100** — **91 / 100**"
    report = parse_report_scores(text, target="cursor-bar")
    assert report.total == 91


def test_parse_d10_dimension_row() -> None:
    text = """
| 10 | Code quality (tool-backed) | 9 / 10 | static-analysis.json:ruff.total_errors=0 |
"""
    report = parse_report_scores(text, target="claude-baz")
    assert len(report.dimensions) == 1
    assert report.dimensions[0].index == 10
    assert report.dimensions[0].score == 9


def test_kimi_cohort_reports_parse_totals() -> None:
    root = REPO_ROOT / "audit-reports" / "kimi_k2_6_ollama_cloud"
    if not root.is_dir():
        return
    reports = list(root.glob("*/report.md"))
    if not reports:
        return
    parsed = sum(
        1 for p in reports if parse_report_scores(p.read_text()).total is not None
    )
    assert parsed >= len(reports) * 0.9
