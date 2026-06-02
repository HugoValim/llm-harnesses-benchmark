"""Expected benchmark replicate leaves from config/models.json num_runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchmark.config import _resolve_model_num_runs, registry_by_slug
from benchmark.full_pipeline import build_matrix
from benchmark.result_layout import (
    REPLICATE_DIR_PATTERN,
    format_replicate_dir,
    target_group_dir,
)
from benchmark.util import load_json


@dataclass(frozen=True)
class ExpectedBenchmarkLeaf:
    """One configured replicate attempt under ``projects/``."""

    harness: str
    model_slug: str
    target_group: str
    replicate_id: str
    num_runs: int

    @property
    def slug(self) -> str:
        """Projects-relative path: ``<harness>-<slug>/run_XX``."""
        return f"{self.target_group}/{self.replicate_id}"


@dataclass(frozen=True)
class ReplicateCoverageGap:
    """One mismatch between configured and on-disk replicate layout."""

    slug: str
    reason: str


def expected_benchmark_leaves(
    models_config_path: Path,
    *,
    harness: str | None = None,
) -> list[ExpectedBenchmarkLeaf]:
    """Return every replicate leaf implied by the build matrix and ``num_runs``."""
    config = load_json(models_config_path)
    registry = registry_by_slug(
        config.get("models", []) if isinstance(config.get("models"), list) else []
    )
    leaves: list[ExpectedBenchmarkLeaf] = []
    for step in build_matrix(models_config_path):
        if harness is not None and step.harness != harness:
            continue
        model_row = registry.get(step.model_slug, {})
        num_runs = _resolve_model_num_runs(model_row) if model_row else 1
        target_group = f"{step.harness}-{step.model_slug}"
        for replicate_index in range(1, num_runs + 1):
            leaves.append(
                ExpectedBenchmarkLeaf(
                    harness=step.harness,
                    model_slug=step.model_slug,
                    target_group=target_group,
                    replicate_id=format_replicate_dir(replicate_index),
                    num_runs=num_runs,
                )
            )
    return leaves


def filter_expected_leaves(
    leaves: list[ExpectedBenchmarkLeaf],
    only: set[str] | None,
) -> list[ExpectedBenchmarkLeaf]:
    """Keep leaves matching ``--only`` tokens (group, replicate, or full slug)."""
    if not only:
        return list(leaves)
    out: list[ExpectedBenchmarkLeaf] = []
    for leaf in leaves:
        if (
            leaf.target_group in only
            or leaf.replicate_id in only
            or leaf.slug in only
            or leaf.model_slug in only
        ):
            out.append(leaf)
    return out


def find_replicate_coverage_gaps(
    projects_root: Path,
    expected_leaves: list[ExpectedBenchmarkLeaf],
) -> list[ReplicateCoverageGap]:
    """Compare configured replicate leaves to on-disk benchmark output."""
    gaps: list[ReplicateCoverageGap] = []
    expected_by_group: dict[str, list[ExpectedBenchmarkLeaf]] = {}
    for leaf in expected_leaves:
        expected_by_group.setdefault(leaf.target_group, []).append(leaf)

    legacy_flat_groups: set[str] = set()
    for target_group, group_leaves in expected_by_group.items():
        group_dir = target_group_dir(
            projects_root,
            group_leaves[0].harness,
            group_leaves[0].model_slug,
        )
        if not group_dir.is_dir():
            continue
        expected_replicate_ids = {leaf.replicate_id for leaf in group_leaves}
        if (group_dir / "project").is_dir():
            legacy_flat_groups.add(target_group)
            gaps.append(
                ReplicateCoverageGap(
                    slug=target_group,
                    reason=(
                        "legacy flat project/ layout; expected nested "
                        f"{', '.join(sorted(expected_replicate_ids))}/"
                    ),
                )
            )
            continue
        for child in sorted(group_dir.iterdir()):
            if not child.is_dir():
                continue
            if not REPLICATE_DIR_PATTERN.match(child.name):
                continue
            if child.name not in expected_replicate_ids:
                gaps.append(
                    ReplicateCoverageGap(
                        slug=f"{target_group}/{child.name}",
                        reason="unexpected replicate directory (not in config num_runs)",
                    )
                )

    for leaf in expected_leaves:
        if leaf.target_group in legacy_flat_groups:
            continue
        leaf_dir = projects_root / leaf.slug
        result_path = leaf_dir / "result.json"
        project_dir = leaf_dir / "project"
        if result_path.is_file() or project_dir.is_dir():
            continue
        gaps.append(
            ReplicateCoverageGap(
                slug=leaf.slug,
                reason="missing replicate directory (no result.json or project/)",
            )
        )

    return gaps


def format_replicate_gaps(gaps: list[ReplicateCoverageGap]) -> str:
    """Return a human-readable gap report, or an empty string when complete."""
    if not gaps:
        return ""
    lines = [
        "Replicate coverage incomplete — every configured harness-model "
        "replicate needs a result directory:",
    ]
    for gap in gaps:
        lines.append(f"  - {gap.slug}: {gap.reason}")
    lines.append(
        "Re-run: python scripts/run_benchmark.py --run-id <run_id> "
        "--harness <harness> [--model <slug>]"
    )
    return "\n".join(lines)


def assert_replicate_coverage(
    *,
    projects_root: Path,
    models_config_path: Path,
    only: set[str] | None = None,
) -> None:
    """Exit non-zero when configured replicate leaves are missing on disk."""
    leaves = filter_expected_leaves(
        expected_benchmark_leaves(models_config_path),
        only,
    )
    message = format_replicate_gaps(
        find_replicate_coverage_gaps(projects_root, leaves)
    )
    if message:
        raise SystemExit(f"ERROR: {message}")
