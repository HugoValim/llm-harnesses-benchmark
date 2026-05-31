"""Single source of truth for benchmark output paths.

Run-scoped layout (preferred)::

    results/<run_id>/projects/<harness>-<slug>/run_XX/project/...
    results/<run_id>/audit-reports/<auditor>/<harness>-<slug>/run_XX/...
    results/<run_id>/meta-analysis.md

Legacy flat layout (no ``--run-id`` or pre-replicate campaigns)::

    results/<harness>-<slug>/project/...
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
REPLICATE_DIR_PATTERN = re.compile(r"^run_\d{2}$")


@dataclass(frozen=True)
class ParsedBenchmarkTarget:
    """One audited benchmark leaf under ``projects/``."""

    target_group: str
    replicate_id: str | None
    harness: str | None
    model_slug: str

    @property
    def slug(self) -> str:
        """Relative path from ``projects/`` used as audit target key."""
        if self.replicate_id is None:
            return self.target_group
        return f"{self.target_group}/{self.replicate_id}"


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


def resolve_default_run_id(results_base: Path) -> str | None:
    """Return the highest ``run_XX`` directory name under ``results_base``, or None."""
    if not results_base.is_dir():
        return None
    candidates: list[tuple[int, str]] = []
    for entry in results_base.iterdir():
        if not entry.is_dir():
            continue
        if not RUN_ID_PATTERN.match(entry.name):
            continue
        candidates.append((int(entry.name.split("_", 1)[1]), entry.name))
    if not candidates:
        return None
    return max(candidates)[1]


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


def format_replicate_dir(replicate_index: int) -> str:
    """Return replicate folder name for ``replicate_index`` (1-based)."""
    if replicate_index < 1:
        raise ValueError(
            f"replicate_index must be >= 1, got {replicate_index!r}"
        )
    return f"run_{replicate_index:02d}"


def target_dir(projects_root: Path, harness: str, slug: str) -> Path:
    """Directory holding one ``(harness, model)`` target group."""
    return projects_root / f"{harness}-{slug}"


def target_group_dir(projects_root: Path, harness: str, slug: str) -> Path:
    """Alias for :func:`target_dir` — parent of replicate leaf dirs."""
    return target_dir(projects_root, harness, slug)


def replicate_result_dir(
    projects_root: Path,
    harness: str,
    slug: str,
    replicate_index: int,
) -> Path:
    """Directory for one replicate attempt under a target group."""
    return target_group_dir(projects_root, harness, slug) / format_replicate_dir(
        replicate_index
    )


def target_project_workspace(
    projects_root: Path,
    harness: str,
    slug: str,
    *,
    replicate_index: int | None = None,
) -> Path:
    """The ``project/`` subdir — agent's working directory."""
    if replicate_index is None:
        return target_dir(projects_root, harness, slug) / "project"
    return replicate_result_dir(
        projects_root, harness, slug, replicate_index
    ) / "project"


def target_result_json(
    projects_root: Path,
    harness: str,
    slug: str,
    *,
    replicate_index: int | None = None,
) -> Path:
    if replicate_index is None:
        return target_dir(projects_root, harness, slug) / "result.json"
    return replicate_result_dir(
        projects_root, harness, slug, replicate_index
    ) / "result.json"


def target_prompt(
    projects_root: Path,
    harness: str,
    slug: str,
    *,
    replicate_index: int | None = None,
) -> Path:
    if replicate_index is None:
        return target_dir(projects_root, harness, slug) / "prompt.txt"
    return replicate_result_dir(
        projects_root, harness, slug, replicate_index
    ) / "prompt.txt"


def target_followup_prompt(
    projects_root: Path,
    harness: str,
    slug: str,
    *,
    replicate_index: int | None = None,
) -> Path:
    if replicate_index is None:
        return target_dir(projects_root, harness, slug) / "followup-prompt.txt"
    return replicate_result_dir(
        projects_root, harness, slug, replicate_index
    ) / "followup-prompt.txt"


def _is_target_group_dir(entry: Path) -> bool:
    if not entry.is_dir():
        return False
    if (entry / "project").is_dir():
        return True
    return any(
        child.is_dir()
        and REPLICATE_DIR_PATTERN.match(child.name)
        and (child / "project").is_dir()
        for child in entry.iterdir()
    )


def _iter_benchmark_target_leaves(group_dir: Path) -> list[Path]:
    """Return sorted replicate leaf dirs under one target group."""
    if (group_dir / "project").is_dir():
        return [group_dir]
    leaves: list[Path] = []
    for child in sorted(group_dir.iterdir()):
        if not child.is_dir():
            continue
        if REPLICATE_DIR_PATTERN.match(child.name) and (child / "project").is_dir():
            leaves.append(child)
    return leaves


def discover_benchmark_target_dirs(projects_root: Path) -> list[Path]:
    """Return sorted leaf dirs that contain a ``project/`` child.

    Supports nested ``<target-group>/run_XX/project`` and legacy flat
    ``<target-group>/project``.
    """
    if not projects_root.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(projects_root.iterdir()):
        if not _is_target_group_dir(entry):
            continue
        found.extend(_iter_benchmark_target_leaves(entry))
    return found


def discover_project_result_jsons(projects_root: Path) -> list[Path]:
    """Return sorted ``result.json`` paths for every benchmark leaf."""
    return sorted(
        leaf / "result.json"
        for leaf in discover_benchmark_target_dirs(projects_root)
        if (leaf / "result.json").is_file()
    )


def parse_benchmark_target_path(rel_path: str) -> ParsedBenchmarkTarget:
    """Parse a projects-relative target slug into group + replicate parts."""
    parts = rel_path.split("/")
    if len(parts) == 1:
        harness, model_slug = split_target_slug(parts[0])
        return ParsedBenchmarkTarget(
            target_group=parts[0],
            replicate_id=None,
            harness=harness,
            model_slug=model_slug,
        )
    if len(parts) == 2:
        target_group, replicate_id = parts
        if not REPLICATE_DIR_PATTERN.match(replicate_id):
            raise ValueError(
                f"expected replicate dir run_XX in target path, got {rel_path!r}"
            )
        harness, model_slug = split_target_slug(target_group)
        return ParsedBenchmarkTarget(
            target_group=target_group,
            replicate_id=replicate_id,
            harness=harness,
            model_slug=model_slug,
        )
    raise ValueError(
        f"benchmark target path must be <group> or <group>/run_XX, got {rel_path!r}"
    )


def benchmark_target_slug_from_leaf(leaf_dir: Path, projects_root: Path) -> str:
    """Return projects-relative slug for a discovered leaf directory."""
    rel = leaf_dir.resolve().relative_to(projects_root.resolve())
    return rel.as_posix()


def matches_benchmark_only_filter(
    result_path: Path, only: set[str], projects_root: Path
) -> bool:
    """Return True when ``result_path`` matches ``--only`` filter tokens."""
    result_dir = result_path.parent
    if REPLICATE_DIR_PATTERN.match(result_dir.name):
        target_group = result_dir.parent.name
        full_slug = f"{target_group}/{result_dir.name}"
        return (
            result_dir.name in only
            or target_group in only
            or full_slug in only
        )
    slug = benchmark_target_slug_from_leaf(result_dir, projects_root)
    return result_dir.name in only or slug in only


def audit_replicate_dir(
    audit_root: Path,
    auditor_slug: str,
    target_group: str,
    replicate_id: str | None = None,
) -> Path:
    """Directory holding one auditor report for a target group replicate."""
    base = audit_root / auditor_slug / target_group
    if replicate_id is None:
        return base
    return base / replicate_id


def audit_target_dir(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    """Directory holding one auditor's report against one target.

    When ``target_slug`` contains ``/`` it is treated as ``group/run_XX``.
    Otherwise ``replicate_id`` selects a nested replicate dir under
    ``target_slug``.
    """
    if "/" in target_slug:
        parsed = parse_benchmark_target_path(target_slug)
        return audit_replicate_dir(
            audit_root,
            auditor_slug,
            parsed.target_group,
            parsed.replicate_id,
        )
    return audit_replicate_dir(
        audit_root, auditor_slug, target_slug, replicate_id
    )


def audit_report_md(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    return audit_target_dir(
        audit_root, auditor_slug, target_slug, replicate_id=replicate_id
    ) / "report.md"


def audit_result_json(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    return audit_target_dir(
        audit_root, auditor_slug, target_slug, replicate_id=replicate_id
    ) / "result.json"


def audit_stream_ndjson(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    return audit_target_dir(
        audit_root, auditor_slug, target_slug, replicate_id=replicate_id
    ) / "stream.ndjson"


def audit_stderr_log(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    return audit_target_dir(
        audit_root, auditor_slug, target_slug, replicate_id=replicate_id
    ) / "stderr.log"


def audit_generation_metrics_json(
    audit_root: Path,
    auditor_slug: str,
    target_slug: str,
    *,
    replicate_id: str | None = None,
) -> Path:
    """Precomputed generation cost/tokens from the benchmark ``result.json``.

    Written by :func:`run_audit` before LLM auditor dispatch; section H of
    ``report.md`` must copy values from this file verbatim.
    """
    return audit_target_dir(
        audit_root, auditor_slug, target_slug, replicate_id=replicate_id
    ) / "generation-metrics.json"


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
