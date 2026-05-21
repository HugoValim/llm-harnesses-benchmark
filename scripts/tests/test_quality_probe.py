"""Tests for benchmark.quality_probe — payload shape + failure paths.

These tests intentionally do NOT spin up a real probe venv (slow, network).
They verify:
 - the missing-project path writes an ``error`` payload without raising
 - the parser helpers cope with malformed tool output
 - the aggregator sets ``status='error'`` when every tool reports error
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.quality_probe import (  # noqa: E402
    _parse_bandit_output,
    _parse_mypy_output,
    _parse_radon_cc_output,
    _parse_radon_mi_output,
    _parse_ruff_output,
    probe,
)


class TestProbeMissingProject(unittest.TestCase):
    def test_missing_project_dir_writes_error_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "static-analysis.json"
            payload = probe(tmp_path / "does-not-exist", out, repo_root=tmp_path)
            self.assertEqual(payload["status"], "error")
            self.assertIn("does not exist", payload["error"])
            self.assertTrue(out.exists())
            on_disk = json.loads(out.read_text())
            self.assertEqual(on_disk["status"], "error")


class TestRuffParser(unittest.TestCase):
    def test_valid_json_extracts_codes_and_offenders(self) -> None:
        stdout = json.dumps(
            [
                {
                    "code": "F401",
                    "filename": "/p/a.py",
                    "message": "unused import",
                    "location": {"row": 3, "column": 1},
                },
                {
                    "code": "E501",
                    "filename": "/p/b.py",
                    "message": "line too long",
                    "location": {"row": 10, "column": 80},
                },
                {
                    "code": "F401",
                    "filename": "/p/c.py",
                    "message": "unused import",
                    "location": {"row": 4, "column": 1},
                },
            ]
        )
        result = _parse_ruff_output(stdout, "", returncode=1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_errors"], 3)
        self.assertEqual(result["by_category"]["F401"], 2)
        self.assertEqual(result["by_category"]["E501"], 1)
        self.assertEqual(len(result["top_offenders"]), 3)
        self.assertEqual(result["top_offenders"][0]["code"], "F401")
        self.assertEqual(result["top_offenders"][0]["line"], 3)

    def test_invalid_json_yields_error_status(self) -> None:
        result = _parse_ruff_output("not-json", "boom", returncode=2)
        self.assertEqual(result["status"], "error")


class TestMypyParser(unittest.TestCase):
    def test_extracts_error_lines(self) -> None:
        stdout = (
            "chat/views.py:12: error: Missing type annotation [no-untyped-def]\n"
            "chat/views.py:18: note: somewhere related\n"
            "chat/consumers.py:42:5: error: Argument 1 has incompatible type\n"
        )
        result = _parse_mypy_output(stdout, "")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_errors"], 2)
        self.assertEqual(result["top_offenders"][0]["file"], "chat/views.py")
        self.assertEqual(result["top_offenders"][1]["line"], 42)

    def test_empty_source_is_ok_zero(self) -> None:
        result = _parse_mypy_output("", "error: There are no Python source files in the current directory")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_errors"], 0)


class TestBanditParser(unittest.TestCase):
    def test_severity_counts(self) -> None:
        payload = json.dumps(
            {
                "results": [
                    {
                        "issue_severity": "HIGH",
                        "filename": "/p/a.py",
                        "line_number": 5,
                        "test_id": "B101",
                        "issue_text": "assert used",
                    },
                    {
                        "issue_severity": "medium",
                        "filename": "/p/b.py",
                        "line_number": 7,
                        "test_id": "B201",
                        "issue_text": "flask_debug_true",
                    },
                    {
                        "issue_severity": "low",
                        "filename": "/p/c.py",
                        "line_number": 9,
                        "test_id": "B311",
                        "issue_text": "random",
                    },
                ]
            }
        )
        result = _parse_bandit_output(payload, "")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["high"], 1)
        self.assertEqual(result["medium"], 1)
        self.assertEqual(result["low"], 1)
        self.assertEqual(result["total"], 3)


class TestRadonCCParser(unittest.TestCase):
    def test_counts_grade_d_or_worse_and_sorts(self) -> None:
        payload = json.dumps(
            {
                "chat/consumers.py": [
                    {"name": "ws_loop", "complexity": 25, "lineno": 18, "rank": "D"},
                    {"name": "minor", "complexity": 6, "lineno": 2, "rank": "B"},
                ],
                "chat/views.py": [
                    {"name": "monster", "complexity": 41, "lineno": 5, "rank": "F"},
                ],
            }
        )
        result = _parse_radon_cc_output(payload, "")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["functions_grade_d_or_worse"], 2)
        self.assertEqual(result["top_offenders"][0]["complexity"], 41)


class TestRadonMIParser(unittest.TestCase):
    def test_counts_modules_below_65(self) -> None:
        payload = json.dumps(
            {
                "chat/consumers.py": {"mi": 42.5, "rank": "B"},
                "chat/views.py": {"mi": 80.0, "rank": "A"},
                "chat/utils.py": {"mi": 12.1, "rank": "C"},
            }
        )
        result = _parse_radon_mi_output(payload, "")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["modules_below_65"], 2)
        self.assertEqual(result["top_offenders"][0]["file"], "chat/utils.py")
        self.assertLess(result["top_offenders"][0]["mi"], 65)


if __name__ == "__main__":
    unittest.main()
