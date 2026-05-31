"""Tests for agent coding rules injection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import (  # noqa: E402
    agent_coding_rules_sha256,
    build_project_context_text,
    load_agent_coding_rules,
    prompt_sha256,
)


class TestAgentCodingRules(unittest.TestCase):
    def test_load_agent_coding_rules_has_version_header(self) -> None:
        rules = load_agent_coding_rules()
        self.assertTrue(rules.startswith("Prompt-Version: agent-coding-rules-v1.0"))
        self.assertIn("Operating mode", rules)
        self.assertNotIn("caveman mode", rules.lower())

    def test_build_project_context_includes_rules_by_default(self) -> None:
        text = build_project_context_text(include_agent_rules=True)
        self.assertIn("Hard constraints", text)
        self.assertIn("Never hardcode secrets", text)
        self.assertIn("---", text)

    def test_build_project_context_opt_out_is_workspace_only(self) -> None:
        text = build_project_context_text(include_agent_rules=False)
        self.assertIn("Hard constraints", text)
        self.assertNotIn("Operating mode", text)
        self.assertNotIn("Never hardcode secrets", text)

    def test_agent_coding_rules_sha256_matches_prompt_sha256(self) -> None:
        rules = load_agent_coding_rules()
        expected = prompt_sha256(rules)
        self.assertEqual(
            agent_coding_rules_sha256(include_agent_rules=True),
            expected,
        )
        self.assertIsNone(agent_coding_rules_sha256(include_agent_rules=False))

    def test_load_agent_coding_rules_missing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.md"
            with self.assertRaisesRegex(FileNotFoundError, "Agent coding rules file missing"):
                load_agent_coding_rules(missing)


if __name__ == "__main__":
    unittest.main()
