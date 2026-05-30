"""Behavior tests for explicit harness routing in resolve_harness_config."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import resolve_harness_config  # noqa: E402
from benchmark.util import uses_ollama_launch_codex  # noqa: E402


def _write_minimal_harnesses(config_dir: Path, harnesses: list[str]) -> None:
    data = {h: {"command": h, "notes": []} for h in harnesses}
    (config_dir / "harnesses.json").write_text(json.dumps(data))


def _resolve(config_dir: Path, models: list[dict], harness: str) -> list[dict]:
    models_path = config_dir / "models.json"
    models_path.write_text(json.dumps({"models": models}))
    result = resolve_harness_config({"models": models}, models_path, harness)
    return result["models"]


class TestOllamaHarnessRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "codex", "opencode"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ollama_claude_routes_to_claude_harness(self) -> None:
        models = [
            {
                "slug": "kimi_claude",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_claude",
            }
        ]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "kimi_claude")

    def test_ollama_codex_routes_to_codex_harness(self) -> None:
        models = [
            {
                "slug": "kimi_codex",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_codex",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(len(rows), 1)

    def test_ollama_claude_gets_ollama_launch_prefix(self) -> None:
        models = [
            {
                "slug": "kimi_claude",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_claude",
            }
        ]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(
            rows[0]["command_prefix"], ["ollama", "launch", "--yes", "claude"]
        )

    def test_ollama_codex_gets_runner_type_ollama(self) -> None:
        models = [
            {
                "slug": "kimi_codex",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_codex",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["runner_type"], "ollama")

    def test_ollama_codex_has_no_command_prefix(self) -> None:
        models = [
            {
                "slug": "kimi_codex",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_codex",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertNotIn("command_prefix", rows[0])

    def test_uses_ollama_launch_codex_with_yes_prefix(self) -> None:
        model = {
            "command_prefix": ["ollama", "launch", "--yes", "codex"],
            "runner_type": "ollama",
        }
        self.assertTrue(uses_ollama_launch_codex(model))

    def test_ollama_opencode_routes_to_opencode_harness(self) -> None:
        models = [
            {
                "slug": "kimi_opencode",
                "label": "Kimi",
                "provider": "ollama_cloud",
                "id": "kimi:cloud",
                "harness": "ollama_opencode",
            }
        ]
        rows = _resolve(self.config_dir, models, "opencode")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["runner_type"], "opencode")
        self.assertEqual(
            rows[0]["command_prefix"], ["ollama", "launch", "--yes", "opencode"]
        )


class TestDirectHarnessRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "codex", "cursor", "opencode"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_claude_harness_row_routes_to_claude_only(self) -> None:
        models = [
            {
                "slug": "sonnet",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-test",
                "harness": "claude",
            }
        ]
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "codex")), 0)

    def test_codex_harness_row_routes_to_codex_only(self) -> None:
        models = [
            {
                "slug": "gpt",
                "label": "GPT",
                "provider": "openai",
                "id": "gpt-5.5",
                "harness": "codex",
            }
        ]
        self.assertEqual(len(_resolve(self.config_dir, models, "codex")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 0)

    def test_cursor_harness_row_routes_to_cursor_only(self) -> None:
        models = [
            {
                "slug": "comp",
                "label": "Composer",
                "provider": "cursor",
                "id": "composer-2.5",
                "harness": "cursor",
            }
        ]
        self.assertEqual(len(_resolve(self.config_dir, models, "cursor")), 1)
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 0)

    def test_codex_runner_type_is_codex(self) -> None:
        models = [
            {
                "slug": "gpt",
                "label": "GPT",
                "provider": "openai",
                "id": "gpt-5.5",
                "harness": "codex",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["runner_type"], "codex")

    def test_row_without_matching_harness_excluded(self) -> None:
        models = [
            {
                "slug": "x",
                "label": "X",
                "provider": "openrouter",
                "id": "x/y",
                "harness": "codex",
            }
        ]
        self.assertEqual(len(_resolve(self.config_dir, models, "claude")), 0)


class TestOpencodeHarnessRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self.config_dir.mkdir()
        _write_minimal_harnesses(self.config_dir, ["claude", "opencode"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_opencode_harness_uses_opencode_id(self) -> None:
        models = [
            {
                "slug": "sonnet_opencode",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-native",
                "opencode_id": "openrouter/anthropic/claude-sonnet",
                "harness": "opencode",
            }
        ]
        rows = _resolve(self.config_dir, models, "opencode")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "openrouter/anthropic/claude-sonnet")

    def test_claude_harness_uses_native_id(self) -> None:
        models = [
            {
                "slug": "sonnet",
                "label": "Sonnet",
                "provider": "anthropic",
                "id": "claude-native",
                "opencode_id": "openrouter/anthropic/claude-sonnet",
                "harness": "claude",
            }
        ]
        rows = _resolve(self.config_dir, models, "claude")
        self.assertEqual(rows[0]["id"], "claude-native")


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
                "harness": "codex",
                "codex_reasoning_effort": "xhigh",
            }
        ]
        rows = _resolve(self.config_dir, models, "codex")
        self.assertEqual(rows[0]["codex_reasoning_effort"], "xhigh")

    def test_missing_id_raises_on_resolve(self) -> None:
        models = [
            {
                "slug": "bad",
                "label": "Bad",
                "provider": "anthropic",
                "harness": "claude",
            }
        ]
        with self.assertRaises(ValueError):
            _resolve(self.config_dir, models, "claude")


if __name__ == "__main__":
    unittest.main()
