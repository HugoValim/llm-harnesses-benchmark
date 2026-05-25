"""Tests for docs/PRICING.md parsing and audit generation metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.pricing import (  # noqa: E402
    PricingError,
    assert_registry_coverage,
    build_generation_metrics,
    compute_estimated_cost,
    extract_token_totals,
    format_generation_metrics_block,
    load_pricing_table,
    pricing_row_for_target,
    validate_section_h_cost,
)
from benchmark.util import load_json  # noqa: E402

MODELS_CONFIG = REPO_ROOT / "config" / "models.json"
PRICING_MD = REPO_ROOT / "docs" / "PRICING.md"


def test_load_pricing_table_covers_all_registry_slugs() -> None:
    models = load_json(MODELS_CONFIG)["models"]
    assert_registry_coverage(models)
    table = load_pricing_table(PRICING_MD)
    assert ("claude_sonnet_4_6", "native") in table
    assert ("composer_2_5", "cursor_list") in table


def test_compute_cost_opencode_tokens() -> None:
    row = pricing_row_for_target("claude_sonnet_4_6", "opencode")
    tokens = extract_token_totals(
        {"tokens": {"input": 1_000_000, "output": 500_000, "total": 1_500_000}},
        harness="opencode",
    )
    cost = compute_estimated_cost(row, tokens)
    assert cost == pytest.approx(3.0 + 7.5)


def test_compute_cost_claude_model_usage() -> None:
    row = pricing_row_for_target("claude_opus_4_7", "claude")
    tokens = extract_token_totals(
        {
            "model_usage": {
                "claude-opus-4-7": {
                    "inputTokens": 2_000_000,
                    "outputTokens": 100_000,
                }
            }
        },
        harness="claude",
    )
    cost = compute_estimated_cost(row, tokens)
    assert cost == pytest.approx(10.0 + 2.5)


def test_compute_cost_composer_cursor_list() -> None:
    row = pricing_row_for_target("composer_2_5", "cursor")
    tokens = extract_token_totals(
        {"tokens": {"input": 15_000_000, "output": 3_000_000, "total": 18_000_000}},
        harness="cursor",
    )
    cost = compute_estimated_cost(row, tokens)
    assert cost == pytest.approx(7.5 + 7.5)


def test_harness_reported_cost_precedence() -> None:
    metrics = build_generation_metrics(
        target_slug="claude-claude_sonnet_4_6",
        model_slug="claude_sonnet_4_6",
        harness="claude",
        benchmark_result_path=None,
    )
    assert metrics["status"] == "missing_benchmark_result"

    result_path = Path("/tmp/pricing-test-result.json")
    payload = {
        "elapsed_seconds": 99.5,
        "tokens": {"input": 1000, "output": 500, "total": 1500},
        "total_cost_usd": 0.042,
        "prompt_sha256": "abc",
    }
    result_path.write_text(json.dumps(payload))
    metrics = build_generation_metrics(
        target_slug="opencode-claude_sonnet_4_6",
        model_slug="claude_sonnet_4_6",
        harness="opencode",
        benchmark_result_path=result_path,
    )
    assert metrics["cost_source"] == "harness_reported"
    assert metrics["estimated_cost_usd"] == 0.042
    result_path.unlink(missing_ok=True)


def test_format_generation_metrics_block_includes_cost() -> None:
    block = format_generation_metrics_block(
        {
            "model_slug": "kimi_k2_6_ollama_cloud",
            "harness": "claude",
            "generation_time_seconds": 120,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.25,
            "pricing_doc": "docs/PRICING.md",
            "pricing_last_updated": "2026-05-25",
            "cost_source": "computed",
            "benchmark_result_path": "/tmp/r.json",
        }
    )
    assert "Estimated-Cost-USD: 0.25" in block
    assert "docs/PRICING.md @ 2026-05-25" in block


def test_validate_section_h_cost_detects_mismatch() -> None:
    metrics = {"estimated_cost_usd": 1.23}
    report = "Estimated-Cost-USD: 2.00"
    issues = validate_section_h_cost(report, metrics)
    assert len(issues) == 1
    assert "1.23" in issues[0]


def test_validate_section_h_cost_ok_when_match() -> None:
    metrics = {"estimated_cost_usd": 1.23}
    report = "Estimated-Cost-USD: 1.23"
    assert validate_section_h_cost(report, metrics) == []


def test_duplicate_slug_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text(
        "Last-Updated: 2026-01-01\n\n"
        "| Slug | Provider | Model ID | Channel | Input $/1M | Output $/1M | "
        "Cache read $/1M | Cache write $/1M | Billable | Source | Snapshot |\n"
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |\n"
        "| a | p | m | native | 1 | 2 | | | yes | s | d |\n"
        "| a | p | m | native | 1 | 2 | | | yes | s | d |\n"
    )
    with pytest.raises(PricingError, match="duplicate"):
        load_pricing_table(bad)
