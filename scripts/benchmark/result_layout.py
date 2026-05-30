"""Single source of truth for benchmark output paths.

Run-scoped layout (preferred)::

    results/<run_id>/projects/<harness>-<slug>/...
    results/<run_id>/audit-reports/<auditor>/<target>/...
    results/<run_id>/meta-analysis.md

Legacy flat layout (no ``--run-id``)::

    results/<harness>-<slug>/...
    audit-reports/<auditor>/<target>/...

Harness-specific log file names (e.g. ``opencode-output.ndjson`` vs.
``stream.ndjson``) remain owned by the runner that writes them — those
are part of the Harness adapter's contract, not the layout.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

# Canonical harness identifiers (matches CONTEXT.md).
HARNESS_PREFIXES: tuple[str, ...] = ("opencode", "codex", "claude", "cursor")

# Agent harnesses compared in meta-analysis harness rankings (not cursor).
BENCHMARK_CONTEST_HARNESSES: frozenset[str] = frozenset(
    {"opencode", "codex", "claude"}
)
CURSOR_AGENT_PREFIX: str = "cursor"

RUN_ID_PATTERN = re.compile(r"^run_\d+$")


@dataclass(frozen=True)
class RunLayout:
    """Paths for one benchmark campaign under ``results/<run_id>/``."""

    run_id: str
    results_base: Path

    @property
    def run_root(self) -> Path:
        return self.results_base / self.run_id

    @property
    def projects_root(self) -> Path:
        return self.run_root / "projects"

    @property
    def audit_root(self) -> Path:
        return self.run_root / "audit-reports"

    @property
    def meta_analysis_md(self) -> Path:
        return self.run_root / "meta-analysis.md"

    @property
    def ollama_warmup_json(self) -> Path:
        return self.run_root / "ollama_warmup.json"

    @property
    def runtime_verification_summary_json(self) -> Path:
        return self.run_root / "runtime_verification_summary.json"


def validate_run_id(run_id: str) -> None:
    """Reject malformed run identifiers."""
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(
            f"run_id must match run_<digits> (e.g. run_02), got {run_id!r}"
        )


def resolve_run_layout(
    run_id: str,
    results_base: Path | None = None,
) -> RunLayout:
    """Build a :class:`RunLayout` for ``run_id`` under ``results_base``."""
    validate_run_id(run_id)
    base = results_base if results_base is not None else Path("results")
    return RunLayout(run_id=run_id, results_base=base)


def layout_from_repo(run_id: str, repo_root: Path) -> RunLayout:
    """Resolve ``run_id`` under ``<repo_root>/results``."""
    return resolve_run_layout(run_id, repo_root / "results")


def add_run_id_arg(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    help_suffix: str = "",
) -> None:
    """Register ``--run-id`` on a CLI parser."""
    suffix = f" {help_suffix}".rstrip()
    parser.add_argument(
        "--run-id",
        default=None,
        required=required,
        help=(
            "Run directory name under results/ (e.g. run_02). "
            "Resolves projects/, audit-reports/, and meta-analysis.md."
            + (f" {suffix}" if suffix else "")
        ),
    )


def discover_benchmark_target_dirs(projects_root: Path) -> list[Path]:
    """Return sorted target dirs that contain a ``project/`` child."""
    if not projects_root.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(projects_root.iterdir()):
        if entry.is_dir() and (entry / "project").is_dir():
            found.append(entry)
    return found


def discover_project_result_jsons(projects_root: Path) -> list[Path]:
    """Return sorted ``result.json`` paths under ``projects_root/*``."""
    if not projects_root.is_dir():
        return []
    return sorted(projects_root.glob("*/result.json"))


def target_dir(projects_root: Path, harness: str, slug: str) -> Path:
    """Directory holding one ``(harness, model)`` benchmark run."""
    return projects_root / f"{harness}-{slug}"


def target_project_workspace(projects_root: Path, harness: str, slug: str) -> Path:
    """The ``project/`` subdir — agent's working directory."""
    return target_dir(projects_root, harness, slug) / "project"


def target_result_json(projects_root: Path, harness: str, slug: str) -> Path:
    return target_dir(projects_root, harness, slug) / "result.json"


def target_prompt(projects_root: Path, harness: str, slug: str) -> Path:
    return target_dir(projects_root, harness, slug) / "prompt.txt"


def target_followup_prompt(projects_root: Path, harness: str, slug: str) -> Path:
    return target_dir(projects_root, harness, slug) / "followup-prompt.txt"


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
