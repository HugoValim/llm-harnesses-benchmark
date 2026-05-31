"""Build-run parity helpers: cold followup, prompt wrapping, result metadata."""

from __future__ import annotations

from benchmark.util import build_project_context_text

FOLLOWUP_CONTINUITY_COLD = "cold"
FRESH_SESSION_FALLBACK = (
    "\n\nIf this is running in a fresh session rather than a continued one, first inspect the existing project "
    "in the current working directory, understand the current implementation state, and then perform the same "
    "runtime validation work before making any additional fixes."
)


def build_followup_prompt(followup: str, *, continuity: str = FOLLOWUP_CONTINUITY_COLD) -> str:
    """Return followup prompt with continuity policy applied."""
    if continuity == FOLLOWUP_CONTINUITY_COLD:
        return followup + FRESH_SESSION_FALLBACK
    raise ValueError(
        f"unsupported followup continuity {continuity!r}; only {FOLLOWUP_CONTINUITY_COLD!r} is supported"
    )


def wrap_primary_prompt(prompt: str, *, include_agent_rules: bool = True) -> str:
    """Prepend canonical project context so all harnesses receive agent rules."""
    context_block = build_project_context_text(include_agent_rules=include_agent_rules)
    return f"{context_block.rstrip()}\n\n---\n\n{prompt.lstrip()}"


def build_parity_metadata(
    *,
    continuity: str,
    primary_prompt_wrapped: bool,
    runtime_isolation: dict[str, str],
) -> dict[str, object]:
    """Shape build_parity fields recorded in result.json."""
    return {
        "followup_continuity": continuity,
        "primary_prompt_wrapped": primary_prompt_wrapped,
        "runtime_isolation": runtime_isolation,
    }
