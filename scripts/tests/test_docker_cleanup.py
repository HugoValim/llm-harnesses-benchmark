"""Tests for post-benchmark Docker prune cleanup."""

from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.docker_cleanup import prune_docker_after_benchmark  # noqa: E402
from run_benchmark import _cleanup_docker_after_benchmark  # noqa: E402


class TestPruneDockerAfterBenchmark(unittest.TestCase):
    def test_skips_when_docker_missing(self) -> None:
        with patch("benchmark.docker_cleanup.shutil.which", return_value=None):
            result = prune_docker_after_benchmark()

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "docker not on PATH")

    def test_runs_builder_then_system_prune_with_force(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            calls.append(cmd)
            completed = MagicMock()
            completed.returncode = 0
            completed.stdout = "Total reclaimed space: 12.5GB\n"
            completed.stderr = ""
            return completed

        with patch("benchmark.docker_cleanup.shutil.which", return_value="/usr/bin/docker"), patch(
            "benchmark.docker_cleanup.subprocess.run", side_effect=fake_run
        ):
            result = prune_docker_after_benchmark(force=True)

        self.assertFalse(result["skipped"])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(
            calls,
            [
                ["docker", "builder", "prune", "-a", "-f"],
                ["docker", "system", "prune", "-a", "-f"],
            ],
        )
        self.assertEqual(result["steps"][0]["reclaimed"], "12.5GB")
        self.assertTrue(result["steps"][1]["ok"])

    def test_omits_force_flag_when_force_false(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            calls.append(cmd)
            completed = MagicMock()
            completed.returncode = 0
            completed.stdout = ""
            completed.stderr = ""
            return completed

        with patch("benchmark.docker_cleanup.shutil.which", return_value="/usr/bin/docker"), patch(
            "benchmark.docker_cleanup.subprocess.run", side_effect=fake_run
        ):
            prune_docker_after_benchmark(force=False)

        self.assertEqual(
            calls,
            [
                ["docker", "builder", "prune", "-a"],
                ["docker", "system", "prune", "-a"],
            ],
        )


class TestCleanupDockerAfterBenchmark(unittest.TestCase):
    def _args(self, **kwargs: bool) -> argparse.Namespace:
        defaults = {"no_docker_prune": False}
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_skips_when_no_docker_prune(self) -> None:
        with patch("run_benchmark.prune_docker_after_benchmark") as prune_mock:
            _cleanup_docker_after_benchmark(self._args(no_docker_prune=True))
        prune_mock.assert_not_called()

    def test_logs_prune_failure(self) -> None:
        with patch(
            "run_benchmark.prune_docker_after_benchmark",
            return_value={
                "skipped": False,
                "steps": [
                    {
                        "label": "builder",
                        "ok": False,
                        "returncode": 1,
                        "stderr": "permission denied",
                    },
                ],
            },
        ), patch("run_benchmark.print_line") as print_mock:
            _cleanup_docker_after_benchmark(self._args())

        messages = [call.args[0] for call in print_mock.call_args_list]
        self.assertTrue(any("builder prune failed" in msg for msg in messages))

    def test_invokes_prune_by_default(self) -> None:
        with patch(
            "run_benchmark.prune_docker_after_benchmark",
            return_value={
                "skipped": False,
                "steps": [
                    {
                        "label": "builder",
                        "ok": True,
                        "reclaimed": "60GB",
                        "returncode": 0,
                    },
                    {"label": "system", "ok": True, "reclaimed": None, "returncode": 0},
                ],
            },
        ) as prune_mock, patch("run_benchmark.print_line") as print_mock:
            _cleanup_docker_after_benchmark(self._args())

        prune_mock.assert_called_once_with()
        messages = [call.args[0] for call in print_mock.call_args_list]
        self.assertTrue(any("builder prune complete" in msg for msg in messages))
        self.assertTrue(any("system prune complete" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
