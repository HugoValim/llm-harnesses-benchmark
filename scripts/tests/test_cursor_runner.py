"""Tests for Cursor CLI benchmark runner."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from benchmark.cursor_runner import CursorStreamResult, build_command, run_variant
from benchmark.pricing import merge_cursor_model_usage, model_usage_from_cursor_final
from benchmark.rate_limit import RateLimitWaitPolicy


class TestCursorBuildCommand(unittest.TestCase):
    def test_phase1_command(self) -> None:
        cmd = build_command("composer-2.5", "build the app")
        self.assertEqual(
            cmd,
            [
                "agent",
                "--model",
                "composer-2.5",
                "-p",
                "--output-format",
                "stream-json",
                "--force",
                "--trust",
                "build the app",
            ],
        )

    def test_phase2_cold_command_has_no_continue(self) -> None:
        cmd = build_command("composer-2", "validate docker", continue_session=False)
        self.assertNotIn("--continue", cmd)

    def test_phase2_uses_continue(self) -> None:
        cmd = build_command("composer-2", "validate docker", continue_session=True)
        self.assertIn("--continue", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "composer-2")

    def test_command_prefix(self) -> None:
        cmd = build_command(
            "composer-2.5",
            "hi",
            command_prefix=["/custom/agent"],
        )
        self.assertEqual(cmd[0], "/custom/agent")

    def test_model_usage_from_final_event(self) -> None:
        final = {
            "type": "result",
            "usage": {
                "inputTokens": 100,
                "outputTokens": 50,
                "cacheReadTokens": 1000,
                "cacheWriteTokens": 0,
            },
        }
        model_usage = model_usage_from_cursor_final("composer-2.5", final)
        self.assertEqual(
            model_usage,
            {
                "composer-2.5": {
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "cacheReadInputTokens": 1000,
                    "cacheCreationInputTokens": 0,
                }
            },
        )

    def test_merge_model_usage_across_phases(self) -> None:
        p1 = model_usage_from_cursor_final(
            "composer-2.5",
            {"usage": {"inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 1}},
        )
        p2 = model_usage_from_cursor_final(
            "composer-2.5",
            {"usage": {"inputTokens": 3, "outputTokens": 2, "cacheReadTokens": 4}},
        )
        merged = merge_cursor_model_usage(p1, p2)
        self.assertEqual(merged["composer-2.5"]["inputTokens"], 13)
        self.assertEqual(merged["composer-2.5"]["outputTokens"], 7)
        self.assertEqual(merged["composer-2.5"]["cacheReadInputTokens"], 5)


class TestCursorRunVariantLifecycle(unittest.TestCase):
    def test_followup_run_uses_shared_lifecycle(self) -> None:
        variant = {"slug": "cursor_demo", "main_model": "composer-2.5"}
        fake_results = [
            CursorStreamResult("", "", False, False, None, assistant_turns=1),
            CursorStreamResult("", "", False, False, None, assistant_turns=2),
        ]
        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with TemporaryDirectory() as tmp:
            with patch("benchmark.workspace.init_project_git"), patch(
                "benchmark.workspace.validate_benchmark_workspace"
            ), patch("benchmark.workspace.write_project_context"), patch(
                "benchmark.cursor_runner.resolve_harness_cli_versions",
                return_value={},
            ), patch(
                "benchmark.cursor_runner.subprocess.Popen",
                return_value=mock_proc,
            ), patch(
                "benchmark.cursor_runner.stream_process",
                side_effect=fake_results,
            ):
                payload = run_variant(
                    variant=variant,
                    prompt="build app",
                    followup_prompt="check app",
                    results_dir=Path(tmp),
                    force=True,
                    rate_limit_policy=RateLimitWaitPolicy(cap_seconds=0),
                )

        self.assertEqual([phase["phase"] for phase in payload["phases"]], ["phase1", "phase2"])
        self.assertEqual(payload["num_turns"], 3)
        self.assertIn("followup_stream_ndjson", payload["paths"])


if __name__ == "__main__":
    unittest.main()
