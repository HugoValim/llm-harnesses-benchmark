"""Markdown report for Claude Code benchmark variants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_variant_results(
    config: dict[str, Any],
    results_dir: Path,
    *,
    harness: str = "claude",
) -> list[dict[str, Any]]:
    """Load ``result.json`` for each variant declared in the config (stable order)."""
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
    """Build markdown summarizing Claude Code variant runs."""
    variant_slugs = [v["slug"] for v in config.get("variants", [])]
    lines = [
        "# Claude Code Benchmark Report — Python (Django + Channels + LangChain)",
        "",
        "Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.",
        "",
        f"Variants in this config: {', '.join(f'`{s}`' for s in variant_slugs) or '(none)'}",
        "",
        "Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`",
        "",
        "Each variant writes under `results/claude-<slug>/`.",
        "",
        "## Summary",
        "",
        "| Variant | Status | Time | Files | Turns | Delegations |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_slug = {r.get("slug"): r for r in results if r.get("slug")}
    for slug in variant_slugs:
        r = by_slug.get(slug, {"slug": slug, "status": "not_run"})
        status = r.get("status", "not_run")
        elapsed = r.get("elapsed_seconds") or 0
        files = r.get("file_count") or 0
        turns = r.get("num_turns") or 0
        delegations = sum((r.get("subagent_invocation_counts") or {}).values())
        lines.append(
            f"| {slug} | {status} | {elapsed:.0f}s | {files} | {turns} | {delegations} |"
        )

    lines.extend(["", "## Per-Model Token Usage", ""])
    lines.append("Extracted from Claude Code's `modelUsage` field.")
    lines.append("")
    for slug in variant_slugs:
        r = by_slug.get(slug, {})
        mu = r.get("model_usage") or {}
        if not mu:
            continue
        lines.append(f"### {slug}")
        lines.append("")
        lines.append("| Model | Input | Output | Cache Read | Cache Create |")
        lines.append("|---|---:|---:|---:|---:|")
        for model, u in mu.items():
            in_t = u.get("inputTokens", 0)
            out_t = u.get("outputTokens", 0)
            cr = u.get("cacheReadInputTokens", 0)
            cc = u.get("cacheCreationInputTokens", 0)
            lines.append(f"| {model} | {in_t:,} | {out_t:,} | {cr:,} | {cc:,} |")
        lines.append("")

    lines.extend(["## Delegation Details", ""])
    for slug in variant_slugs:
        r = by_slug.get(slug, {})
        invocations = r.get("subagent_invocations") or []
        if not invocations:
            continue
        lines.append(f"### {slug} ({len(invocations)} delegations)")
        lines.append("")
        for i, inv in enumerate(invocations, 1):
            desc = (inv.get("description") or "").replace("\n", " ")[:200]
            lines.append(f"{i}. `{inv.get('subagent_type')}` — {desc}")
        lines.append("")

    return "\n".join(lines)
