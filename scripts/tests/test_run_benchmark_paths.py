"""Tests for benchmark CLI path normalization."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_benchmark import REPO_ROOT, normalize_benchmark_paths  # noqa: E402


class TestRunBenchmarkPaths(unittest.TestCase):
    def test_default_results_dir_resolves_under_repo_root(self) -> None:
        args = argparse.Namespace(
            config=str(REPO_ROOT / "config" / "models.json"),
            followup_prompt=str(
                REPO_ROOT / "prompts" / "benchmark_followup_prompt.txt"
            ),
            ollama_warmup_results=str(REPO_ROOT / "results" / "ollama_warmup.json"),
            opencode_config=str(REPO_ROOT / "config" / "opencode.benchmark.json"),
            prompt="prompts/benchmark_prompt.txt",
            report=str(REPO_ROOT / "docs" / "report.md"),
            results_dir="results",
        )

        normalized = normalize_benchmark_paths(args)

        self.assertEqual(Path(normalized.results_dir), REPO_ROOT / "results")

    def test_relative_input_and_output_paths_resolve_under_repo_root(self) -> None:
        args = argparse.Namespace(
            config="config/models.json",
            followup_prompt="prompts/followup.txt",
            ollama_warmup_results="results/warmup.json",
            opencode_config="config/opencode.benchmark.json",
            prompt="prompts/benchmark_prompt.txt",
            report="docs/report.md",
            results_dir="tmp/results",
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
            Path(normalized.opencode_config),
            REPO_ROOT / "config" / "opencode.benchmark.json",
        )
        self.assertEqual(
            Path(normalized.prompt), REPO_ROOT / "prompts" / "benchmark_prompt.txt"
        )
        self.assertEqual(Path(normalized.report), REPO_ROOT / "docs" / "report.md")
        self.assertEqual(Path(normalized.results_dir), REPO_ROOT / "tmp" / "results")


if __name__ == "__main__":
    unittest.main()
