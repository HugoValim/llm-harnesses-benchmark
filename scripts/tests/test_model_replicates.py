"""Tests for per-model benchmark replicate dispatch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import (  # noqa: E402
    _normalize_registry_models,
    registry_harness_values,
    resolve_build_harness_config,
)
from benchmark.replicates import attach_replicate_fields, model_num_runs, run_replicate_attempts  # noqa: E402


class TestNumRunsConfig(unittest.TestCase):
    def test_normalize_requires_positive_num_runs(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_registry_models([{"slug": "demo", "num_runs": 0, "harness": "codex"}])

    def test_normalize_propagates_num_runs(self) -> None:
        rows = _normalize_registry_models(
            [
                {
                    "slug": "demo",
                    "num_runs": 3,
                    "provider": "openai",
                    "id": "gpt-5",
                    "harness": "codex",
                }
            ]
        )
        self.assertEqual(rows[0]["num_runs"], 3)

    def test_normalize_accepts_harness_list(self) -> None:
        rows = _normalize_registry_models(
            [
                {
                    "slug": "kimi_k2_6",
                    "num_runs": 3,
                    "provider": "ollama_cloud",
                    "id": "kimi-k2.6:cloud",
                    "harness": ["ollama_claude", "ollama_codex"],
                }
            ]
        )
        self.assertEqual(
            rows[0]["harness"],
            ["ollama_claude", "ollama_codex"],
        )
        self.assertEqual(
            registry_harness_values(rows[0]),
            ["ollama_claude", "ollama_codex"],
        )

    def test_normalize_accepts_legacy_string_harness(self) -> None:
        rows = _normalize_registry_models(
            [
                {
                    "slug": "demo",
                    "num_runs": 1,
                    "id": "gpt-5",
                    "harness": "codex",
                }
            ]
        )
        self.assertEqual(rows[0]["harness"], ["codex"])

    def test_normalize_rejects_empty_harness_list(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_registry_models(
                [{"slug": "demo", "num_runs": 1, "harness": []}]
            )

    def test_normalize_rejects_invalid_harness_in_list(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_registry_models(
                [{"slug": "demo", "num_runs": 1, "harness": ["not_a_harness"]}]
            )

    def test_resolve_build_harness_config_keeps_num_runs(self) -> None:
        import json

        config_path = REPO_ROOT / "config" / "models.json"
        raw = json.loads(config_path.read_text())
        expected = {m["slug"]: m["num_runs"] for m in raw["models"]}
        config = resolve_build_harness_config(raw, config_path, "codex")
        self.assertTrue(config["models"])
        for model in config["models"]:
            self.assertEqual(model.get("num_runs"), expected[model["slug"]])


class TestReplicateHelpers(unittest.TestCase):
    def test_attach_replicate_fields(self) -> None:
        payload = attach_replicate_fields({}, replicate_index=2, num_runs=3)
        self.assertEqual(payload["replicate_index"], 2)
        self.assertEqual(payload["replicate_id"], "run_02")
        self.assertEqual(payload["num_runs"], 3)

    def test_run_replicate_attempts_sequential(self) -> None:
        calls: list[int] = []

        def _run_once(replicate_index: int, num_runs: int) -> dict:
            calls.append(replicate_index)
            self.assertEqual(num_runs, 2)
            return {"replicate_index": replicate_index}

        model = {"slug": "demo", "num_runs": 2}
        last = run_replicate_attempts(model, _run_once)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(last, {"replicate_index": 2})

    def test_model_num_runs_defaults_to_one(self) -> None:
        self.assertEqual(model_num_runs({"slug": "demo"}), 1)


class TestRegistryModelsJson(unittest.TestCase):
    def test_models_json_has_num_runs_on_every_row(self) -> None:
        import json

        payload = json.loads((REPO_ROOT / "config" / "models.json").read_text())
        for model in payload["models"]:
            self.assertIsInstance(model.get("num_runs"), int)
            self.assertGreaterEqual(model["num_runs"], 1)


if __name__ == "__main__":
    unittest.main()
