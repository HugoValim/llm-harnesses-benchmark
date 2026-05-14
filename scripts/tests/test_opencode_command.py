"""Regression tests for OpenCode benchmark command construction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.runner import build_opencode_command  # noqa: E402


class TestBuildOpenCodeCommand(unittest.TestCase):
    def test_plain_opencode_command_sets_project_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            command = build_opencode_command(
                {"command": "opencode", "args": ["run", "--format", "json"]},
                "openrouter/test-model",
                "build it",
                project_dir=project_dir,
            )

            self.assertEqual(
                command,
                [
                    "opencode",
                    "run",
                    "--dir",
                    str(project_dir.resolve()),
                    "--format",
                    "json",
                    "-m",
                    "openrouter/test-model",
                    "build it",
                ],
            )

    def test_ollama_launch_forwards_project_dir_to_opencode(self) -> None:
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            command = build_opencode_command(
                {"command": "opencode", "args": ["run", "--format", "json"]},
                "qwen3:cloud",
                "build it",
                project_dir=project_dir,
                command_prefix=["ollama", "launch", "--yes", "opencode"],
            )

            self.assertEqual(
                command,
                [
                    "ollama",
                    "launch",
                    "--yes",
                    "opencode",
                    "--model",
                    "qwen3:cloud",
                    "--",
                    "run",
                    "--dir",
                    str(project_dir.resolve()),
                    "--format",
                    "json",
                    "build it",
                ],
            )

    def test_session_resume_command_keeps_project_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            command = build_opencode_command(
                {"command": "opencode", "args": ["run", "--format", "json"]},
                "openrouter/test-model",
                "fix it",
                project_dir=project_dir,
                continue_session_id="session-123",
            )

            self.assertEqual(
                command,
                [
                    "opencode",
                    "run",
                    "--dir",
                    str(project_dir.resolve()),
                    "--format",
                    "json",
                    "--session",
                    "session-123",
                    "fix it",
                ],
            )


if __name__ == "__main__":
    unittest.main()
