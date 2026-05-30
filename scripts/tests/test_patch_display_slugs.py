"""Tests for patch_display_slugs meta-analysis patching."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from patch_display_slugs import patch_meta_analysis_text  # noqa: E402


def test_patch_meta_analysis_preserves_path_segments() -> None:
    text = "\n".join(
        [
            "# Meta-analysis: codex_gpt_5_5 audit reports",
            "",
            "See `audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro/report.md`.",
            "",
            "| 1 | codex | codex_gpt_5_5 | 86.0 | A |",
            "",
            "Leader `codex_gpt_5_5` scored 86 under codex.",
            "Target `codex-codex_gpt_5_5` is the self-run.",
        ]
    )
    display_map = {"codex_gpt_5_5": "codex_gpt_5_5(xhigh)"}
    patched = patch_meta_analysis_text(text, display_map)
    assert "# Meta-analysis: codex_gpt_5_5(xhigh) audit reports" in patched
    assert "audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro" in patched
    assert "| 1 | codex | codex_gpt_5_5(xhigh) | 86.0 | A |" in patched
    assert "Leader `codex_gpt_5_5(xhigh)` scored 86" in patched
    assert "`codex-codex_gpt_5_5`" in patched
