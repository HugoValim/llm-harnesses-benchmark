"""Shared defaults for audit and meta-analysis dispatch."""

from __future__ import annotations

# GPT-5.5 xhigh via Codex CLI (config/models.json: codex_reasoning_effort=xhigh).
DEFAULT_AUDITOR_SLUG = "codex_gpt_5_5"

# Harness for DEFAULT_AUDITOR_SLUG (openai provider -> codex).
DEFAULT_AUDIT_HARNESS = "codex"
