"""Benchmark replicate dispatch helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

from benchmark.config import _resolve_model_num_runs
from benchmark.result_layout import format_replicate_dir, replicate_result_dir
from benchmark.result_layout import target_dir as layout_target_dir
from benchmark.util import print_line


def model_num_runs(model: dict[str, Any]) -> int:
    """Return configured replicate count for ``model``."""
    return _resolve_model_num_runs(model)


def resolve_result_dir(
    *,
    results_dir: Path,
    harness: str,
    slug: str,
    replicate_index: int | None = None,
    explicit_result_dir: Path | None = None,
) -> Path:
    """Resolve the on-disk result directory for one benchmark attempt."""
    if explicit_result_dir is not None:
        return explicit_result_dir.resolve()
    if replicate_index is None:
        return layout_target_dir(results_dir, harness, slug).resolve()
    return replicate_result_dir(
        results_dir, harness, slug, replicate_index
    ).resolve()


def attach_replicate_fields(
    payload: dict[str, Any],
    *,
    replicate_index: int,
    num_runs: int,
) -> dict[str, Any]:
    """Add replicate metadata to a benchmark ``result.json`` payload."""
    payload["replicate_index"] = replicate_index
    payload["replicate_id"] = format_replicate_dir(replicate_index)
    payload["num_runs"] = num_runs
    return payload


def expand_replicate_first(
    items: list[T],
    *,
    num_runs: Callable[[T], int],
) -> list[tuple[T, int, int]]:
    """Expand items into replicate-first order: all run_01, then run_02, etc.

    Example:
        ``expand_replicate_first([a, b], num_runs=model_num_runs)`` with
        ``a.num_runs=2`` and ``b.num_runs=1`` returns ``[(a,1,2), (b,1,1), (a,2,2)]``.
    """
    if not items:
        return []
    max_runs = max(num_runs(item) for item in items)
    expanded: list[tuple[T, int, int]] = []
    for replicate_index in range(1, max_runs + 1):
        for item in items:
            item_runs = num_runs(item)
            if replicate_index <= item_runs:
                expanded.append((item, replicate_index, item_runs))
    return expanded


def replicate_log_suffix(replicate_index: int, num_runs: int) -> str:
    """Human-readable replicate suffix for progress logs."""
    if num_runs <= 1:
        return ""
    return f" {format_replicate_dir(replicate_index)}/{num_runs}"


def run_replicate_attempts(
    model: dict[str, Any],
    run_once: Callable[[int, int], dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Run ``run_once(replicate_index, num_runs)`` sequentially for each replicate."""
    num_runs = model_num_runs(model)
    last_payload: dict[str, Any] | None = None
    for replicate_index in range(1, num_runs + 1):
        suffix = replicate_log_suffix(replicate_index, num_runs)
        if suffix:
            print_line(
                f"[{model.get('slug', '<unknown>')}] starting replicate"
                f"{suffix}"
            )
        last_payload = run_once(replicate_index, num_runs)
    return last_payload
