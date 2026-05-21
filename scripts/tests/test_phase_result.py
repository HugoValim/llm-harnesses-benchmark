"""Tests for shared benchmark phase result assembly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.phase_result import build_phase_payload, derive_phase_status  # noqa: E402


class TestPhaseStatus(unittest.TestCase):
    def test_timeout_wins_over_other_completion_signals(self) -> None:
        status = derive_phase_status(
            timed_out=True,
            stalled=False,
            finish_reason="stop",
            exit_code=0,
            works_as_intended="yes",
        )

        self.assertEqual(status, "timeout")

    def test_stalled_phase_is_failed(self) -> None:
        status = derive_phase_status(
            timed_out=False,
            stalled=True,
            finish_reason="stop",
            exit_code=0,
            works_as_intended="yes",
        )

        self.assertEqual(status, "failed")


class TestPhasePayload(unittest.TestCase):
    def test_build_phase_payload_preserves_public_result_fields(self) -> None:
        payload = build_phase_payload(
            phase_name="phase1",
            assistant_output="assistant text",
            command=["opencode", "run"],
            continued_from_session="session-parent",
            elapsed_seconds=2.0,
            ended_at="2026-05-14T10:00:01Z",
            exit_code=0,
            finish_reason="stop",
            model={"slug": "demo", "id": "provider/model"},
            session_id="session-child",
            paths={
                "project_dir": "/tmp/result/project",
                "prompt": "/tmp/result/prompt.txt",
                "stderr": "/tmp/result/stderr.log",
                "stdout": "/tmp/result/stdout.ndjson",
            },
            project_summary={"works_as_intended": "yes", "file_count": 3},
            prompt="build app",
            started_at="2026-05-14T10:00:00Z",
            stderr="stderr text",
            stalled=False,
            stall_reason=None,
            timed_out=False,
            timeout_seconds=10,
            no_progress_timeout_seconds=5,
            tokens={"input": 2, "output": 4, "total": 6},
            harness_metrics={
                "preview_output_tokens_per_second": 1.5,
                "preview_output_tokens_per_second_average": 1.25,
            },
        )

        self.assertEqual(
            set(payload),
            {
                "phase",
                "assistant_output_excerpt",
                "command",
                "continued_from_session",
                "elapsed_seconds",
                "ended_at",
                "exit_code",
                "finish_reason",
                "model",
                "opencode_session_id",
                "paths",
                "project_summary",
                "prompt_sha256",
                "started_at",
                "status",
                "stderr_excerpt",
                "stalled",
                "stall_reason",
                "timed_out",
                "timeout_seconds",
                "no_progress_timeout_seconds",
                "tokens",
                "preview_output_tokens_per_second",
                "preview_output_tokens_per_second_average",
                "tokens_per_second",
                "output_tokens_per_second",
            },
        )
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["tokens_per_second"], 3.0)
        self.assertEqual(payload["output_tokens_per_second"], 2.0)

    def test_terminal_stop_with_working_project_is_completed(self) -> None:
        status = derive_phase_status(
            timed_out=False,
            stalled=False,
            finish_reason="stop",
            exit_code=1,
            works_as_intended="yes",
        )

        self.assertEqual(status, "completed")

    def test_terminal_stop_with_nonworking_project_is_completed_with_errors(
        self,
    ) -> None:
        status = derive_phase_status(
            timed_out=False,
            stalled=False,
            finish_reason="stop",
            exit_code=1,
            works_as_intended="no",
        )

        self.assertEqual(status, "completed_with_errors")

    def test_nonzero_exit_without_terminal_stop_is_failed(self) -> None:
        status = derive_phase_status(
            timed_out=False,
            stalled=False,
            finish_reason=None,
            exit_code=1,
            works_as_intended="yes",
        )

        self.assertEqual(status, "failed")


if __name__ == "__main__":
    unittest.main()
