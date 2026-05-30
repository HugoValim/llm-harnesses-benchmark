"""Regression tests for leader-relative normalization in audit_report."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    DEFAULT_DIMENSION_LABELS,
    NUM_DIMENSIONS,
    DimensionScore,
    ParsedReport,
    _is_leader_slug,
    _leader_ceiling,
    _normalized_scores_section,
)
from benchmark.audit_rollup import _cross_harness_cohort_slugs  # noqa: E402


def test_cross_harness_cohort_excludes_single_harness_leaders() -> None:
    def row(harness: str, slug: str) -> ParsedReport:
        return ParsedReport(
            auditor="a",
            target=f"{harness}-{slug}",
            harness=harness,
            model_slug=slug,
            total=80,
        )

    reports = [
        row("codex", "codex_gpt_5_5"),
        row("claude", "claude_opus_4_7"),
        row("codex", "glm_5_1_codex"),
        row("claude", "glm_5_1_claude"),
        row("opencode", "glm_5_1_opencode"),
    ]
    assert _cross_harness_cohort_slugs(reports) == frozenset({"glm_5_1"})


def test_is_leader_slug_positive() -> None:
    assert _is_leader_slug("gpt_5_5")
    assert _is_leader_slug("GPT_5_5")
    assert _is_leader_slug("codex_gpt_5_5_ollama_cloud")
    assert _is_leader_slug("claude_opus_4_7")
    assert _is_leader_slug("CLAUDE_OPUS_4_7")


def test_is_leader_slug_negative() -> None:
    assert not _is_leader_slug("kimi_k2_6")
    assert not _is_leader_slug("claude_sonnet_4_6")


def test_leader_ceiling_no_leaders() -> None:
    reports = [
        ParsedReport(
            auditor="a",
            target="claude-foo",
            harness="claude",
            model_slug="foo",
            total=50,
        )
    ]
    c = _leader_ceiling(reports)
    assert c["total"] is None
    assert all(c[str(i)] is None for i in range(1, NUM_DIMENSIONS + 1))


def test_leader_ceiling_with_leaders() -> None:
    reports = [
        ParsedReport(
            auditor="a",
            target="claude-gpt_5_5",
            harness="claude",
            model_slug="gpt_5_5",
            total=80,
            dimensions=[DimensionScore(1, "D1", 20, 25)],
        ),
        ParsedReport(
            auditor="a",
            target="codex-gpt_5_5",
            harness="codex",
            model_slug="gpt_5_5",
            total=100,
            dimensions=[DimensionScore(1, "D1", 10, 25)],
        ),
    ]
    c = _leader_ceiling(reports)
    assert c["total"] == 90.0
    assert c["1"] == 15.0


def test_normalized_scores_section_no_leaders() -> None:
    reports = [
        ParsedReport(
            auditor="x",
            target="claude-kimi_k2_6",
            harness="claude",
            model_slug="kimi_k2_6",
            total=70,
        )
    ]
    lines = _normalized_scores_section(reports, list(DEFAULT_DIMENSION_LABELS))
    text = "\n".join(lines)
    assert "no leader runs found" in text


def test_normalized_scores_section_with_leaders() -> None:
    dim_labels = list(DEFAULT_DIMENSION_LABELS)
    dims_leader = [
        DimensionScore(i, f"D{i}", 10, 10) for i in range(1, NUM_DIMENSIONS + 1)
    ]
    dims_other = [
        DimensionScore(i, f"D{i}", 5, 10) for i in range(1, NUM_DIMENSIONS + 1)
    ]
    reports = [
        ParsedReport(
            auditor="a",
            target="claude-gpt_5_5",
            harness="claude",
            model_slug="gpt_5_5",
            total=100,
            dimensions=dims_leader,
        ),
        ParsedReport(
            auditor="a",
            target="claude-kimi_k2_6",
            harness="claude",
            model_slug="kimi_k2_6",
            total=50,
            dimensions=dims_other,
        ),
    ]
    lines = _normalized_scores_section(reports, dim_labels)
    text = "\n".join(lines)
    assert "Benchmark leaders" in text
    assert "Non-leader models" in text
    assert "kimi_k2_6" in text
    assert "50.0" in text
    assert "50.0%" in text or "50%" in text
