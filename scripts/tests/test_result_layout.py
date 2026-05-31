"""Tests for benchmark.result_layout — single source of truth for paths."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.result_layout import (  # noqa: E402
    RunLayout,
    audit_generation_metrics_json,
    audit_target_dir,
    audit_report_md,
    audit_result_json,
    audit_stream_ndjson,
    audit_stderr_log,
    benchmark_target_slug_from_leaf,
    discover_benchmark_target_dirs,
    discover_project_result_jsons,
    format_replicate_dir,
    layout_from_repo,
    matches_benchmark_only_filter,
    parse_benchmark_target_path,
    replicate_result_dir,
    resolve_default_run_id,
    resolve_run_layout,
    split_target_slug,
    target_dir,
    target_followup_prompt,
    target_project_workspace,
    target_prompt,
    target_result_json,
    validate_run_id,
    BENCHMARK_CONTEST_HARNESSES,
    CURSOR_AGENT_PREFIX,
    HARNESS_PREFIXES,
)


class TestTargetPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = Path("/tmp/r/run_02/projects")

    def test_target_dir_joins_harness_and_slug(self) -> None:
        self.assertEqual(
            target_dir(self.projects, "claude", "claude_sonnet_4_6"),
            Path("/tmp/r/run_02/projects/claude-claude_sonnet_4_6"),
        )

    def test_project_workspace_is_project_subdir(self) -> None:
        self.assertEqual(
            target_project_workspace(self.projects, "opencode", "demo"),
            Path("/tmp/r/run_02/projects/opencode-demo/project"),
        )

    def test_result_json_path(self) -> None:
        self.assertEqual(
            target_result_json(self.projects, "cursor", "demo"),
            Path("/tmp/r/run_02/projects/cursor-demo/result.json"),
        )

    def test_prompt_path(self) -> None:
        self.assertEqual(
            target_prompt(self.projects, "codex", "gpt5"),
            Path("/tmp/r/run_02/projects/codex-gpt5/prompt.txt"),
        )

    def test_followup_prompt_path(self) -> None:
        self.assertEqual(
            target_followup_prompt(self.projects, "claude", "demo"),
            Path("/tmp/r/run_02/projects/claude-demo/followup-prompt.txt"),
        )


class TestResolveDefaultRunId(unittest.TestCase):
    def test_picks_highest_run_xx(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run_01").mkdir()
            (root / "run_02").mkdir()
            self.assertEqual(resolve_default_run_id(root), "run_02")

    def test_picks_highest_run_xx_by_numeric_suffix(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run_02").mkdir()
            (root / "run_10").mkdir()
            self.assertEqual(resolve_default_run_id(root), "run_10")

    def test_returns_none_for_flat_legacy_tree(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opencode-bad").mkdir()
            self.assertIsNone(resolve_default_run_id(root))


class TestRunLayout(unittest.TestCase):
    def test_run_layout_paths(self) -> None:
        layout = resolve_run_layout("run_02", Path("/tmp/results"))
        self.assertEqual(layout.run_root, Path("/tmp/results/run_02"))
        self.assertEqual(layout.projects_root, Path("/tmp/results/run_02/projects"))
        self.assertEqual(layout.audit_root, Path("/tmp/results/run_02/audit-reports"))
        self.assertEqual(
            layout.meta_analysis_md,
            Path("/tmp/results/run_02/meta-analysis.md"),
        )

    def test_validate_run_id_rejects_bad_ids(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_id("01")
        with self.assertRaises(ValueError):
            validate_run_id("run")
        validate_run_id("run_01")

    def test_layout_from_repo(self) -> None:
        layout = layout_from_repo("run_03", REPO_ROOT)
        self.assertEqual(layout.run_id, "run_03")
        self.assertEqual(layout.results_base, REPO_ROOT / "results")

    def test_discover_benchmark_targets(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "codex-demo" / "project").mkdir(parents=True)
            (root / "empty-dir").mkdir()
            found = discover_benchmark_target_dirs(root)
            self.assertEqual([p.name for p in found], ["codex-demo"])

    def test_discover_nested_replicate_targets(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "codex-demo" / "run_01" / "project").mkdir(parents=True)
            (root / "codex-demo" / "run_02" / "project").mkdir(parents=True)
            found = discover_benchmark_target_dirs(root)
            self.assertEqual(
                [p.name for p in found],
                ["run_01", "run_02"],
            )

    def test_replicate_path_helpers(self) -> None:
        projects = Path("/tmp/r/run_02/projects")
        self.assertEqual(format_replicate_dir(1), "run_01")
        self.assertEqual(
            replicate_result_dir(projects, "codex", "demo", 2),
            Path("/tmp/r/run_02/projects/codex-demo/run_02"),
        )
        parsed = parse_benchmark_target_path("codex-demo/run_01")
        self.assertEqual(parsed.target_group, "codex-demo")
        self.assertEqual(parsed.replicate_id, "run_01")
        self.assertEqual(parsed.harness, "codex")
        self.assertEqual(parsed.model_slug, "demo")

    def test_nested_audit_target_dir(self) -> None:
        root = Path("/tmp/audit-reports")
        self.assertEqual(
            audit_target_dir(root, "auditor", "codex-demo/run_01"),
            Path("/tmp/audit-reports/auditor/codex-demo/run_01"),
        )

    def test_matches_benchmark_only_filter(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "codex-demo" / "run_01"
            leaf.mkdir(parents=True)
            result_path = leaf / "result.json"
            result_path.write_text("{}")
            only = {"codex-demo"}
            self.assertTrue(
                matches_benchmark_only_filter(result_path, only, root)
            )
            self.assertTrue(
                matches_benchmark_only_filter(result_path, {"run_01"}, root)
            )
            self.assertFalse(
                matches_benchmark_only_filter(result_path, {"other"}, root)
            )

    def test_benchmark_target_slug_from_leaf(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "codex-demo" / "run_02"
            leaf.mkdir(parents=True)
            self.assertEqual(
                benchmark_target_slug_from_leaf(leaf, root),
                "codex-demo/run_02",
            )

    def test_discover_project_result_jsons(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "codex-demo"
            (legacy / "project").mkdir(parents=True)
            (legacy / "result.json").write_text("{}")
            nested = root / "codex-other" / "run_01"
            (nested / "project").mkdir(parents=True)
            (nested / "result.json").write_text("{}")
            paths = discover_project_result_jsons(root)
            self.assertEqual(len(paths), 2)
            self.assertEqual({p.parent.name for p in paths}, {"codex-demo", "run_01"})


class TestAuditPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/tmp/audit-reports")

    def test_audit_target_dir(self) -> None:
        self.assertEqual(
            audit_target_dir(self.root, "claude_opus_4_7", "opencode-demo"),
            Path("/tmp/audit-reports/claude_opus_4_7/opencode-demo"),
        )

    def test_audit_report_md(self) -> None:
        self.assertEqual(
            audit_report_md(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/report.md"),
        )

    def test_audit_result_json(self) -> None:
        self.assertEqual(
            audit_result_json(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/result.json"),
        )

    def test_audit_stream_and_stderr(self) -> None:
        self.assertEqual(
            audit_stream_ndjson(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/stream.ndjson"),
        )
        self.assertEqual(
            audit_stderr_log(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/stderr.log"),
        )

    def test_audit_generation_metrics_json(self) -> None:
        self.assertEqual(
            audit_generation_metrics_json(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/generation-metrics.json"),
        )


class TestSplitTargetSlug(unittest.TestCase):
    def test_strips_recognised_harness_prefix(self) -> None:
        self.assertEqual(
            split_target_slug("claude-claude_sonnet_4_6"),
            ("claude", "claude_sonnet_4_6"),
        )
        self.assertEqual(
            split_target_slug("opencode-gpt5"),
            ("opencode", "gpt5"),
        )
        self.assertEqual(
            split_target_slug("codex-gpt5"),
            ("codex", "gpt5"),
        )
        self.assertEqual(
            split_target_slug("cursor-foo"),
            ("cursor", "foo"),
        )

    def test_unknown_prefix_keeps_full_name_as_model(self) -> None:
        self.assertEqual(
            split_target_slug("plain_name"),
            (None, "plain_name"),
        )

    def test_known_harness_prefixes_published(self) -> None:
        # Anyone listing canonical harnesses pulls from one place.
        self.assertEqual(
            set(HARNESS_PREFIXES),
            {"opencode", "codex", "claude", "cursor"},
        )

    def test_benchmark_contest_harnesses_exclude_cursor(self) -> None:
        self.assertEqual(
            BENCHMARK_CONTEST_HARNESSES,
            frozenset({"opencode", "codex", "claude"}),
        )
        self.assertNotIn(CURSOR_AGENT_PREFIX, BENCHMARK_CONTEST_HARNESSES)

    def test_unrecognized_prefix_treated_as_model_name(self) -> None:
        # Only canonical harness prefixes split; everything else is one slug.
        self.assertEqual(
            split_target_slug("ollama-gpt_5"),
            (None, "ollama-gpt_5"),
        )


if __name__ == "__main__":
    unittest.main()
