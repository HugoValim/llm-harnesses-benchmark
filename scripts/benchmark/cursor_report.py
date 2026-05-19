"""Markdown report for Cursor CLI benchmark variants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_variant_results(
    config: dict[str, Any],
    results_dir: Path,
    *,
    harness: str = "cursor",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for v in config.get("variants", []):
        slug = v["slug"]
        rp = results_dir / f"{harness}-{slug}" / "result.json"
        if rp.exists():
            try:
                rows.append(json.loads(rp.read_text()))
            except json.JSONDecodeError:
                rows.append({"slug": slug, "status": "not_run"})
        else:
            rows.append({"slug": slug, "status": "not_run"})
    return rows


def build_variant_report(config: dict[str, Any], results: list[dict[str, Any]]) -> str:
    variant_slugs = [v["slug"] for v in config.get("variants", [])]
    lines = [
        "# Cursor CLI Benchmark Report — Python (Django + Channels)",
        "",
        "Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). "
        "Phase 1 + Phase 2 when `enable_followup` is true.",
        "",
        f"Variants: {', '.join(f'`{s}`' for s in variant_slugs) or '(none)'}",
        "",
        "Runner: `agent -p --output-format stream-json --force --trust`",
        "",
        "Each variant writes under `results/cursor-<slug>/`.",
        "",
        "## Summary",
        "",
        "| Variant | Model | Status | Time | Files | Turns |",
        "|---|---|---|---:|---:|---:|",
    ]
    by_slug = {r.get("slug"): r for r in results if r.get("slug")}
    for slug in variant_slugs:
        r = by_slug.get(slug, {"slug": slug, "status": "not_run"})
        model = r.get("main_model", "-")
        status = r.get("status", "not_run")
        elapsed = r.get("elapsed_seconds") or 0
        files = r.get("file_count") or 0
        turns = r.get("num_turns") or 0
        lines.append(
            f"| {slug} | {model} | {status} | {elapsed:.0f}s | {files} | {turns} |"
        )

    phase_rows = [
        (slug, by_slug[slug])
        for slug in variant_slugs
        if slug in by_slug and by_slug[slug].get("phases")
    ]
    if phase_rows:
        lines.extend(["", "## Phase Breakdown", ""])
        for slug, r in phase_rows:
            lines.append(f"### {slug}")
            lines.append("")
            lines.append("| Phase | Status | Time | Turns | Files |")
            lines.append("|---|---|---:|---:|---:|")
            for ph in r["phases"]:
                lines.append(
                    f"| {ph.get('phase', '?')} | {ph.get('status', '?')} "
                    f"| {ph.get('elapsed_seconds', 0):.0f}s "
                    f"| {ph.get('num_turns', 0)} "
                    f"| {ph.get('file_count', 0)} |"
                )
            lines.append("")

    tool_rows = [
        slug
        for slug in variant_slugs
        if by_slug.get(slug, {}).get("tool_use_counts")
    ]
    if tool_rows:
        lines.extend(["", "## Tool activity", ""])
        for slug in tool_rows:
            counts = by_slug[slug]["tool_use_counts"]
            lines.append(f"### {slug}")
            lines.append("")
            for name, count in sorted(counts.items(), key=lambda x: -x[1]):
                lines.append(f"- `{name}`: {count}")
            lines.append("")

    return "\n".join(lines)
