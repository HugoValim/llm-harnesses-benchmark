"""Tests for rate-limit reset extraction and capped wait/retry."""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.rate_limit import (  # noqa: E402
    RateLimitWaitPolicy,
    extract_rate_limit_wait_seconds,
    extract_session_id_from_paths,
    payload_hit_usage_limit,
    run_with_rate_limit_resume,
    run_with_rate_limit_retry,
    stream_event_looks_rate_limited,
    text_looks_rate_limited,
    wait_for_rate_limit_reset,
)
from benchmark.util import USAGE_LIMIT_REACHED  # noqa: E402


class TestRateLimitDetection(unittest.TestCase):
    def test_session_limit_text(self) -> None:
        self.assertTrue(
            text_looks_rate_limited(
                "You've hit your session limit · resets 2:40pm (Europe/Berlin)"
            )
        )

    def test_file_size_with_429_substring_is_not_rate_limited(self) -> None:
        """ls -la output can include byte counts like 42958276 — not HTTP 429."""
        tool_result = json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "content": "-rwxrwxr-x 1 hugo hugo 42958276 May 27 tailwindcss",
                        }
                    ],
                },
            }
        )
        self.assertFalse(text_looks_rate_limited(tool_result))
        self.assertFalse(stream_event_looks_rate_limited(json.loads(tool_result)))

    def test_cursor_read_tool_filesize_429_is_not_rate_limited(self) -> None:
        """Cursor readToolCall metadata uses fileSize bytes — not HTTP 429."""
        event = {
            "type": "tool_call",
            "subtype": "completed",
            "tool_call": {
                "readToolCall": {
                    "args": {"path": "/project/config/asgi.py"},
                    "result": {
                        "success": {
                            "content": '"""ASGI config."""\n',
                            "totalLines": 18,
                            "fileSize": 429,
                            "path": "/project/config/asgi.py",
                        }
                    },
                }
            },
        }
        self.assertFalse(text_looks_rate_limited(json.dumps(event)))
        self.assertFalse(stream_event_looks_rate_limited(event))

    def test_http_429_status_still_detected(self) -> None:
        self.assertTrue(text_looks_rate_limited('{"status":429,"error":"too many requests"}'))

    def test_claude_rate_limit_event(self) -> None:
        event = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "resetsAt": int(time.time()) + 120,
            },
        }
        self.assertTrue(stream_event_looks_rate_limited(event))

    def test_claude_allowed_rate_limit_event_is_not_throttled(self) -> None:
        """Telemetry events with status=allowed must not stall the harness."""
        event = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "resetsAt": 1779903600,
                "rateLimitType": "five_hour",
                "overageStatus": "rejected",
                "overageDisabledReason": "org_level_disabled",
            },
        }
        self.assertFalse(stream_event_looks_rate_limited(event))
        self.assertIsNone(extract_rate_limit_wait_seconds(json.dumps(event)))

    def test_payload_usage_limit_status(self) -> None:
        self.assertTrue(payload_hit_usage_limit({"status": USAGE_LIMIT_REACHED}))


class TestResetExtraction(unittest.TestCase):
    def test_extract_resets_at_from_claude_stream(self) -> None:
        reset_at = int(time.time()) + 300
        line = json.dumps(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {"resetsAt": reset_at, "status": "rejected"},
            }
        )
        wait = extract_rate_limit_wait_seconds(line)
        self.assertIsNotNone(wait)
        assert wait is not None
        self.assertGreaterEqual(wait, 250)
        self.assertLessEqual(wait, 305)

    def test_extract_retry_after_from_text(self) -> None:
        wait = extract_rate_limit_wait_seconds("retry after 90 seconds")
        self.assertEqual(wait, 90)


class TestWaitPolicy(unittest.TestCase):
    @patch("benchmark.rate_limit.time.sleep")
    def test_known_reset_waits_with_jitter(self, sleep_mock) -> None:
        policy = RateLimitWaitPolicy(cap_seconds=3600)
        should_retry, slept = wait_for_rate_limit_reset(
            log_tag="test",
            policy=policy,
            wait_seconds=120,
            attempt=1,
        )
        self.assertTrue(should_retry)
        self.assertGreaterEqual(slept, 120)
        self.assertLessEqual(slept, 150)
        sleep_mock.assert_called_once()

    @patch("benchmark.rate_limit.time.sleep")
    def test_long_reset_waits_at_poll_interval(self, sleep_mock) -> None:
        policy = RateLimitWaitPolicy(cap_seconds=20_000, poll_interval_seconds=1800)
        should_retry, slept = wait_for_rate_limit_reset(
            log_tag="test",
            policy=policy,
            wait_seconds=14_913,
            attempt=1,
        )
        self.assertTrue(should_retry)
        self.assertGreaterEqual(slept, 1800)
        self.assertLessEqual(slept, 1830)
        sleep_mock.assert_called_once()

    @patch("benchmark.rate_limit.time.sleep")
    def test_unknown_reset_waits_at_poll_interval(self, sleep_mock) -> None:
        policy = RateLimitWaitPolicy(cap_seconds=3600, poll_interval_seconds=300)
        should_retry, slept = wait_for_rate_limit_reset(
            log_tag="test",
            policy=policy,
            wait_seconds=None,
            attempt=3,
        )
        self.assertTrue(should_retry)
        self.assertGreaterEqual(slept, 300)
        self.assertLessEqual(slept, 330)
        sleep_mock.assert_called_once()

    @patch("benchmark.rate_limit.time.sleep")
    def test_zero_cap_does_not_wait(self, sleep_mock) -> None:
        policy = RateLimitWaitPolicy(cap_seconds=0)
        should_retry, slept = wait_for_rate_limit_reset(
            log_tag="test",
            policy=policy,
            wait_seconds=120,
            attempt=1,
        )
        self.assertFalse(should_retry)
        self.assertEqual(slept, 0)
        sleep_mock.assert_not_called()


class TestSessionExtraction(unittest.TestCase):
    def test_extract_session_id_from_stream(self) -> None:
        line = json.dumps(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "abc-123",
            }
        )
        self.assertEqual(extract_session_id_from_paths(line), "abc-123")


class TestResumeLoop(unittest.TestCase):
    @patch("benchmark.rate_limit.wait_for_rate_limit_reset")
    def test_resumes_same_session_after_rate_limit(self, wait_mock) -> None:
        wait_mock.return_value = (True, 10)
        calls: list[tuple[bool, str | None]] = []

        def run_segment(resume: bool, session_id: str | None) -> dict:
            calls.append((resume, session_id))
            if len(calls) == 1:
                return {
                    "status": USAGE_LIMIT_REACHED,
                    "paths": {
                        "stream_ndjson": json.dumps(
                            {"type": "system", "session_id": "sess-1"}
                        )
                    },
                }
            return {"status": "completed", "paths": {}}

        payload = run_with_rate_limit_resume(
            log_tag="test",
            policy=RateLimitWaitPolicy(cap_seconds=3600),
            run_segment=run_segment,
            capture_paths=lambda phase_payload: [
                phase_payload.get("paths", {}).get("stream_ndjson")
            ],
        )
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(calls[0], (False, None))
        self.assertEqual(calls[1], (True, "sess-1"))
        wait_mock.assert_called_once()


class TestRetryLoop(unittest.TestCase):
    @patch("benchmark.rate_limit.wait_for_rate_limit_reset")
    def test_retries_until_success(self, wait_mock) -> None:
        wait_mock.return_value = (True, 10)
        calls = {"n": 0}

        def run_once() -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                return {"status": USAGE_LIMIT_REACHED, "paths": {}}
            return {"status": "completed", "paths": {}}

        payload = run_with_rate_limit_retry(
            log_tag="test",
            policy=RateLimitWaitPolicy(cap_seconds=3600),
            run_once=run_once,
            capture_paths=lambda _payload: [],
        )
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(calls["n"], 2)
        wait_mock.assert_called_once()

    @patch("benchmark.rate_limit.wait_for_rate_limit_reset")
    def test_cap_exhaustion_marks_usage_limit(self, wait_mock) -> None:
        wait_mock.return_value = (False, 0)
        payload = run_with_rate_limit_retry(
            log_tag="test",
            policy=RateLimitWaitPolicy(cap_seconds=0),
            run_once=lambda: {"status": USAGE_LIMIT_REACHED, "paths": {}},
            capture_paths=lambda _payload: [],
        )
        self.assertEqual(payload["status"], USAGE_LIMIT_REACHED)
        self.assertTrue(payload.get("rate_limit_wait_exhausted"))


if __name__ == "__main__":
    unittest.main()
