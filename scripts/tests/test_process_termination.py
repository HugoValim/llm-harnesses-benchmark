"""Regression tests for process-group termination."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import terminate_process_group  # noqa: E402


class FakeProcess:
    pid = 1234

    def __init__(self) -> None:
        self.killed = False
        self.terminated = False

    def wait(self, timeout: int) -> None:
        raise subprocess.TimeoutExpired("fake", timeout)

    def kill(self) -> None:
        self.killed = True

    def terminate(self) -> None:
        self.terminated = True


class TestTerminateProcessGroup(unittest.TestCase):
    def test_escalates_to_sigkill_after_timeout(self) -> None:
        process = FakeProcess()

        with patch.object(os, "killpg") as killpg:
            terminate_process_group(process)  # type: ignore[arg-type]

        self.assertEqual(
            killpg.call_args_list[0].args,
            (process.pid, signal.SIGTERM),
        )
        self.assertEqual(
            killpg.call_args_list[1].args,
            (process.pid, signal.SIGKILL),
        )

    def test_falls_back_to_process_methods_on_permission_error(self) -> None:
        process = FakeProcess()

        with patch.object(os, "killpg", side_effect=PermissionError):
            terminate_process_group(process)  # type: ignore[arg-type]

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)


if __name__ == "__main__":
    unittest.main()
