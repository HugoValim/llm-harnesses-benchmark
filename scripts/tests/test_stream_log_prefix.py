"""Tests for live benchmark stream log labels."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import stream_log_prefix  # noqa: E402


def test_stream_log_prefix_harness_model() -> None:
    assert stream_log_prefix("opencode", "minimax_m2_7_ollama_cloud") == (
        "opencode:minimax_m2_7_ollama_cloud"
    )


def test_stream_log_prefix_includes_phase() -> None:
    assert stream_log_prefix("opencode", "minimax_m2_7_ollama_cloud", "phase1") == (
        "opencode:minimax_m2_7_ollama_cloud/phase1"
    )


def test_stream_log_prefix_phase2() -> None:
    assert stream_log_prefix("claude", "kimi_k2_6_ollama_cloud", "phase2") == (
        "claude:kimi_k2_6_ollama_cloud/phase2"
    )
