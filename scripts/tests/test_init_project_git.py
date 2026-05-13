"""Tests for :func:`benchmark.util.init_project_git`."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import init_project_git  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "git not on PATH")
class TestInitProjectGit(unittest.TestCase):
    def test_creates_git_dir_and_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            init_project_git(project)
            self.assertTrue((project / ".git").is_dir())
            init_project_git(project)
            self.assertTrue((project / ".git").is_dir())

    def test_rev_parse_show_toplevel_is_project_dir(self) -> None:
        """Nested repo so ``git rev-parse --show-toplevel`` stays under ``project``."""
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "nested" / "project"
            project.mkdir(parents=True)
            init_project_git(project)
            out = subprocess.run(
                ["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(Path(out).resolve(), project.resolve())


if __name__ == "__main__":
    unittest.main()
