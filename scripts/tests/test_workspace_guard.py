"""Tests for benchmark workspace launch guards."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import init_project_git, validate_benchmark_workspace  # noqa: E402
from benchmark.workspace import prepare_project_workspace  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "git not on PATH")
class TestValidateBenchmarkWorkspace(unittest.TestCase):
    def test_prepare_project_workspace_creates_isolated_context(self) -> None:
        with TemporaryDirectory() as tmp:
            results_dir = Path(tmp) / "results"
            result_dir = results_dir / "opencode-model"
            project_dir = result_dir / "project"

            prepare_project_workspace(results_dir, result_dir, project_dir)

            self.assertTrue((project_dir / ".git").is_dir())
            self.assertTrue((project_dir / "CLAUDE.md").is_file())
            validate_benchmark_workspace(results_dir, result_dir, project_dir)

    def test_accepts_project_workspace_under_results_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            results_dir = Path(tmp) / "results"
            result_dir = results_dir / "opencode-model"
            project_dir = result_dir / "project"
            project_dir.mkdir(parents=True)
            init_project_git(project_dir)

            validate_benchmark_workspace(results_dir, result_dir, project_dir)

    def test_rejects_project_workspace_outside_results_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            results_dir = root / "results"
            result_dir = results_dir / "opencode-model"
            project_dir = root / "escaped-project"
            project_dir.mkdir(parents=True)
            init_project_git(project_dir)

            with self.assertRaisesRegex(
                RuntimeError,
                "outside results_dir.*expected workspace shape",
            ) as caught:
                validate_benchmark_workspace(results_dir, result_dir, project_dir)

            self.assertIn(str(project_dir.resolve()), str(caught.exception))

    def test_rejects_parent_git_top_level_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            results_dir = Path(tmp) / "results"
            result_dir = results_dir / "opencode-model"
            project_dir = result_dir / "project"
            project_dir.mkdir(parents=True)
            init_project_git(result_dir)

            with self.assertRaisesRegex(
                RuntimeError,
                "git top-level .* does not match project_dir .*expected workspace shape",
            ) as caught:
                validate_benchmark_workspace(results_dir, result_dir, project_dir)

            error = str(caught.exception)
            self.assertIn(str(result_dir.resolve()), error)
            self.assertIn(str(project_dir.resolve()), error)


if __name__ == "__main__":
    unittest.main()
