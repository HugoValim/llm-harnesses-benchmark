"""Tests for runtime verifier subprocess cleanup."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import analyze_results_runtime as runtime_module  # noqa: E402


class TimeoutProcess:
    pid = 1234

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def wait(self, timeout: int) -> int:
        if timeout == 1:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0


class TestRuntimeVerificationTermination(unittest.TestCase):
    def test_run_command_uses_shared_termination_on_timeout(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            with patch.object(
                runtime_module.subprocess, "Popen", TimeoutProcess
            ), patch.object(
                runtime_module,
                "terminate_process_group",
                create=True,
            ) as terminate:
                result = runtime_module.run_command(
                    ["fake-command"],
                    cwd=tmp_path,
                    env={},
                    timeout_seconds=1,
                    stdout_path=tmp_path / "stdout.log",
                    stderr_path=tmp_path / "stderr.log",
                )

            self.assertFalse(result.ok)
            self.assertEqual(result.exit_code, None)
            self.assertEqual(result.note, "timed out after 1s")
            terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
