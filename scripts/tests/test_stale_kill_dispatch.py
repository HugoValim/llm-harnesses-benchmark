"""Regression tests for _kill_stale_opencode_processes dispatch under run_model.

Covers the contract between run_benchmark.py's executor-level kill (run once
before the ThreadPoolExecutor) and run_model's per-call kill (gated by
``skip_stale_kill``). When the executor manages parallel cloud workers, every
worker MUST suppress its own kill — otherwise one worker's kill terminates a
sibling worker's live opencode child.
"""

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


class _SuccessfulPhase:
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


def _bench(results_dir: Path) -> BenchmarkConfig:
    return BenchmarkConfig(
        runner={},
        config_path=REPO_ROOT / "config" / "models.json",
        results_dir=results_dir,
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
        followup_prompt=None,
    )


def _model() -> dict[str, Any]:
    return {
        "id": "openrouter/test-model",
        "provider": "openrouter",
        "runner_type": "opencode",
        "slug": "fake_model",
    }


class TestStaleKillDispatch(unittest.TestCase):
    def test_skip_stale_kill_true_suppresses_kill(self) -> None:
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch.object(
                    runner_module, "run_opencode_phase", _SuccessfulPhase()
                ), patch.object(
                    runner_module, "export_opencode_session", return_value=None
                ), patch.object(
                    runner_module, "_kill_stale_opencode_processes"
                ) as kill_mock:
                    run_model(
                        _model(),
                        _bench(Path("results")),
                        1,
                        1,
                        skip_stale_kill=True,
                    )
                kill_mock.assert_not_called()
            finally:
                os.chdir(previous_cwd)

    def test_skip_stale_kill_false_invokes_kill(self) -> None:
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch.object(
                    runner_module, "run_opencode_phase", _SuccessfulPhase()
                ), patch.object(
                    runner_module, "export_opencode_session", return_value=None
                ), patch.object(
                    runner_module, "_kill_stale_opencode_processes"
                ) as kill_mock:
                    run_model(
                        _model(),
                        _bench(Path("results")),
                        1,
                        1,
                        skip_stale_kill=False,
                    )
                kill_mock.assert_called_once()
            finally:
                os.chdir(previous_cwd)

    def test_codex_runner_never_invokes_kill(self) -> None:
        previous_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                codex_model = {**_model(), "runner_type": "codex"}
                with patch.object(
                    runner_module, "run_codex_phase", _SuccessfulPhase()
                ), patch.object(
                    runner_module, "_kill_stale_opencode_processes"
                ) as kill_mock:
                    run_model(
                        codex_model,
                        _bench(Path("results")),
                        1,
                        1,
                        skip_stale_kill=False,
                    )
                kill_mock.assert_not_called()
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
