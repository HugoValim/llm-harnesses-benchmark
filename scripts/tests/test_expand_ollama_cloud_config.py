"""Regression tests for ``expand_ollama_cloud_config``."""

from __future__ import annotations

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

    def test_inline_unified_config_codex_claude_ollama(self) -> None:
        raw = {
            "ollama_cloud": True,
            "runner_configs": {
                "codex": {"command_prefix": ["ollama", "launch", "codex"]},
                "claude": {"command_prefix": ["ollama", "launch", "claude"]},
                "opencode": {"command_prefix": ["ollama", "launch", "opencode"]},
            },
            "models": [
                {
                    "slug": "kimi_k2_6_ollama_cloud",
                    "id": "kimi-k2.6:cloud",
                    "label": "Kimi K2.6",
                    "selection_reason": "Regression fixture.",
                },
                {
                    "slug": "gemma4_ollama_cloud",
                    "id": "gemma4:31b-cloud",
                    "label": "Gemma 4",
                    "selection_reason": "Regression fixture.",
                },
            ],
        }
        codex = expand_ollama_cloud_config(raw, "codex")
        self.assertEqual(len(codex["models"]), 2)
        self.assertEqual(codex["models"][0]["runner_type"], "codex")
        self.assertTrue(codex["models"][0]["label"].endswith(" via Codex"))
        by_slug = {m["slug"]: m for m in codex["models"]}
        self.assertEqual(by_slug["gemma4_ollama_cloud"]["id"], "gemma4:31b-cloud")

        claude = expand_ollama_cloud_config(raw, "claude")
        self.assertEqual(len(claude["variants"]), 2)
        self.assertEqual(claude["variants"][0]["main_model"], "kimi-k2.6:cloud")
        self.assertTrue(claude["variants"][0]["label"].endswith(" via Claude Code"))

        ollama = expand_ollama_cloud_config(raw, "ollama")
        self.assertEqual(ollama["models"][0]["runner_type"], "ollama")

        opencode = expand_ollama_cloud_config(raw, "opencode")
        self.assertEqual(opencode["models"][0]["runner_type"], "opencode")
        self.assertTrue(opencode["models"][0]["label"].endswith(" via OpenCode"))

    def test_model_entry_validation_reports_missing_required_key(self) -> None:
        cfg = {
            "ollama_cloud": True,
            "runner_configs": {
                "codex": {"command_prefix": ["ollama", "launch", "codex"]}
            },
            "models": [
                {
                    "slug": "missing_id",
                    "label": "Missing ID",
                    "selection_reason": "Regression fixture.",
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            r"ollama_cloud models\[0\] missing required string key 'id'.*missing_id",
        ):
            expand_ollama_cloud_config(cfg, "codex")


if __name__ == "__main__":
    unittest.main()
