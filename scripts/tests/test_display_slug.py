"""Tests for model display slug formatting."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import (  # noqa: E402
    build_display_slug_map,
    display_slug_for,
    format_display_slug,
    registry_by_slug,
)


def test_format_display_slug_without_effort() -> None:
    assert format_display_slug("claude_sonnet_4_6") == "claude_sonnet_4_6"


def test_format_display_slug_with_effort() -> None:
    assert format_display_slug("codex_gpt_5_5", codex_reasoning_effort="xhigh") == (
        "codex_gpt_5_5(xhigh)"
    )


def test_registry_by_slug_indexes_models() -> None:
    models = [
        {"slug": "codex_gpt_5_5", "codex_reasoning_effort": "xhigh"},
        {"slug": "claude_sonnet_4_6"},
    ]
    registry = registry_by_slug(models)
    assert set(registry) == {"codex_gpt_5_5", "claude_sonnet_4_6"}


def test_display_slug_for_annotates_effort() -> None:
    registry = registry_by_slug(
        [{"slug": "codex_gpt_5_5", "codex_reasoning_effort": "xhigh"}]
    )
    assert display_slug_for(registry, "codex_gpt_5_5") == "codex_gpt_5_5(xhigh)"
    assert display_slug_for(registry, "unknown") == "unknown"


def test_build_display_slug_map_from_models_json() -> None:
    display_map = build_display_slug_map(REPO_ROOT / "config" / "models.json")
    assert display_map["codex_gpt_5_5"] == "codex_gpt_5_5(xhigh)"
    assert display_map["claude_opus_4_7"] == "claude_opus_4_7"
    assert display_map["claude_opus_4_8"] == "claude_opus_4_8"


def test_all_runs_ranking_table_shows_reasoning_effort() -> None:
    from benchmark.audit_report import ParsedReport  # noqa: PLC0415
    from benchmark.audit_rollup import build_all_runs_ranking_table  # noqa: PLC0415

    reports = [
        ParsedReport(
            auditor="codex_gpt_5_5",
            target="codex-codex_gpt_5_5",
            harness="codex",
            model_slug="codex_gpt_5_5",
            total=86,
            tier="A",
        )
    ]
    display_map = {"codex_gpt_5_5": "codex_gpt_5_5(xhigh)"}
    table = build_all_runs_ranking_table(reports, display_slug_map=display_map)
    assert "codex_gpt_5_5(xhigh)" in table
    assert "| codex | codex_gpt_5_5(xhigh) |" in table
