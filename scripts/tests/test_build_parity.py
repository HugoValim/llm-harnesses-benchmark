"""Tests for benchmark build parity helpers and lifecycle wiring."""

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

from benchmark.build_parity import (  # noqa: E402
    FOLLOWUP_CONTINUITY_COLD,
    FRESH_SESSION_FALLBACK,
    build_followup_prompt,
    build_parity_metadata,
    wrap_primary_prompt,
)
from benchmark.target_lifecycle import (  # noqa: E402
    PhaseRunRequest,
    TargetRunLifecycle,
    TargetRunPaths,
)
from benchmark.util import prompt_sha256  # noqa: E402
import benchmark.runner as runner_module  # noqa: E402
from benchmark.config import BenchmarkConfig  # noqa: E402
from benchmark.runner import run_model  # noqa: E402


class TestBuildFollowupPrompt(unittest.TestCase):
    def test_cold_followup_always_appends_fallback(self) -> None:
        followup = "validate docker"
        result = build_followup_prompt(followup, continuity=FOLLOWUP_CONTINUITY_COLD)
        self.assertEqual(result, followup + FRESH_SESSION_FALLBACK)


class TestWrapPrimaryPrompt(unittest.TestCase):
    def test_wrap_primary_prompt_includes_agent_rules_when_enabled(self) -> None:
        wrapped = wrap_primary_prompt("build the app", include_agent_rules=True)
        self.assertIn("---", wrapped)
        self.assertTrue(wrapped.endswith("build the app"))
        self.assertIn("Prompt-Version: agent-coding-rules", wrapped)

    def test_wrap_primary_prompt_omits_rules_when_disabled(self) -> None:
        wrapped = wrap_primary_prompt("build the app", include_agent_rules=False)
        self.assertIn("---", wrapped)
        self.assertNotIn("Prompt-Version: agent-coding-rules", wrapped)


class TestBuildParityMetadata(unittest.TestCase):
    def test_build_parity_metadata_shape(self) -> None:
        metadata = build_parity_metadata(
            continuity="cold",
            primary_prompt_wrapped=True,
            runtime_isolation={"HOME": "/tmp/run/.agent-home"},
        )
        self.assertEqual(
            metadata,
            {
                "followup_continuity": "cold",
                "primary_prompt_wrapped": True,
                "runtime_isolation": {"HOME": "/tmp/run/.agent-home"},
            },
        )


class SessionCapturingPhaseRunner:
    def __init__(self) -> None:
        self.requests: list[PhaseRunRequest] = []

    def __call__(self, request: PhaseRunRequest) -> dict[str, Any]:
        self.requests.append(request)
        request.prompt_path.write_text(request.prompt)
        request.stdout_path.write_text("")
        request.stderr_path.write_text("")
        return {
            "phase": request.phase_name,
            "status": "completed",
            "elapsed_seconds": 0.1,
            "opencode_session_id": "phase1-session-id",
        }


class TestTargetLifecycleColdContinuity(unittest.TestCase):
    def test_target_lifecycle_cold_ignores_session_selector(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_dir = root / "results" / "opencode-demo" / "run_01"
            paths = TargetRunPaths.opencode(result_dir)
            phase_runner = SessionCapturingPhaseRunner()

            TargetRunLifecycle(
                harness="opencode",
                slug="demo",
                results_dir=root / "results",
                paths=paths,
                force=True,
                prompt="build app",
                followup_prompt="check app",
                run_phase=phase_runner,
                followup_continuity=FOLLOWUP_CONTINUITY_COLD,
            ).run()

            self.assertEqual(len(phase_runner.requests), 2)
            phase2 = phase_runner.requests[1]
            self.assertEqual(phase2.phase_name, "phase2")
            self.assertIsNone(phase2.continue_session_id)
            self.assertIn(FRESH_SESSION_FALLBACK, phase2.prompt)


class TestWrapPrimaryPromptHash(unittest.TestCase):
    def test_wrap_primary_prompt_produces_different_hash_than_raw(self) -> None:
        raw = "build the app"
        wrapped = wrap_primary_prompt(raw)
        self.assertNotEqual(prompt_sha256(raw), prompt_sha256(wrapped))


class PhaseKwargCapturingRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        Path(str(kwargs["prompt_path"])).write_text(str(kwargs["prompt"]))
        Path(str(kwargs["stdout_path"])).write_text("")
        Path(str(kwargs["stderr_path"])).write_text("")
        return {
            "elapsed_seconds": 0.1,
            "model": kwargs["model"],
            "opencode_session_id": f"{kwargs['phase_name']}-session",
            "paths": {},
            "project_summary": {"file_count": 1},
            "status": "completed",
            "tokens": {},
            "runtime_isolation": {},
        }


class TestRunModelBuildParity(unittest.TestCase):
    def test_run_model_phase2_opencode_has_no_session_continue(self) -> None:
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
                phase_runner = PhaseKwargCapturingRunner()

                with patch.object(
                    runner_module, "run_opencode_phase", phase_runner
                ), patch.object(
                    runner_module,
                    "export_opencode_session",
                    return_value=None,
                ):
                    payload = run_model(model, bench, 1, 1, skip_stale_kill=True)

                phase2_calls = [
                    call
                    for call in phase_runner.calls
                    if call.get("phase_name") == "phase2"
                ]
                self.assertEqual(len(phase2_calls), 1)
                self.assertIsNone(phase2_calls[0].get("continue_session_id"))
                self.assertIn(FRESH_SESSION_FALLBACK, str(phase2_calls[0]["prompt"]))
                build_parity = payload.get("build_parity")
                self.assertIsInstance(build_parity, dict)
                assert isinstance(build_parity, dict)
                self.assertEqual(build_parity.get("followup_continuity"), "cold")
                self.assertTrue(build_parity.get("primary_prompt_wrapped"))
            finally:
                os.chdir(previous_cwd)


if __name__ == "__main__":
    unittest.main()
