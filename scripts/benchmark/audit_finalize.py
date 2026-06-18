"""Finalize audit runs: stream fallback extraction and report completeness."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.audit_report import audit_report_is_complete

INCOMPLETE_REPORT_STATUS = "incomplete_report"

_ASSISTANT_TEXT_TYPES = ("text", "thinking")


def extract_final_report_from_stream(stream_path: Path, report_path: Path) -> bool:
    """Best-effort: write assistant content from NDJSON to ``report_path``.

    Supports Claude Code ``type == "assistant"`` events (``text`` and ``thinking``
    parts; ``text`` preferred) and Codex ``item.completed`` agent messages.
    Returns True when any content was written.
    """
    text_chunks: list[str] = []
    thinking_chunks: list[str] = []
    try:
        with stream_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "assistant":
                    msg = event.get("message", {})
                    for part in msg.get("content", []):
                        part_type = part.get("type")
                        if part_type not in _ASSISTANT_TEXT_TYPES:
                            continue
                        raw = part.get("text") or part.get("thinking") or ""
                        if not isinstance(raw, str) or not raw.strip():
                            continue
                        if part_type == "text":
                            text_chunks.append(raw)
                        else:
                            thinking_chunks.append(raw)
                elif event.get("type") == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        raw = item.get("text", "")
                        if isinstance(raw, str) and raw.strip():
                            text_chunks.append(raw)
        chunks = text_chunks if text_chunks else thinking_chunks
        if not chunks:
            return False
        report_path.write_text("\n\n".join(chunks), encoding="utf-8")
        return True
    except OSError:
        return False


def ensure_audit_report(
    *,
    report_path: Path,
    stream_path: Path | None,
) -> tuple[bool, str]:
    """Ensure ``report_path`` exists with a parseable rubric total.

    When missing, tries stream extraction. Returns ``(True, "")`` on success or
    ``(False, reason)`` when the report is still incomplete.
    """
    if not report_path.is_file():
        if stream_path is not None and stream_path.is_file():
            extract_final_report_from_stream(stream_path, report_path)
    if audit_report_is_complete(report_path):
        return True, ""
    if report_path.is_file():
        return False, "report.md missing parseable total score"
    if stream_path is not None and stream_path.is_file():
        return False, "no report.md (stream had no rubric output to recover)"
    return False, "no report.md"


def mark_audit_result_incomplete(result_path: Path) -> None:
    """Record that the harness finished without a complete rubric report."""
    if not result_path.is_file():
        return
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    harness_status = payload.get("status")
    if harness_status and harness_status != INCOMPLETE_REPORT_STATUS:
        payload["harness_status"] = harness_status
    payload["status"] = INCOMPLETE_REPORT_STATUS
    result_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
