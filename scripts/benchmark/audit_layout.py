"""Audit report directory layout discovery (flat and replicate paths)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from benchmark.result_layout import REPLICATE_DIR_PATTERN


def iter_target_group_report_paths(target_dir: Path) -> Iterable[Path]:
    """Yield ``report.md`` paths for one audited target group.

    Supports flat ``<target>/report.md`` and replicate
    ``<target>/run_XX/report.md`` layouts (flat wins when both exist).
    """
    if not target_dir.is_dir():
        return
    direct_report = target_dir / "report.md"
    if direct_report.is_file():
        yield direct_report
        return
    for replicate_dir in sorted(target_dir.iterdir()):
        if not replicate_dir.is_dir():
            continue
        if not REPLICATE_DIR_PATTERN.match(replicate_dir.name):
            continue
        report_path = replicate_dir / "report.md"
        if report_path.is_file():
            yield report_path


def target_group_has_reports(target_dir: Path) -> bool:
    """True when one target group contains at least one ``report.md``."""
    return any(iter_target_group_report_paths(target_dir))


def iter_target_group_report_entries(target_dir: Path) -> Iterable[tuple[Path, str]]:
    """Yield ``(report_path, target_label)`` for one audited target group."""
    if not target_dir.is_dir():
        return
    direct_report = target_dir / "report.md"
    if direct_report.is_file():
        yield direct_report, target_dir.name
        return
    for replicate_dir in sorted(target_dir.iterdir()):
        if not replicate_dir.is_dir():
            continue
        if not REPLICATE_DIR_PATTERN.match(replicate_dir.name):
            continue
        report_path = replicate_dir / "report.md"
        if report_path.is_file():
            yield report_path, f"{target_dir.name}/{replicate_dir.name}"


def auditor_dir_has_reports(auditor_dir: Path) -> bool:
    """True when ``auditor_dir`` contains at least one audit ``report.md``."""
    if not auditor_dir.is_dir():
        return False
    return any(
        target_group_has_reports(child)
        for child in auditor_dir.iterdir()
        if child.is_dir()
    )


def iter_auditor_report_paths(auditor_dir: Path) -> Iterable[Path]:
    """Yield every ``report.md`` under one auditor tree."""
    if not auditor_dir.is_dir():
        return
    for target_dir in sorted(auditor_dir.iterdir()):
        if not target_dir.is_dir():
            continue
        yield from iter_target_group_report_paths(target_dir)
