"""Tests for benchmark CLI path normalization."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import resolve_build_harness_config  # noqa: E402
from benchmark.util import load_json  # noqa: E402
from run_benchmark import (  # noqa: E402
    REPO_ROOT,
    _default_config_path,
    _run_model_harness,
    normalize_benchmark_paths,
    parse_args,
)


class TestRunBenchmarkPaths(unittest.TestCase):
    def test_default_results_dir_resolves_under_repo_root(self) -> None:
        args = argparse.Namespace(
            config=str(REPO_ROOT / "config" / "models.json"),
            followup_prompt=str(
                REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"
            ),
            ollama_warmup_results=str(REPO_ROOT / "results" / "ollama_warmup.json"),
            prompt="prompts/benchmark_prompt.txt",
            results_dir="results",
            run_id=None,
        )

        normalized = normalize_benchmark_paths(args)

        self.assertEqual(Path(normalized.results_dir), REPO_ROOT / "results")

    def test_parse_args_rejects_variant_flag(self) -> None:
        stderr = io.StringIO()

        with patch.object(
            sys,
            "argv",
            ["run_benchmark.py", "--harness", "claude", "--variant", "x"],
        ):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    parse_args()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments: --variant x", stderr.getvalue())

    def test_parse_args_rejects_old_config_flag(self) -> None:
        stderr = io.StringIO()

        with patch.object(
            sys,
            "argv",
            ["run_benchmark.py", "--harness", "opencode", "--config", "x.json"],
        ):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    parse_args()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments: --config x.json", stderr.getvalue())

    def test_claude_and_cursor_default_to_shared_models_registry(self) -> None:
        models_path = REPO_ROOT / "config" / "models.json"

        self.assertEqual(_default_config_path("claude"), models_path)
        self.assertEqual(_default_config_path("cursor"), models_path)

    def test_relative_input_and_output_paths_resolve_under_repo_root(self) -> None:
        args = argparse.Namespace(
            config="config/models.json",
            followup_prompt="prompts/followup.txt",
            ollama_warmup_results="results/warmup.json",
            prompt="prompts/benchmark_prompt.txt",
            results_dir="tmp/results",
            run_id=None,
        )

        normalized = normalize_benchmark_paths(args)

        self.assertEqual(Path(normalized.config), REPO_ROOT / "config" / "models.json")
        self.assertEqual(
            Path(normalized.followup_prompt), REPO_ROOT / "prompts" / "followup.txt"
        )
        self.assertEqual(
            Path(normalized.ollama_warmup_results),
            REPO_ROOT / "results" / "warmup.json",
        )
        self.assertEqual(
            Path(normalized.prompt), REPO_ROOT / "prompts" / "benchmark_prompt.txt"
        )
        self.assertEqual(Path(normalized.results_dir), REPO_ROOT / "tmp" / "results")

    def test_rejects_slug_from_other_harness(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            prompts_dir = root / "prompts"
            config_dir.mkdir()
            prompts_dir.mkdir()
            (prompts_dir / "prompt.txt").write_text("build")
            (prompts_dir / "followup.txt").write_text("check")
            (config_dir / "harnesses.json").write_text(
                json.dumps({"opencode": {"notes": []}, "codex": {"notes": []}})
            )
            (config_dir / "models.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "harness": "codex",
                                "slug": "codex_only",
                                "id": "gpt-test",
                                "label": "Codex Only",
                                "provider": "openai",
                                "selection_reason": "Codex row.",
                            }
                        ]
                    }
                )
            )
            args = argparse.Namespace(
                auto_skip_slow_preview=False,
                config=str(config_dir / "models.json"),
                followup_prompt=str(prompts_dir / "followup.txt"),
                force=False,
                jobs=1,
                local_api_base=None,
                local_backend="ollama",
                max_runs=None,
                min_preview_output_tps=5.0,
                min_preview_samples=3,
                models=["codex_only"],
                no_progress_minutes=1,
                no_docker_prune=True,
                no_result_validation=True,
                ollama_warmup_results=str(root / "results" / "warmup.json"),
                prompt=str(prompts_dir / "prompt.txt"),
                results_dir=str(root / "results"),
                timeout_minutes=1,
                variant=None,
            )
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = _run_model_harness(args, "opencode")

            self.assertEqual(exit_code, 1)
            self.assertIn(
                "Slug `codex_only` is not a opencode model", stderr.getvalue()
            )

    def test_models_registry_selection_uses_provider_routing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            config_dir.mkdir()
            config_path = config_dir / "models.json"
            (config_dir / "harnesses.json").write_text(
                json.dumps({"claude": {"command": "claude", "notes": []}})
            )
            payload = {
                "models": [
                    {
                        "slug": "claude_model",
                        "label": "Claude",
                        "provider": "anthropic",
                        "id": "claude-test",
                        "selection_reason": "Anthropic row.",
                    },
                    {
                        "slug": "gpt_model",
                        "label": "GPT",
                        "provider": "openai",
                        "id": "gpt-test",
                        "selection_reason": "OpenAI row — should not appear in claude harness.",
                    },
                ]
            }

            resolved = resolve_build_harness_config(payload, config_path, "claude")

            self.assertEqual([m["slug"] for m in resolved["models"]], ["claude_model"])

    def test_default_models_registry_resolves_build_harnesses(self) -> None:
        config_path = REPO_ROOT / "config" / "models.json"
        raw = load_json(config_path)

        opencode = resolve_build_harness_config(raw, config_path, "opencode")
        codex = resolve_build_harness_config(raw, config_path, "codex")
        claude = resolve_build_harness_config(raw, config_path, "claude")
        cursor = resolve_build_harness_config(raw, config_path, "cursor")

        self.assertIn("notes", opencode["runner"])
        self.assertIn("notes", codex["runner"])
        self.assertIn("notes", claude["runner"])
        self.assertIn("notes", cursor["runner"])
        self.assertGreater(len(opencode["models"]), 0)
        self.assertGreater(len(codex["models"]), 0)
        self.assertGreater(len(claude["models"]), 0)
        self.assertGreater(len(cursor["models"]), 0)
        self.assertTrue(all(m["harness"] == "opencode" for m in opencode["models"]))
        self.assertTrue(all(m["harness"] == "codex" for m in codex["models"]))
        self.assertTrue(all(m["harness"] == "claude" for m in claude["models"]))
        self.assertTrue(all(m["harness"] == "cursor" for m in cursor["models"]))
        raw_models = raw["models"]
        self.assertTrue(all("role" not in m for m in raw_models))
        self.assertTrue(all("harness" not in m for m in raw_models))


if __name__ == "__main__":
    unittest.main()
