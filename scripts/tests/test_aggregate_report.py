"""Tests for the unified report builder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.report import build_report, load_results  # noqa: E402
from benchmark.util import RESULT_SCHEMA_VERSION  # noqa: E402


class TestBuildReportOpencode(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "models": [
                {
                    "slug": "test-model",
                    "id": "test-provider/test-model",
                    "label": "Test Model",
                    "provider": "openrouter",
                    "selection_reason": "fast and cheap",
                },
            ],
            "runner": {"notes": ["test note"]},
        }

    def test_report_includes_harness_and_status(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "opencode",
                    "model": self.config["models"][0],
                    "status": "completed",
                    "elapsed_seconds": 100.0,
                    "tokens": {"total": 5000},
                    "tokens_per_second": 50.0,
                    "project_summary": {
                        "file_count": 20,
                        "works_as_intended": "yes",
                        "works_note": "",
                    },
                    "ollama_warmup": None,
                }
            ],
            "test prompt",
            harness="opencode",
        )
        self.assertIn("opencode", report)
        self.assertIn("Test Model", report)
        self.assertIn("completed", report)
        self.assertIn("100", report)

    def test_not_run_result_is_included(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "status": "not_run",
                    "elapsed_seconds": None,
                    "tokens": {},
                    "model": self.config["models"][0],
                    "harness": "opencode",
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "project_summary": {
                        "file_count": 0,
                        "works_as_intended": "n/a",
                        "works_note": "Run has not been executed yet.",
                    },
                }
            ],
            "test prompt",
            harness="opencode",
        )
        self.assertIn("not_run", report)


class TestBuildReportClaude(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "variants": [
                {"slug": "claude-sonnet", "main_model": "claude_sonnet_4_6"},
            ],
        }

    def test_report_includes_summary_table(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "claude",
                    "slug": "claude-sonnet",
                    "main_model": "claude_sonnet_4_6",
                    "status": "completed",
                    "elapsed_seconds": 200.0,
                    "file_count": 30,
                    "num_turns": 15,
                    "subagent_invocation_counts": {"explore": 3},
                }
            ],
            harness="claude",
        )
        self.assertIn("Claude Code", report)
        self.assertIn("claude-sonnet", report)
        self.assertIn("completed", report)
        self.assertIn("15", report)  # turns
        self.assertIn("3", report)  # delegations

    def test_model_usage_section(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "claude",
                    "slug": "claude-sonnet",
                    "status": "completed",
                    "elapsed_seconds": 200.0,
                    "file_count": 30,
                    "num_turns": 15,
                    "model_usage": {
                        "claude-sonnet-4-6": {
                            "inputTokens": 1000,
                            "outputTokens": 500,
                            "cacheReadInputTokens": 200,
                            "cacheCreationInputTokens": 100,
                        }
                    },
                }
            ],
            harness="claude",
        )
        self.assertIn("Per-Model Token Usage", report)
        self.assertIn("1,000", report)
        self.assertIn("500", report)

    def test_delegation_details(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "claude",
                    "slug": "claude-sonnet",
                    "status": "completed",
                    "elapsed_seconds": 200.0,
                    "file_count": 30,
                    "num_turns": 15,
                    "subagent_invocations": [
                        {"subagent_type": "explore", "description": "find files"},
                    ],
                }
            ],
            harness="claude",
        )
        self.assertIn("Delegation Details", report)
        self.assertIn("explore", report)
        self.assertIn("find files", report)

    def test_phase_breakdown(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "claude",
                    "slug": "claude-sonnet",
                    "status": "completed",
                    "elapsed_seconds": 300.0,
                    "file_count": 30,
                    "num_turns": 20,
                    "phases": [
                        {
                            "phase": "phase1",
                            "status": "completed",
                            "elapsed_seconds": 200,
                            "num_turns": 10,
                            "file_count": 25,
                        },
                        {
                            "phase": "phase2",
                            "status": "completed",
                            "elapsed_seconds": 100,
                            "num_turns": 10,
                            "file_count": 30,
                        },
                    ],
                }
            ],
            harness="claude",
        )
        self.assertIn("Phase Breakdown", report)
        self.assertIn("phase1", report)
        self.assertIn("phase2", report)


class TestBuildReportCursor(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "variants": [
                {"slug": "cursor-gpt5", "main_model": "gpt-5"},
            ],
        }

    def test_report_includes_summary_table(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "cursor",
                    "slug": "cursor-gpt5",
                    "main_model": "gpt-5",
                    "status": "completed",
                    "elapsed_seconds": 180.0,
                    "file_count": 25,
                    "num_turns": 12,
                }
            ],
            harness="cursor",
        )
        self.assertIn("Cursor CLI", report)
        self.assertIn("cursor-gpt5", report)
        self.assertIn("gpt-5", report)
        self.assertIn("completed", report)
        self.assertIn("12", report)  # turns

    def test_tool_activity_section(self) -> None:
        report = build_report(
            self.config,
            [
                {
                    "result_schema_version": RESULT_SCHEMA_VERSION,
                    "harness": "cursor",
                    "slug": "cursor-gpt5",
                    "status": "completed",
                    "elapsed_seconds": 180.0,
                    "file_count": 25,
                    "num_turns": 12,
                    "tool_use_counts": {"write /app/file.py": 5, "shell ls": 3},
                }
            ],
            harness="cursor",
        )
        self.assertIn("Tool activity", report)
        self.assertIn("write /app/file.py", report)
        self.assertIn("5", report)


if __name__ == "__main__":
    unittest.main()
