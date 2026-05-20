"""Behavior tests for provider-based harness routing in resolve_harness_config."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import resolve_harness_config  # noqa: E402


def _write_minimal_harnesses(config_dir: Path, harnesses: list[str]) -> None:
    data = {h: {"command": h, "notes": []} for h in harnesses}
    (config_dir / "harnesses.json").write_text(json.dumps(data))


def _resolve(config_dir: Path, models: list[dict], harness: str) -> list[dict]:
    models_path = config_dir / "models.json"
    models_path.write_text(json.dumps({"models": models}))
    result = resolve_harness_config({"models": models}, models_path, harness)
    return result["models"]


class TestOllamaCloudRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "codex"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ollama_cloud_appears_in_claude_harness(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi:cloud"}]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "kimi")

    def test_ollama_cloud_appears_in_codex_harness(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi:cloud"}]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "kimi")

    def test_ollama_cloud_claude_gets_ollama_launch_prefix(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi:cloud"}]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(rows[0]["command_prefix"], ["ollama", "launch", "claude"])

    def test_ollama_cloud_codex_gets_runner_type_ollama(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi:cloud"}]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["runner_type"], "ollama")

    def test_ollama_cloud_codex_has_no_command_prefix(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi:cloud"}]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertNotIn("command_prefix", rows[0])

    def test_ollama_cloud_id_preserved(self) -> None:
        models = [{"slug": "kimi", "label": "Kimi", "provider": "ollama_cloud", "id": "kimi-k2.6:cloud"}]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(rows[0]["id"], "kimi-k2.6:cloud")


class TestProviderHarnessMapping(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "codex", "cursor", "opencode"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_anthropic_routes_to_claude_only(self) -> None:
        models = [{"slug": "sonnet", "label": "Sonnet", "provider": "anthropic", "id": "claude-test"}]
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "codex")), 0)
        self.assertEqual(len(_resolve(self.config_dir, models, "cursor")), 0)

    def test_openai_routes_to_codex_only(self) -> None:
        models = [{"slug": "gpt", "label": "GPT", "provider": "openai", "id": "gpt-5.5"}]
        self.assertEqual(len(_resolve(self.config_dir, models, "codex")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 0)
        self.assertEqual(len(_resolve(self.config_dir, models, "cursor")), 0)

    def test_cursor_routes_to_cursor_only(self) -> None:
        models = [{"slug": "comp", "label": "Composer", "provider": "cursor", "id": "composer-2.5"}]
        self.assertEqual(len(_resolve(self.config_dir, models, "cursor")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 0)
        self.assertEqual(len(_resolve(self.config_dir, models, "codex")), 0)

    def test_openai_runner_type_is_codex(self) -> None:
        models = [{"slug": "gpt", "label": "GPT", "provider": "openai", "id": "gpt-5.5"}]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["runner_type"], "codex")

    def test_unknown_provider_excluded_from_all_harnesses(self) -> None:
        models = [{"slug": "x", "label": "X", "provider": "openrouter", "id": "x/y"}]
        for harness in ("claude", "codex", "cursor"):
            self.assertEqual(len(_resolve(self.config_dir, models, harness)), 0)


class TestOpencodeIdRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "opencode"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_model_with_opencode_id_appears_in_opencode(self) -> None:
        models = [
            {
                "slug": "sonnet",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-native",
                "opencode_id": "openrouter/anthropic/claude-sonnet",
            }
        ]
        rows = _resolve(self.config_dir, models, "opencode")
        self.assertEqual(len(rows), 1)

    def test_model_with_opencode_id_uses_opencode_id_in_opencode_harness(self) -> None:
        models = [
            {
                "slug": "sonnet",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-native",
                "opencode_id": "openrouter/anthropic/claude-sonnet",
            }
        ]
        rows = _resolve(self.config_dir, models, "opencode")
        self.assertEqual(rows[0]["id"], "openrouter/anthropic/claude-sonnet")

    def test_model_with_opencode_id_uses_native_id_in_claude_harness(self) -> None:
        models = [
            {
                "slug": "sonnet",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-native",
                "opencode_id": "openrouter/anthropic/claude-sonnet",
            }
        ]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(rows[0]["id"], "claude-native")

    def test_model_without_opencode_id_absent_from_opencode(self) -> None:
        models = [{"slug": "sonnet", "label": "Sonnet", "provider": "anthropic", "id": "claude-native"}]
        rows = _resolve(self.config_dir, models, "opencode")
        self.assertEqual(len(rows), 0)


class TestModelFieldPassthrough(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["codex", "claude"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_codex_reasoning_effort_flows_through(self) -> None:
        models = [
            {
                "slug": "gpt55",
                "label": "GPT-5.5",
                "provider": "openai",
                "id": "gpt-5.5",
                "codex_reasoning_effort": "xhigh",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["codex_reasoning_effort"], "xhigh")

    def test_enable_followup_flows_through(self) -> None:
        models = [
            {
                "slug": "gpt54",
                "label": "GPT-5.4",
                "provider": "openai",
                "id": "gpt-5.4",
                "enable_followup": True,
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertTrue(rows[0]["enable_followup"])

    def test_missing_id_raises_on_resolve(self) -> None:
        models = [{"slug": "bad", "label": "Bad", "provider": "anthropic"}]
        with self.assertRaises(ValueError):
            _resolve(self.config_dir, models, "claude")
