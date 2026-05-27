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
    payload_hit_usage_limit,
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

    def test_claude_rate_limit_event(self) -> None:
        event = {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "rejected",
                "resetsAt": int(time.time()) + 120,
            },
        }
        self.assertTrue(stream_event_looks_rate_limited(event))

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
