"""Shared model slug identity helpers (audit/pricing-free)."""

from __future__ import annotations

_OLLAMA_COHORT_SUFFIXES = ("_claude", "_codex", "_opencode")


def cohort_slug(model_slug: str) -> str:
    """Return the shared model identity for contest-harness suffixed slugs."""
    for suffix in _OLLAMA_COHORT_SUFFIXES:
        if not model_slug.endswith(suffix):
            continue
        base = model_slug[: -len(suffix)]
        if suffix == "_opencode" and base.startswith(("claude_", "codex_")):
            return model_slug
        return base
    return model_slug
