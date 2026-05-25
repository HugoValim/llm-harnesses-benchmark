"""Tests for benchmark.result_layout — single source of truth for paths."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.result_layout import (  # noqa: E402
    audit_generation_metrics_json,
    audit_static_analysis_json,
    audit_target_dir,
    audit_report_md,
    audit_result_json,
    audit_stream_ndjson,
    audit_stderr_log,
    split_target_slug,
    target_dir,
    target_followup_prompt,
    target_project_workspace,
    target_prompt,
    target_result_json,
    HARNESS_PREFIXES,
)


class TestTargetPaths(unittest.TestCase):
    def setUp(self) -> None:
        self.results = Path("/tmp/r")

    def test_target_dir_joins_harness_and_slug(self) -> None:
        self.assertEqual(
            target_dir(self.results, "claude", "claude_sonnet_4_6"),
            Path("/tmp/r/claude-claude_sonnet_4_6"),
        )

    def test_project_workspace_is_project_subdir(self) -> None:
        self.assertEqual(
            target_project_workspace(self.results, "opencode", "demo"),
            Path("/tmp/r/opencode-demo/project"),
        )

    def test_result_json_path(self) -> None:
        self.assertEqual(
            target_result_json(self.results, "cursor", "demo"),
            Path("/tmp/r/cursor-demo/result.json"),
        )

    def test_prompt_path(self) -> None:
        self.assertEqual(
            target_prompt(self.results, "codex", "gpt5"),
            Path("/tmp/r/codex-gpt5/prompt.txt"),
        )

    def test_followup_prompt_path(self) -> None:
        self.assertEqual(
            target_followup_prompt(self.results, "claude", "demo"),
            Path("/tmp/r/claude-demo/followup-prompt.txt"),
        )


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

    def test_audit_static_analysis_json(self) -> None:
        # Evidence file for the audit-v3.3 D10 dimension lives next to report.md.
        self.assertEqual(
            audit_static_analysis_json(self.root, "auditor", "target"),
            Path("/tmp/audit-reports/auditor/target/static-analysis.json"),
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

    def test_unrecognized_prefix_treated_as_model_name(self) -> None:
        # Only canonical harness prefixes split; everything else is one slug.
        self.assertEqual(
            split_target_slug("ollama-gpt_5"),
            (None, "ollama-gpt_5"),
        )


if __name__ == "__main__":
    unittest.main()
