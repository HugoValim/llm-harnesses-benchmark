"""Tests for Cursor CLI benchmark runner."""

from __future__ import annotations

import unittest

from benchmark.cursor_runner import build_command
from benchmark.pricing import merge_cursor_model_usage, model_usage_from_cursor_final


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


if __name__ == "__main__":
    unittest.main()
