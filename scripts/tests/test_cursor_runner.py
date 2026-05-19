"""Tests for Cursor CLI benchmark runner."""

from __future__ import annotations

import unittest

from benchmark.cursor_runner import build_command


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


if __name__ == "__main__":
    unittest.main()
