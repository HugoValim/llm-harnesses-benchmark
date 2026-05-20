"""Tests for runner result path payloads."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmark.runner as runner_module  # noqa: E402
from benchmark.config import BenchmarkConfig  # noqa: E402
from benchmark.runner import run_model  # noqa: E402


class FailingLocalBackend:
    backend_name = "fake"

    def list_active(self) -> list[str]:
        return []

    def ensure_model_ready(
        self, model_name: str, model_slug: str, context_limit: int | None
    ) -> tuple[bool, str]:
        return False, f"model {model_name} for {model_slug} unavailable"


class SuccessfulPhaseRunner:
    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        Path(kwargs["prompt_path"]).write_text(kwargs["prompt"])
        Path(kwargs["stdout_path"]).write_text("")
        Path(kwargs["stderr_path"]).write_text("")
        return {
            "elapsed_seconds": 0.1,
            "model": kwargs["model"],
            "opencode_session_id": f"{kwargs['phase_name']}-session",
            "paths": {},
            "project_summary": {"file_count": 1},
            "status": "completed",
            "tokens": {},
        }


class TestRunnerPaths(unittest.TestCase):
    def test_preflight_failure_paths_are_absolute(self) -> None:
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                bench = BenchmarkConfig(
                    runner={},
                    config_path=REPO_ROOT / "config" / "models.json",
                    results_dir=Path("results"),
                    harness="opencode",
                    timeout_seconds=1,
                    no_progress_timeout_seconds=1,
                    min_preview_output_tps=None,
                    min_preview_samples=0,
                    auto_skip_slow_preview=False,
                    force=True,
                    backend=FailingLocalBackend(),
                    selected_models=[],
                    prompt="build app",
                    followup_prompt=None,
                )
                model = {
                    "id": "ollama/test-model",
                    "provider": "ollama",
                    "runner_type": "opencode",
                    "slug": "fake_model",
                }

                payload = run_model(model, bench, 1, 1)

                expected_root = Path(tmp) / "results" / "opencode-fake_model"
                self.assertEqual(
                    Path(payload["paths"]["project_dir"]),
                    expected_root / "project",
                )
                self.assertEqual(
                    Path(payload["paths"]["prompt"]), expected_root / "prompt.txt"
                )
                self.assertEqual(
                    Path(payload["paths"]["stderr"]),
                    expected_root / "opencode-stderr.log",
                )
                self.assertEqual(
                    Path(payload["paths"]["stdout"]),
                    expected_root / "opencode-output.ndjson",
                )
                self.assertTrue(Path(payload["paths"]["project_dir"]).is_absolute())
            finally:
                os.chdir(previous_cwd)

    def test_followup_artifact_paths_are_absolute(self) -> None:
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                bench = BenchmarkConfig(
                    runner={},
                    config_path=REPO_ROOT / "config" / "models.json",
                    results_dir=Path("results"),
                    harness="opencode",
                    timeout_seconds=1,
                    no_progress_timeout_seconds=1,
                    min_preview_output_tps=None,
                    min_preview_samples=0,
                    auto_skip_slow_preview=False,
                    force=True,
                    backend=None,
                    selected_models=[],
                    prompt="build app",
                    followup_prompt="check app",
                )
                model = {
                    "id": "openrouter/test-model",
                    "provider": "openrouter",
                    "runner_type": "opencode",
                    "slug": "fake_model",
                }

                with patch.object(
                    runner_module, "run_opencode_phase", SuccessfulPhaseRunner()
                ), patch.object(
                    runner_module,
                    "export_opencode_session",
                    return_value=(
                        Path(tmp)
                        / "results"
                        / "opencode-fake_model"
                        / "session-export.json"
                    ),
                ):
                    payload = run_model(model, bench, 1, 1, skip_stale_kill=True)

                expected_root = Path(tmp) / "results" / "opencode-fake_model"
                self.assertEqual(
                    Path(payload["paths"]["followup_prompt"]),
                    expected_root / "followup-prompt.txt",
                )
                self.assertEqual(
                    Path(payload["paths"]["followup_stderr"]),
                    expected_root / "followup-opencode-stderr.log",
                )
                self.assertEqual(
                    Path(payload["paths"]["followup_stdout"]),
                    expected_root / "followup-opencode-output.ndjson",
                )
                self.assertTrue(Path(payload["paths"]["followup_prompt"]).is_absolute())
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
