"""Regression tests for ``expand_ollama_cloud_config``."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import expand_ollama_cloud_config  # noqa: E402


class TestExpandOllamaCloudConfig(unittest.TestCase):
    def test_pass_through_when_not_unified(self) -> None:
        cfg = {"runner": {}, "models": [{"slug": "x", "id": "y"}]}
        self.assertIs(expand_ollama_cloud_config(cfg, "codex"), cfg)

    def test_unified_file_codex_claude_ollama(self) -> None:
        path = REPO_ROOT / "config" / "ollama_cloud_models.json"
        raw = json.loads(path.read_text())
        codex = expand_ollama_cloud_config(raw, "codex")
        self.assertEqual(len(codex["models"]), 9)
        self.assertEqual(codex["models"][0]["runner_type"], "codex")
        self.assertTrue(codex["models"][0]["label"].endswith(" via Codex"))
        by_slug = {m["slug"]: m for m in codex["models"]}
        self.assertEqual(by_slug["gemma4_ollama_cloud"]["id"], "gemma4:31b-cloud")
        self.assertEqual(
            by_slug["gemini_3_flash_preview_ollama_cloud"]["id"],
            "gemini-3-flash-preview:cloud",
        )

        claude = expand_ollama_cloud_config(raw, "claude")
        self.assertEqual(len(claude["variants"]), 9)
        self.assertEqual(claude["variants"][0]["main_model"], "kimi-k2.6:cloud")
        self.assertTrue(claude["variants"][0]["label"].endswith(" via Claude Code"))

        ollama = expand_ollama_cloud_config(raw, "ollama")
        self.assertEqual(ollama["models"][0]["runner_type"], "ollama")

        opencode = expand_ollama_cloud_config(raw, "opencode")
        self.assertEqual(opencode["models"][0]["runner_type"], "opencode")
        self.assertTrue(opencode["models"][0]["label"].endswith(" via OpenCode"))


if __name__ == "__main__":
    unittest.main()
