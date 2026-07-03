"""Tests for subscription provider serialization helpers."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.subscription_providers import (  # noqa: E402
    build_campaign_concurrency_keys,
    build_job_concurrency_keys,
    subscription_provider,
)


def test_subscription_provider_only_for_cli_subscription_rows() -> None:
    assert subscription_provider({"provider": "anthropic"}) == "anthropic"
    assert subscription_provider({"provider": "openai"}) == "openai"
    assert subscription_provider({"provider": "cursor"}) == "cursor"
    assert subscription_provider({"provider": "ollama_cloud"}) is None


def test_build_job_concurrency_keys() -> None:
    assert build_job_concurrency_keys(
        harness="claude",
        model_row={"provider": "anthropic", "slug": "claude_opus_4_8"},
    ) == frozenset({"subscription:anthropic"})
    assert build_job_concurrency_keys(
        harness="opencode",
        model_row={"provider": "ollama_cloud", "slug": "kimi_k2_7"},
    ) == frozenset({"harness:opencode"})


def test_build_campaign_concurrency_keys_adds_model_slug() -> None:
    assert build_campaign_concurrency_keys(
        harness="codex",
        model_row={"provider": "openai", "slug": "codex_gpt_5_5"},
    ) == frozenset({"subscription:openai", "model:codex_gpt_5_5"})
