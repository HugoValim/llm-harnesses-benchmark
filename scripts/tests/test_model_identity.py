"""Tests for benchmark.model_identity public slug helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.model_identity import cohort_slug  # noqa: E402


@pytest.mark.parametrize(
    ("model_slug", "expected"),
    [
        ("glm_5_1_claude", "glm_5_1"),
        ("glm_5_1_codex", "glm_5_1"),
        ("glm_5_1_opencode", "glm_5_1"),
        ("claude_opus_4_7", "claude_opus_4_7"),
        ("claude_opus_4_8", "claude_opus_4_8"),
        ("claude_sonnet_4_6_opencode", "claude_sonnet_4_6_opencode"),
    ],
)
def test_cohort_slug(model_slug: str, expected: str) -> None:
    assert cohort_slug(model_slug) == expected
