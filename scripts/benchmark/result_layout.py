"""Single source of truth for benchmark output paths.

Every caller that needs to know where ``results/<harness>-<slug>/...`` or
``audit-reports/<auditor>/<target>/...`` lives reaches into this module
instead of concatenating strings. Renaming or restructuring the layout
becomes one edit here, not a sweep across runners, reports, and audit
pipelines.

Harness-specific log file names (e.g. ``opencode-output.ndjson`` vs.
``stream.ndjson``) remain owned by the runner that writes them — those
are part of the Harness adapter's contract, not the layout.
"""

from __future__ import annotations

from pathlib import Path

# Canonical harness identifiers (matches CONTEXT.md).
HARNESS_PREFIXES: tuple[str, ...] = ("opencode", "codex", "claude", "cursor")

# Agent harnesses compared in meta-analysis harness rankings (not cursor).
BENCHMARK_CONTEST_HARNESSES: frozenset[str] = frozenset(
    {"opencode", "codex", "claude"}
)
CURSOR_AGENT_PREFIX: str = "cursor"


def target_dir(results_root: Path, harness: str, slug: str) -> Path:
    """Directory holding one ``(harness, model)`` benchmark run."""
    return results_root / f"{harness}-{slug}"


def target_project_workspace(results_root: Path, harness: str, slug: str) -> Path:
    """The ``project/`` subdir — agent's working directory."""
    return target_dir(results_root, harness, slug) / "project"


def target_result_json(results_root: Path, harness: str, slug: str) -> Path:
    return target_dir(results_root, harness, slug) / "result.json"


def target_prompt(results_root: Path, harness: str, slug: str) -> Path:
    return target_dir(results_root, harness, slug) / "prompt.txt"


def target_followup_prompt(results_root: Path, harness: str, slug: str) -> Path:
    return target_dir(results_root, harness, slug) / "followup-prompt.txt"


def audit_target_dir(audit_root: Path, auditor_slug: str, target_slug: str) -> Path:
    """Directory holding one auditor's report against one target."""
    return audit_root / auditor_slug / target_slug


def audit_report_md(audit_root: Path, auditor_slug: str, target_slug: str) -> Path:
    return audit_target_dir(audit_root, auditor_slug, target_slug) / "report.md"


def audit_result_json(audit_root: Path, auditor_slug: str, target_slug: str) -> Path:
    return audit_target_dir(audit_root, auditor_slug, target_slug) / "result.json"


def audit_stream_ndjson(audit_root: Path, auditor_slug: str, target_slug: str) -> Path:
    return audit_target_dir(audit_root, auditor_slug, target_slug) / "stream.ndjson"


def audit_stderr_log(audit_root: Path, auditor_slug: str, target_slug: str) -> Path:
    return audit_target_dir(audit_root, auditor_slug, target_slug) / "stderr.log"


def audit_generation_metrics_json(
    audit_root: Path, auditor_slug: str, target_slug: str
) -> Path:
    """Precomputed generation cost/tokens from the benchmark ``result.json``.

    Written by :func:`run_audit` before LLM auditor dispatch; section H of
    ``report.md`` must copy values from this file verbatim.
    """
    return audit_target_dir(audit_root, auditor_slug, target_slug) / "generation-metrics.json"


def split_target_slug(name: str) -> tuple[str | None, str]:
    """Split a target directory name into ``(harness, model_slug)``.

    >>> split_target_slug("claude-claude_sonnet_4_6")
    ('claude', 'claude_sonnet_4_6')
    >>> split_target_slug("plain_name")
    (None, 'plain_name')
    """
    for prefix in HARNESS_PREFIXES:
        head = f"{prefix}-"
        if name.startswith(head):
            return prefix, name[len(head):]
    return None, name
