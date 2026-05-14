"""Tests for provider usage / rate limit detection and abort signalling."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.claude_code_runner import (  # noqa: E402
    ClaudeCodeStreamResult,
    run_variant,
)
from benchmark.phase_result import derive_phase_status  # noqa: E402
from benchmark.report import _rederive_status  # noqa: E402
from benchmark.stream_state import ActionKind, EventStreamState  # noqa: E402
from benchmark.util import USAGE_LIMIT_REACHED, contains_usage_limit  # noqa: E402
from run_benchmark import _phase_hit_usage_limit  # noqa: E402


class TestContainsUsageLimit(unittest.TestCase):
    def test_matches_common_provider_messages(self) -> None:
        self.assertTrue(contains_usage_limit("Claude.ai usage limit reached"))
        self.assertTrue(contains_usage_limit("Error: rate limit exceeded"))
        self.assertTrue(contains_usage_limit("Too Many Requests"))
        self.assertTrue(contains_usage_limit("model overloaded"))

    def test_no_match_on_unrelated_errors(self) -> None:
        self.assertFalse(contains_usage_limit("syntax error near unexpected token"))
        self.assertFalse(contains_usage_limit(""))


class TestStreamStateUsageLimit(unittest.TestCase):
    def test_immediate_stall_on_rate_limit_message(self) -> None:
        state = EventStreamState(
            model_slug="m",
            min_preview_output_tps=None,
            min_preview_samples=2,
        )
        action = state.process_event(
            {"type": "error", "message": "rate limit exceeded"}
        )
        self.assertEqual(action.kind, ActionKind.STALL)
        self.assertEqual(action.reason, USAGE_LIMIT_REACHED)


class TestRederiveStatusUsageLimit(unittest.TestCase):
    def test_report_only_keeps_usage_limit(self) -> None:
        row = {
            "stalled": True,
            "stall_reason": USAGE_LIMIT_REACHED,
            "timed_out": False,
            "finish_reason": None,
            "exit_code": 1,
        }
        self.assertEqual(
            _rederive_status(row, {"works_as_intended": "no"}),
            USAGE_LIMIT_REACHED,
        )


class TestDerivePhaseStatusUsageLimit(unittest.TestCase):
    def test_usage_limit_wins_over_timeout_when_both_stalled(self) -> None:
        status = derive_phase_status(
            timed_out=True,
            stalled=True,
            stall_reason=USAGE_LIMIT_REACHED,
            finish_reason=None,
            exit_code=None,
            works_as_intended="no",
        )
        self.assertEqual(status, USAGE_LIMIT_REACHED)


class TestPhaseHitUsageLimit(unittest.TestCase):
    def test_top_level_status(self) -> None:
        self.assertTrue(
            _phase_hit_usage_limit({"status": USAGE_LIMIT_REACHED, "phases": []})
        )

    def test_nested_phase(self) -> None:
        self.assertTrue(
            _phase_hit_usage_limit(
                {
                    "status": "failed",
                    "phases": [{"status": USAGE_LIMIT_REACHED}],
                }
            )
        )

    def test_empty_payload(self) -> None:
        self.assertFalse(_phase_hit_usage_limit(None))
        self.assertFalse(_phase_hit_usage_limit({}))


class TestRunVariantUsageLimitStatus(unittest.TestCase):
    def test_status_from_stream_usage_limit_flag(self) -> None:
        variant = {
            "slug": "test_variant",
            "main_model": "test-model",
        }
        fake_result = ClaudeCodeStreamResult(
            stdout="",
            stderr="",
            timed_out=False,
            stalled=True,
            stall_reason=USAGE_LIMIT_REACHED,
            usage_limit_reached=True,
            final_result_event={"is_error": True, "message": "usage limit"},
        )
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            with patch("benchmark.claude_code_runner.init_project_git"), patch(
                "benchmark.claude_code_runner.validate_benchmark_workspace"
            ), patch("benchmark.claude_code_runner.write_project_context"), patch(
                "benchmark.claude_code_runner.write_project_agent"
            ), patch(
                "benchmark.claude_code_runner.subprocess.Popen",
                return_value=mock_proc,
            ), patch(
                "benchmark.claude_code_runner.stream_process",
                return_value=fake_result,
            ):
                payload = run_variant(
                    variant=variant,
                    prompt="hi",
                    results_dir=results_dir,
                    timeout_seconds=60,
                    no_progress_timeout_seconds=30,
                    force=True,
                )
        self.assertEqual(payload["status"], USAGE_LIMIT_REACHED)

    def test_status_from_final_event_text_without_stream_flag(self) -> None:
        variant = {
            "slug": "test_variant2",
            "main_model": "test-model",
        }
        final = {"is_error": True, "message": "usage limit reached for your plan"}
        fake_result = ClaudeCodeStreamResult(
            stdout="",
            stderr="",
            timed_out=False,
            stalled=False,
            stall_reason=None,
            usage_limit_reached=False,
            final_result_event=final,
        )
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            with patch("benchmark.claude_code_runner.init_project_git"), patch(
                "benchmark.claude_code_runner.validate_benchmark_workspace"
            ), patch("benchmark.claude_code_runner.write_project_context"), patch(
                "benchmark.claude_code_runner.write_project_agent"
            ), patch(
                "benchmark.claude_code_runner.subprocess.Popen",
                return_value=mock_proc,
            ), patch(
                "benchmark.claude_code_runner.stream_process",
                return_value=fake_result,
            ):
                payload = run_variant(
                    variant=variant,
                    prompt="hi",
                    results_dir=results_dir,
                    timeout_seconds=60,
                    no_progress_timeout_seconds=30,
                    force=True,
                )
        self.assertEqual(payload["status"], USAGE_LIMIT_REACHED)
        self.assertTrue(contains_usage_limit(json.dumps(final)))


if __name__ == "__main__":
    unittest.main()
