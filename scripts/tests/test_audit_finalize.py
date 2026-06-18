"""Tests for audit report finalization and stream extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_coverage import audit_dispatch_needed  # noqa: E402
from benchmark.audit_finalize import (  # noqa: E402
    INCOMPLETE_REPORT_STATUS,
    ensure_audit_report,
    extract_final_report_from_stream,
    mark_audit_result_incomplete,
)


def test_extract_final_report_prefers_text_over_thinking(tmp_path: Path) -> None:
    stream = tmp_path / "stream.ndjson"
    report = tmp_path / "report.md"
    stream.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "thinking", "thinking": "internal"},
                                {
                                    "type": "text",
                                    "text": "C. **Total score / 100**\n\n**42 / 100**",
                                },
                            ]
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    assert extract_final_report_from_stream(stream, report)
    assert "42 / 100" in report.read_text()


def test_extract_final_report_falls_back_to_thinking(tmp_path: Path) -> None:
    stream = tmp_path / "stream.ndjson"
    report = tmp_path / "report.md"
    stream.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "Only thinking output."},
                    ]
                },
            }
        )
        + "\n"
    )
    assert extract_final_report_from_stream(stream, report)
    assert "Only thinking output." in report.read_text()


def test_ensure_audit_report_does_not_clobber_existing_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    original = "C. **Total score / 100**: 80 / 100\n"
    report.write_text(original)
    stream = tmp_path / "stream.ndjson"
    stream.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "Only thinking output."},
                    ]
                },
            }
        )
        + "\n"
    )
    ok, reason = ensure_audit_report(report_path=report, stream_path=stream)
    assert report.read_text() == original
    assert ok
    assert reason == ""


def test_ensure_audit_report_requires_parseable_total(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("no score here\n")
    ok, reason = ensure_audit_report(report_path=report, stream_path=None)
    assert not ok
    assert "parseable" in reason


def test_mark_audit_result_incomplete_preserves_harness_status(
    tmp_path: Path,
) -> None:
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"status": "completed", "exit_code": 0}))
    mark_audit_result_incomplete(result)
    payload = json.loads(result.read_text())
    assert payload["status"] == INCOMPLETE_REPORT_STATUS
    assert payload["harness_status"] == "completed"


def test_audit_dispatch_needed_retries_incomplete_report_status(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"status": INCOMPLETE_REPORT_STATUS}))
    assert audit_dispatch_needed(
        report_path=report, audit_result_path=result, force=False
    )
