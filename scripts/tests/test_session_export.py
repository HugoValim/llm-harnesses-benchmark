"""Tests for opencode session export env parity with benchmark runs."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.agent_runtime_env import benchmark_env_for_harness  # noqa: E402
from benchmark.session_export import export_opencode_session  # noqa: E402


class TestSessionExportEnv(unittest.TestCase):
    def test_export_uses_isolated_xdg_data_home(self) -> None:
        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            result_dir.mkdir()
            export_path = result_dir / "session-export.json"
            captured_env: dict[str, str] = {}

            def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
                captured_env.update(kwargs.get("env", {}))
                return type(
                    "Completed",
                    (),
                    {"returncode": 0, "stdout": "{}", "stderr": ""},
                )()

            process_env = benchmark_env_for_harness(
                "opencode",
                os.environ.copy(),
                result_dir=result_dir,
            )
            process_env["OPENCODE_PERMISSION"] = "{}"

            with patch("benchmark.session_export.subprocess.run", side_effect=fake_run):
                export_opencode_session(
                    "session-123",
                    export_path,
                    process_env,
                    "demo-model",
                )

            self.assertTrue(captured_env["XDG_DATA_HOME"].endswith(".xdg-data"))


if __name__ == "__main__":
    unittest.main()
