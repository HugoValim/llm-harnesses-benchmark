"""Tests for :func:`benchmark.util.write_project_context`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import write_project_context  # noqa: E402


class TestWriteProjectContext(unittest.TestCase):
    def test_writes_claude_and_agents_with_constraints(self) -> None:
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            write_project_context(project)
            claude = (project / "CLAUDE.md").read_text()
            agents = (project / "AGENTS.md").read_text()
            self.assertIn("Hard constraints", claude)
            self.assertIn("Operating mode", claude)
            self.assertIn("Never hardcode secrets", claude)
            self.assertEqual(claude, agents)

    def test_opt_out_writes_workspace_only(self) -> None:
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            write_project_context(project, include_agent_rules=False)
            claude = (project / "CLAUDE.md").read_text()
            self.assertIn("Hard constraints", claude)
            self.assertNotIn("Operating mode", claude)

    def test_overwrite_is_idempotent_for_content(self) -> None:
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            write_project_context(project)
            first = (project / "CLAUDE.md").read_text()
            write_project_context(project)
            second = (project / "CLAUDE.md").read_text()
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
