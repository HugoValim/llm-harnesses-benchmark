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
    enrich_cursor_result_row,
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


def test_extract_token_totals_cursor_model_usage() -> None:
    tokens = extract_token_totals(
        {
            "model_usage": {
                "composer-2.5": {
                    "inputTokens": 10_000,
                    "outputTokens": 2_000,
                    "cacheReadInputTokens": 100_000,
                }
            }
        },
        harness="cursor",
    )
    assert tokens.input_tokens == 10_000
    assert tokens.output_tokens == 2_000
    assert tokens.cache_read_tokens == 100_000


def test_enrich_cursor_result_row_from_streams() -> None:
    repo_result = REPO_ROOT / "results" / "cursor-composer_2_5" / "result.json"
    if not repo_result.is_file():
        pytest.skip("cursor-composer_2_5 benchmark result not present")
    row = load_json(repo_result)
    assert "model_usage" not in row or not row.get("model_usage")
    enriched = enrich_cursor_result_row(
        row, benchmark_result_path=repo_result
    )
    usage = enriched["model_usage"]["composer-2.5"]
    assert usage["inputTokens"] == 72_370
    assert usage["outputTokens"] == 21_772
    metrics = build_generation_metrics(
        target_slug="cursor-composer_2_5",
        model_slug="composer_2_5",
        harness="cursor",
        benchmark_result_path=repo_result,
    )
    assert metrics["cost_source"] == "computed"
    assert metrics["input_tokens"] == 72_370
    assert metrics["estimated_cost_usd"] is not None
    assert metrics["estimated_cost_usd"] > 0


def test_build_generation_metrics_includes_harness_cli_version(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "elapsed_seconds": 10,
                "tokens": {"input": 1, "output": 1, "total": 2},
                "harness_cli_version": "claude 2.0.0",
                "harness_cli_probe_argv": ["claude", "--version"],
                "command_shim_version": "ollama 0.5.0",
                "command_shim_probe_argv": ["ollama", "--version"],
            }
        )
    )
    metrics = build_generation_metrics(
        target_slug="claude-claude_sonnet_4_6",
        model_slug="claude_sonnet_4_6",
        harness="claude",
        benchmark_result_path=result_path,
    )
    assert metrics["harness_cli_version"] == "claude 2.0.0"
    assert metrics["command_shim_version"] == "ollama 0.5.0"


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


def test_format_generation_metrics_block_includes_cli_versions() -> None:
    block = format_generation_metrics_block(
        {
            "model_slug": "kimi_k2_6_claude",
            "harness": "claude",
            "harness_cli_version": "claude 2.0.0",
            "command_shim_version": "ollama 0.5.0",
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
    assert "Harness-CLI-Version: claude 2.0.0" in block
    assert "Command-Shim-Version: ollama 0.5.0" in block


def test_format_generation_metrics_block_includes_cost() -> None:
    block = format_generation_metrics_block(
        {
            "model_slug": "kimi_k2_6_claude",
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
