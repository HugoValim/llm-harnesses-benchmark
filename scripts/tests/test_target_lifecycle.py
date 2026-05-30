"""Tests for shared target run lifecycle behavior."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.target_lifecycle import (  # noqa: E402
    PhaseRunRequest,
    TargetRunLifecycle,
    TargetRunPaths,
)


class RecordingPhaseRunner:
    def __init__(self) -> None:
        self.phase_names: list[str] = []

    def __call__(self, phase: PhaseRunRequest) -> dict[str, Any]:
        self.phase_names.append(phase.phase_name)
        phase.prompt_path.write_text(phase.prompt)
        phase.stdout_path.write_text("")
        phase.stderr_path.write_text("")
        return {
            "phase": phase.phase_name,
            "status": "completed",
            "elapsed_seconds": 0.25,
            "opencode_session_id": f"{phase.phase_name}-session",
            "project_summary": {"file_count": len(self.phase_names)},
            "tokens": {"total": len(self.phase_names)},
        }


class TestTargetRunLifecycle(unittest.TestCase):
    def test_runs_phase1_and_followup_then_persists_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_dir = root / "results" / "opencode-demo" / "run_01"
            paths = TargetRunPaths.opencode(result_dir)
            phase_runner = RecordingPhaseRunner()

            payload = TargetRunLifecycle(
                harness="opencode",
                slug="demo",
                results_dir=root / "results",
                paths=paths,
                force=True,
                prompt="build app",
                followup_prompt="check app",
                run_phase=phase_runner,
            ).run()

            self.assertEqual(phase_runner.phase_names, ["phase1", "phase2"])
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["elapsed_seconds"], 0.5)
            self.assertEqual(len(payload["phases"]), 2)
            self.assertEqual(payload["paths"]["project_dir"], str(paths.project_dir))
            self.assertEqual(
                payload["paths"]["followup_prompt"],
                str(paths.followup_prompt_path),
            )
            saved = json.loads(paths.result_path.read_text())
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(len(saved["phases"]), 2)

    def test_cli_paths_use_stream_artifact_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_dir = root / "results" / "claude-demo" / "run_01"
            paths = TargetRunPaths.cli(result_dir)

            payload = TargetRunLifecycle(
                harness="claude",
                slug="demo",
                results_dir=root / "results",
                paths=paths,
                force=True,
                prompt="build app",
                followup_prompt=None,
                run_phase=RecordingPhaseRunner(),
            ).run()

            self.assertEqual(
                payload["paths"]["stream_ndjson"],
                str(paths.stdout_path),
            )
            self.assertEqual(payload["paths"]["stderr_log"], str(paths.stderr_path))


if __name__ == "__main__":
    unittest.main()
