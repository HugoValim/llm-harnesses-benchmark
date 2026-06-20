"""Tests for per-model replicate expectation and coverage checks."""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.replicate_expectations import (  # noqa: E402
    ExpectedBenchmarkLeaf,
    assert_replicate_coverage,
    expected_benchmark_leaves,
    filter_expected_leaves,
    find_replicate_coverage_gaps,
    format_replicate_gaps,
)


class TestExpectedBenchmarkLeaves(unittest.TestCase):
    def test_registry_models_emit_variable_replicate_counts(self) -> None:
        leaves = expected_benchmark_leaves(REPO_ROOT / "config" / "models.json")
        slugs = {leaf.slug for leaf in leaves}
        for prefix in (
            "codex-codex_gpt_5_5",
            "claude-claude_opus_4_7",
            "claude-claude_opus_4_8",
            "opencode-kimi_k2_6",
        ):
            for run in ("run_01", "run_02", "run_03"):
                self.assertIn(f"{prefix}/{run}", slugs)

    def test_expected_leaves_per_harness_num_runs(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            config_path = self._write_registry_config(
                Path(tmp),
                [
                    {
                        "slug": "kimi_k2_6",
                        "provider": "ollama_cloud",
                        "id": "kimi-k2.6:cloud",
                        "harness": [
                            "ollama_claude",
                            "ollama_codex",
                            "ollama_opencode",
                        ],
                        "num_runs": 2,
                    }
                ],
            )
            leaves = expected_benchmark_leaves(config_path)
            self.assertEqual(len(leaves), 6)
            slugs = {leaf.slug for leaf in leaves}
            self.assertEqual(
                slugs,
                {
                    "claude-kimi_k2_6/run_01",
                    "claude-kimi_k2_6/run_02",
                    "codex-kimi_k2_6/run_01",
                    "codex-kimi_k2_6/run_02",
                    "opencode-kimi_k2_6/run_01",
                    "opencode-kimi_k2_6/run_02",
                },
            )

    def test_custom_config_mixed_num_runs(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            config_path = self._write_registry_config(
                Path(tmp),
                [
                    {
                        "slug": "solo",
                        "provider": "openai",
                        "id": "gpt-5",
                        "harness": "codex",
                        "num_runs": 1,
                    },
                    {
                        "slug": "triple",
                        "provider": "openai",
                        "id": "gpt-5",
                        "harness": "codex",
                        "num_runs": 3,
                    },
                ],
            )
            leaves = expected_benchmark_leaves(config_path, harness="codex")
            slugs = [leaf.slug for leaf in leaves]
            self.assertEqual(
                slugs,
                [
                    "codex-solo/run_01",
                    "codex-triple/run_01",
                    "codex-triple/run_02",
                    "codex-triple/run_03",
                ],
            )

    def test_filter_expected_leaves_respects_only(self) -> None:
        all_leaves = expected_benchmark_leaves(REPO_ROOT / "config" / "models.json")
        leaf = all_leaves[0]
        filtered = filter_expected_leaves(all_leaves, {leaf.replicate_id})
        self.assertTrue(all(item.replicate_id == leaf.replicate_id for item in filtered))

    def _write_registry_config(self, root: Path, models: list[dict]) -> Path:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(
            REPO_ROOT / "config" / "harnesses.json",
            config_dir / "harnesses.json",
        )
        config_path = config_dir / "models.json"
        config_path.write_text(json.dumps({"models": models}), encoding="utf-8")
        return config_path


class TestFindReplicateCoverageGaps(unittest.TestCase):
    def _demo_expected(self) -> list[ExpectedBenchmarkLeaf]:
        return [
            ExpectedBenchmarkLeaf(
                harness="codex",
                model_slug="demo",
                target_group="codex-demo",
                replicate_id=f"run_0{i}",
                num_runs=3,
            )
            for i in range(1, 4)
        ]

    def test_complete_nested_layout_has_no_gaps(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(1, 4):
                leaf = root / "codex-demo" / f"run_0{i}"
                leaf.mkdir(parents=True)
                (leaf / "result.json").write_text("{}", encoding="utf-8")
            gaps = find_replicate_coverage_gaps(root, self._demo_expected())
            self.assertEqual(gaps, [])

    def test_project_without_result_json_is_not_a_coverage_gap(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "codex-demo" / "run_01"
            leaf.mkdir(parents=True)
            (leaf / "project").mkdir()
            gaps = find_replicate_coverage_gaps(root, self._demo_expected())
            gap_slugs = {gap.slug for gap in gaps}
            self.assertNotIn("codex-demo/run_01", gap_slugs)
            self.assertIn("codex-demo/run_02", gap_slugs)

    def test_missing_replicate_is_reported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gaps = find_replicate_coverage_gaps(root, self._demo_expected())
            self.assertEqual(len(gaps), 3)
            self.assertIn("run_02", gaps[1].slug)

    def test_legacy_flat_layout_is_flagged(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "codex-demo"
            group.mkdir(parents=True)
            (group / "project").mkdir()
            gaps = find_replicate_coverage_gaps(root, self._demo_expected())
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0].slug, "codex-demo")
            self.assertIn("legacy flat", gaps[0].reason)

    def test_unexpected_replicate_dir_is_reported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("run_01", "run_02", "run_03", "run_04"):
                leaf = root / "codex-demo" / name
                leaf.mkdir(parents=True)
                (leaf / "result.json").write_text("{}", encoding="utf-8")
            gaps = find_replicate_coverage_gaps(root, self._demo_expected())
            reasons = {gap.slug: gap.reason for gap in gaps}
            self.assertIn("codex-demo/run_04", reasons)
            self.assertIn("unexpected replicate", reasons["codex-demo/run_04"])

    def test_format_replicate_gaps_empty_when_complete(self) -> None:
        self.assertEqual(format_replicate_gaps([]), "")


class TestAssertReplicateCoverage(unittest.TestCase):
    def test_assert_replicate_coverage_exits_when_incomplete(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = TestExpectedBenchmarkLeaves()._write_registry_config(
                root,
                [
                    {
                        "slug": "demo",
                        "provider": "openai",
                        "id": "gpt-5",
                        "harness": "codex",
                        "num_runs": 2,
                    }
                ],
            )
            projects = root / "projects"
            projects.mkdir()
            with self.assertRaises(SystemExit) as ctx:
                assert_replicate_coverage(
                    projects_root=projects,
                    models_config_path=config_path,
                )
            self.assertIn("Replicate coverage incomplete", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
