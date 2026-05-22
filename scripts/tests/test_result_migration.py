"""Tests for result.json schema v1 → v2 migration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import (  # noqa: E402
    RESULT_SCHEMA_VERSION,
    _deduce_harness,
    migrate_to_v2,
)

V1_OPENCODE = {
    "status": "completed",
    "elapsed_seconds": 123.4,
    "file_count": 42,
    "model": {"slug": "test-model", "label": "Test Model", "provider": "openrouter"},
    "opencode_session_id": "sess_abc",
    "tokens": {"total": 5000},
    "tokens_per_second": 40.5,
    "paths": {"project_dir": "/tmp/results/opencode-test-model/project"},
    "finish_reason": "stop",
}

V1_CLAUDE = {
    "slug": "claude-sonnet",
    "status": "completed",
    "elapsed_seconds": 200.0,
    "file_count": 30,
    "main_model": "claude_sonnet_4_6",
    "model_usage": {"claude-sonnet-4-6": {"inputTokens": 1000, "outputTokens": 500}},
    "subagent_invocation_counts": {"explore": 3},
}

V1_CURSOR = {
    "slug": "cursor-gpt5",
    "status": "completed",
    "elapsed_seconds": 180.0,
    "file_count": 25,
    "main_model": "gpt-5",
    "tool_use_counts": {"write /app/file.py": 5, "shell ls": 3},
}


class TestDeduceHarness(unittest.TestCase):
    def test_opencode(self) -> None:
        self.assertEqual(_deduce_harness(V1_OPENCODE), "opencode")

    def test_claude(self) -> None:
        self.assertEqual(_deduce_harness(V1_CLAUDE), "claude")

    def test_cursor(self) -> None:
        self.assertEqual(_deduce_harness(V1_CURSOR), "cursor")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(_deduce_harness({"status": "completed"}))


class TestMigrateToV2(unittest.TestCase):
    def test_adds_schema_version(self) -> None:
        row = migrate_to_v2(dict(V1_OPENCODE))
        self.assertEqual(row["result_schema_version"], RESULT_SCHEMA_VERSION)

    def test_adds_harness_for_opencode(self) -> None:
        row = migrate_to_v2(dict(V1_OPENCODE))
        self.assertEqual(row["harness"], "opencode")

    def test_adds_harness_for_claude(self) -> None:
        row = migrate_to_v2(dict(V1_CLAUDE))
        self.assertEqual(row["harness"], "claude")

    def test_adds_harness_for_cursor(self) -> None:
        row = migrate_to_v2(dict(V1_CURSOR))
        self.assertEqual(row["harness"], "cursor")

    def test_adds_phases_when_missing(self) -> None:
        row = migrate_to_v2(dict(V1_OPENCODE))
        self.assertIn("phases", row)
        self.assertEqual(len(row["phases"]), 1)
        self.assertEqual(row["phases"][0]["phase"], "phase1")
        self.assertEqual(row["phases"][0]["status"], "completed")

    def test_preserves_existing_phases(self) -> None:
        existing = [{"phase": "phase1", "status": "completed"}]
        row = migrate_to_v2({**V1_OPENCODE, "phases": existing})
        self.assertIs(row["phases"], existing)

    def test_idempotent(self) -> None:
        row = migrate_to_v2(dict(V1_OPENCODE))
        row2 = migrate_to_v2(row)
        self.assertIs(row, row2)  # returns same object

    def test_preserves_harness_specific_fields(self) -> None:
        row = migrate_to_v2(dict(V1_CLAUDE))
        self.assertIn("model_usage", row)
        self.assertIn("subagent_invocation_counts", row)

    def test_stale_harness_not_overwritten(self) -> None:
        row = migrate_to_v2({"status": "ok", "harness": "custom"})
        self.assertEqual(row["harness"], "custom")

    def test_backfills_phases_when_schema_already_v2(self) -> None:
        # Reproduces the gemma4 false-positive: claude_code_runner serializes
        # phase1-only completions with result_schema_version=2 but no phases[],
        # so the validator's missing_phases check trips on an otherwise-OK run.
        row = migrate_to_v2(
            {
                "result_schema_version": RESULT_SCHEMA_VERSION,
                "harness": "claude",
                "status": "completed",
                "elapsed_seconds": 1603.94,
                "file_count": 27,
            }
        )
        self.assertIn("phases", row)
        self.assertEqual(len(row["phases"]), 1)
        self.assertEqual(row["phases"][0]["phase"], "phase1")
        self.assertEqual(row["phases"][0]["status"], "completed")
        self.assertEqual(row["phases"][0]["elapsed_seconds"], 1603.94)
        self.assertEqual(row["phases"][0]["file_count"], 27)


if __name__ == "__main__":
    unittest.main()
