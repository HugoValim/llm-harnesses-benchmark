"""Tests that benchmark runners use the parent process env without isolation."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.claude_code_runner import _build_claude_env  # noqa: E402
from benchmark.config import BenchmarkConfig  # noqa: E402
from benchmark.runner import run_codex_phase, run_opencode_phase  # noqa: E402


def _minimal_bench(harness: str) -> BenchmarkConfig:
    runner: dict[str, object] = {}
    if harness == "opencode":
        runner = {
            "command": "opencode",
            "args": ["run", "--agent", "build", "--format", "json"],
        }
    return BenchmarkConfig(
        runner=runner,
        config_path=REPO_ROOT / "config" / "models.json",
        results_dir=Path("results"),
        harness=harness,
        timeout_seconds=60,
        no_progress_timeout_seconds=60,
        min_preview_output_tps=None,
        min_preview_samples=0,
        auto_skip_slow_preview=False,
        force=True,
        backend=None,
        selected_models=[],
        prompt="build",
        followup_prompt="check",
    )


class TestRunnerProcessEnv(unittest.TestCase):
    def test_run_opencode_phase_uses_parent_env(self) -> None:
        captured: dict[str, Any] = {}

        def fake_popen(*args: Any, **kwargs: Any) -> MagicMock:
            captured["env"] = kwargs.get("env")
            proc = MagicMock()
            proc.stdout = MagicMock()
            proc.stderr = MagicMock()
            proc.returncode = 0
            return proc

        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            project_dir = result_dir / "project"
            project_dir.mkdir(parents=True)
            prompt_path = result_dir / "prompt.txt"
            stdout_path = result_dir / "out.ndjson"
            stderr_path = result_dir / "err.log"
            bench = _minimal_bench("opencode")
            model = {
                "id": "test/model",
                "provider": "openrouter",
                "runner_type": "opencode",
                "slug": "demo",
            }
            with patch.dict(os.environ, {"BENCHMARK_ENV_PROBE": "opencode-parent"}, clear=False):
                with patch("benchmark.runner.subprocess.Popen", side_effect=fake_popen):
                    with patch("benchmark.runner.stream_process_output") as stream_mock:
                        stream_mock.return_value = MagicMock(
                            stdout="",
                            stderr="",
                            stalled=False,
                            stall_reason=None,
                            timed_out=False,
                            latest_preview_output_tps=None,
                            preview_average_output_tps=None,
                        )
                        with patch("benchmark.runner.parse_event_stream", return_value=[]):
                            with patch(
                                "benchmark.runner.extract_metrics",
                                return_value={
                                    "assistant_output": "",
                                    "finish_reason": "stop",
                                    "session_id": None,
                                    "tokens": {},
                                },
                            ):
                                run_opencode_phase(
                                    bench=bench,
                                    model=model,
                                    model_slug="demo",
                                    prompt="build",
                                    started_at="2026-01-01T00:00:00Z",
                                    project_dir=project_dir,
                                    prompt_path=prompt_path,
                                    stdout_path=stdout_path,
                                    stderr_path=stderr_path,
                                    result_path=None,
                                )

            env = captured.get("env")
            self.assertIsInstance(env, dict)
            assert isinstance(env, dict)
            self.assertEqual(env.get("BENCHMARK_ENV_PROBE"), "opencode-parent")
            self.assertEqual(env.get("OPENCODE_YOLO"), "1")
            self.assertEqual(env.get("OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS"), "true")
            self.assertIn("OPENCODE_CONFIG_CONTENT", env)
            config_content = env.get("OPENCODE_CONFIG_CONTENT")
            self.assertIsInstance(config_content, str)
            self.assertNotIn("XDG_DATA_HOME", env)

    def test_run_codex_phase_uses_parent_env(self) -> None:
        captured: dict[str, Any] = {}

        def fake_popen(*args: Any, **kwargs: Any) -> MagicMock:
            captured["env"] = kwargs.get("env")
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdout = MagicMock()
            proc.stderr = MagicMock()
            proc.returncode = 0
            return proc

        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            project_dir = result_dir / "project"
            project_dir.mkdir(parents=True)
            prompt_path = result_dir / "prompt.txt"
            stdout_path = result_dir / "out.ndjson"
            stderr_path = result_dir / "err.log"
            bench = _minimal_bench("codex")
            model = {
                "id": "gpt-test",
                "provider": "openai",
                "runner_type": "codex",
                "slug": "demo",
            }
            with patch.dict(os.environ, {"BENCHMARK_ENV_PROBE": "codex-parent"}, clear=False):
                with patch("benchmark.runner.subprocess.Popen", side_effect=fake_popen):
                    with patch("benchmark.runner.stream_process_output") as stream_mock:
                        stream_mock.return_value = MagicMock(
                            stdout="",
                            stderr="",
                            stalled=False,
                            stall_reason=None,
                            timed_out=False,
                            latest_preview_output_tps=None,
                            preview_average_output_tps=None,
                        )
                        with patch("benchmark.runner.parse_event_stream", return_value=[]):
                            with patch(
                                "benchmark.runner.extract_codex_metrics",
                                return_value={
                                    "assistant_output": "",
                                    "finish_reason": "stop",
                                    "session_id": None,
                                    "tokens": {},
                                },
                            ):
                                run_codex_phase(
                                    bench=bench,
                                    model=model,
                                    model_slug="demo",
                                    prompt="build",
                                    started_at="2026-01-01T00:00:00Z",
                                    project_dir=project_dir,
                                    prompt_path=prompt_path,
                                    stdout_path=stdout_path,
                                    stderr_path=stderr_path,
                                    result_path=None,
                                    for_benchmark_build=True,
                                )

            env = captured.get("env")
            self.assertIsInstance(env, dict)
            assert isinstance(env, dict)
            self.assertEqual(env.get("BENCHMARK_ENV_PROBE"), "codex-parent")
            self.assertNotIn("CODEX_HOME", env)

    def test_run_codex_phase_sets_codex_home_for_ollama_launch_codex(self) -> None:
        captured: dict[str, Any] = {}

        def fake_popen(*args: Any, **kwargs: Any) -> MagicMock:
            captured["env"] = kwargs.get("env")
            proc = MagicMock()
            proc.stdin = MagicMock()
            proc.stdout = MagicMock()
            proc.stderr = MagicMock()
            proc.returncode = 0
            return proc

        with TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "run_01"
            project_dir = result_dir / "project"
            project_dir.mkdir(parents=True)
            prompt_path = result_dir / "prompt.txt"
            stdout_path = result_dir / "out.ndjson"
            stderr_path = result_dir / "err.log"
            bench = _minimal_bench("codex")
            model = {
                "id": "gpt-test",
                "provider": "openai",
                "runner_type": "codex",
                "slug": "demo",
            }

            fake_home = Path(tmp) / "home"
            codex_home = fake_home / ".codex"
            codex_home.mkdir(parents=True)
            (codex_home / "config.toml").write_text('profile="ollama-launch"\n')

            with patch("pathlib.Path.home", return_value=fake_home):
                with patch.dict(os.environ, {"BENCHMARK_ENV_PROBE": "codex-parent"}, clear=False):
                    with patch("benchmark.runner.subprocess.Popen", side_effect=fake_popen):
                        with patch("benchmark.runner.stream_process_output") as stream_mock:
                            stream_mock.return_value = MagicMock(
                                stdout="",
                                stderr="",
                                stalled=False,
                                stall_reason=None,
                                timed_out=False,
                                latest_preview_output_tps=None,
                                preview_average_output_tps=None,
                            )
                            with patch("benchmark.runner.parse_event_stream", return_value=[]):
                                with patch(
                                    "benchmark.runner.extract_codex_metrics",
                                    return_value={
                                        "assistant_output": "",
                                        "finish_reason": "stop",
                                        "session_id": None,
                                        "tokens": {},
                                    },
                                ):
                                    run_codex_phase(
                                        bench=bench,
                                        model=model,
                                        model_slug="demo",
                                        prompt="build",
                                        started_at="2026-01-01T00:00:00Z",
                                        project_dir=project_dir,
                                        prompt_path=prompt_path,
                                        stdout_path=stdout_path,
                                        stderr_path=stderr_path,
                                        result_path=None,
                                        for_benchmark_build=True,
                                        command_prefix=["ollama", "launch", "--yes", "codex"],
                                    )

            env = captured.get("env")
            self.assertIsInstance(env, dict)
            assert isinstance(env, dict)
            self.assertIn("CODEX_HOME", env)
            self.assertEqual(env["CODEX_HOME"], str(result_dir / ".codex-home"))

    def test_build_claude_env_uses_parent_env(self) -> None:
        with patch.dict(os.environ, {"BENCHMARK_ENV_PROBE": "claude-parent"}, clear=False):
            env = _build_claude_env(
                variant={},
                log_tag="claude:demo",
            )
        self.assertEqual(env.get("BENCHMARK_ENV_PROBE"), "claude-parent")
        probe_home = os.environ.get("HOME")
        if probe_home is not None:
            self.assertEqual(env.get("HOME"), probe_home)


if __name__ == "__main__":
    unittest.main()
