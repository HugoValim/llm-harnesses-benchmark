"""Benchmark report generation for all harnesses (opencode, codex, claude, cursor)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.config import summarize_project
from benchmark.result_layout import target_result_json
from benchmark.util import (
    USAGE_LIMIT_REACHED,
    format_value,
    load_json,
    migrate_to_v2,
    model_matches_harness,
    prompt_sha256,
    utc_now,
)


def _rederive_status(row: dict[str, Any], project_summary: dict[str, Any]) -> str:
    """Recompute the run status using the fresh project summary.

    Mirrors the logic in :func:`benchmark.runner.run_codex_phase` /
    ``run_opencode_phase`` so a ``--report-only`` rebuild reflects updated
    scaffold detection without re-running the benchmark.
    """
    if row.get("stalled") and row.get("stall_reason") == USAGE_LIMIT_REACHED:
        return USAGE_LIMIT_REACHED
    if row.get("timed_out"):
        return "timeout"
    if row.get("stalled"):
        return "failed"
    works = project_summary.get("works_as_intended") == "yes"
    terminal_stop = row.get("finish_reason") == "stop"
    if terminal_stop and works:
        return "completed"
    if terminal_stop:
        return "completed_with_errors"
    exit_code = row.get("exit_code")
    if exit_code == 0 and works:
        return "completed"
    if exit_code == 0:
        return "completed_with_errors"
    return "failed"


# ── unified loading ──────────────────────────────────────────────────────────


def load_results(
    config: dict[str, Any],
    results_dir: Path,
    warmup_payload: dict[str, Any] | None = None,
    *,
    harness: str = "opencode",
) -> list[dict[str, Any]]:
    """Load ``result.json`` for every model or variant declared in *config*."""
    warmup_results = warmup_payload.get("results_by_slug", {}) if warmup_payload else {}

    if harness in ("claude", "cursor"):
        return _load_variant_results(config, results_dir, harness, warmup_results)
    return _load_model_results(config, results_dir, harness, warmup_results)


def _load_model_results(
    config: dict[str, Any],
    results_dir: Path,
    harness: str,
    warmup_results: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in config["models"]:
        if not model_matches_harness(model, harness):
            continue
        result_path = target_result_json(results_dir, harness, model['slug'])
        if result_path.exists():
            row = migrate_to_v2(load_json(result_path))
            row["ollama_warmup"] = warmup_results.get(model["slug"])
            project_dir_path = (row.get("paths") or {}).get("project_dir")
            if project_dir_path:
                project_dir = Path(project_dir_path)
                if project_dir.is_dir():
                    fresh = summarize_project(project_dir)
                    row["project_summary"] = fresh
                    row["status"] = _rederive_status(row, fresh)
            rows.append(row)
            continue
        rows.append({
            "status": "not_run",
            "elapsed_seconds": None,
            "tokens": {},
            "tokens_per_second": None,
            "output_tokens_per_second": None,
            "model": model,
            "harness": harness,
            "result_schema_version": 2,
            "ollama_warmup": warmup_results.get(model["slug"]),
            "project_summary": {
                "file_count": 0,
                "works_as_intended": "n/a",
                "works_note": "Run has not been executed yet.",
            },
        })
    return rows


def _load_variant_results(
    config: dict[str, Any],
    results_dir: Path,
    harness: str,
    warmup_results: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for v in config.get("variants", []):
        slug = v["slug"]
        rp = target_result_json(results_dir, harness, slug)
        if rp.exists():
            try:
                rows.append(migrate_to_v2(json.loads(rp.read_text())))
            except json.JSONDecodeError:
                rows.append({"slug": slug, "status": "not_run"})
        else:
            rows.append({"slug": slug, "status": "not_run"})
    return rows


# ── helpers ──────────────────────────────────────────────────────────────────


def _build_notes(
    result: dict[str, Any], warmup_minimum_useful_context: int | None
) -> str:
    summary = result.get("project_summary") or {}
    notes = summary.get("works_note", "")
    if result.get("timed_out"):
        notes = f"Timed out. {notes}".strip()
    elif result.get("exit_code") not in (None, 0):
        notes = f"Exit code {result['exit_code']}. {notes}".strip()

    warmup = result.get("ollama_warmup")
    if isinstance(warmup, dict):
        highest = warmup.get("highest_verified_context")
        recommendation = warmup.get("recommendation")
        if highest is None:
            warmup_note = "Warmup found no verified Ollama context."
        elif (
            warmup_minimum_useful_context is not None
            and highest < warmup_minimum_useful_context
        ):
            warmup_note = f"Warmup only verified up to {highest} context."
        else:
            warmup_note = f"Warmup verified {highest} context."
        if isinstance(recommendation, str) and recommendation:
            warmup_note = f"{warmup_note} {recommendation}."
        notes = f"{notes} {warmup_note}".strip()

    return notes.replace("|", "/")


# ── unified report builder ───────────────────────────────────────────────────


def build_report(
    config: dict[str, Any],
    results: list[dict[str, Any]],
    prompt: str | None = None,
    warmup_payload: dict[str, Any] | None = None,
    warmup_path: Path | None = None,
    *,
    harness: str = "opencode",
) -> str:
    """Build a markdown report for *harness* from *results*."""
    if harness in ("claude", "cursor"):
        return _build_cli_report(config, results, harness)
    return _build_model_report(config, results, prompt or "", warmup_payload, warmup_path, harness)


def _build_model_report(
    config: dict[str, Any],
    results: list[dict[str, Any]],
    prompt: str,
    warmup_payload: dict[str, Any] | None,
    warmup_path: Path | None,
    harness: str,
) -> str:
    lines: list[str] = []
    counts: dict[str, int] = {}
    warmup_minimum_useful_context = None
    if warmup_payload:
        minimum = warmup_payload.get("minimum_useful_context")
        if isinstance(minimum, int):
            warmup_minimum_useful_context = minimum
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"Generated at: {utc_now()}")
    lines.append(f"Prompt SHA256: `{prompt_sha256(prompt)}`")
    lines.append("")

    # Progress
    lines.append("## Progress")
    lines.append("")
    for status in (
        "completed", "completed_with_errors", "failed", "timeout",
        "usage_limit_reached", "not_run",
    ):
        lines.append(f"- `{status}`: {counts.get(status, 0)}")
    lines.append("")

    # Runner
    lines.append("## Runner")
    lines.append("")
    if harness in {"codex", "ollama"}:
        lines.append(
            "`codex exec --json --ephemeral ...` "
            f"(harness `{harness}` — runs under `results/{harness}-<slug>/`)"
        )
    else:
        lines.append(
            "`opencode run --agent build --format json` "
            f"(harness `{harness}` — runs under `results/{harness}-<slug>/`)"
        )
    lines.append("")
    for note in config["runner"]["notes"]:
        lines.append(f"- {note}")
    lines.append("")

    # Model Selection
    lines.append("## Model Selection")
    lines.append("")
    for model in config["models"]:
        if not model_matches_harness(model, harness):
            continue
        lines.append(
            f"- `{model['slug']}` -> `{model['id']}`: {model['selection_reason']}"
        )
    lines.append("")

    # Ollama Warmup
    if warmup_payload:
        lines.append("## Ollama Warmup")
        lines.append("")
        if warmup_path is not None:
            lines.append(f"Loaded from `{warmup_path}`.")
            lines.append("")
        if warmup_minimum_useful_context is not None:
            lines.append(
                f"Minimum useful context target: `{warmup_minimum_useful_context}`"
            )
            lines.append("")
        lines.append("| Model | Highest verified ctx | Recommendation |")
        lines.append("| --- | ---: | --- |")
        for result in results:
            model = result.get("model") or {}
            if model.get("provider") != "ollama":
                continue
            warmup = result.get("ollama_warmup")
            if isinstance(warmup, dict):
                highest = format_value(warmup.get("highest_verified_context"))
                recommendation = str(warmup.get("recommendation", "-")).replace("|", "/")
            else:
                highest = "-"
                recommendation = "No warmup result recorded."
            lines.append(f"| {model.get('label', '-')} | {highest} | {recommendation} |")
        lines.append("")

    # Results
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |"
    )
    lines.append(
        "| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |"
    )
    for result in results:
        model = result.get("model") or {}
        summary = result.get("project_summary") or {}
        tokens = result.get("tokens") or {}
        warmup = result.get("ollama_warmup")
        warmup_context = (
            format_value(warmup.get("highest_verified_context"))
            if isinstance(warmup, dict)
            else "-"
        )
        notes = _build_notes(result, warmup_minimum_useful_context)
        label = model.get("label", result.get("slug", "-"))
        provider = model.get("provider", result.get("harness", "-"))
        lines.append(
            f"| {label} | {provider} | {warmup_context} | {result.get('status', '-')} "
            f"| {format_value(result.get('elapsed_seconds'))} "
            f"| {format_value(tokens.get('total'))} "
            f"| {format_value(result.get('tokens_per_second'))} "
            f"| {summary.get('works_as_intended', '-')} "
            f"| {format_value(summary.get('file_count'))} "
            f"| {notes or '-'} |"
        )
    lines.append("")

    # Per-run paths
    lines.append("## Per-Run Paths")
    lines.append("")
    lines.append(f"Each run writes to `results/{harness}-<slug>/` with these files:")
    lines.append("")
    lines.append("- `project/`: the generated project workspace")
    lines.append("- `prompt.txt`: exact prompt used for the run")
    lines.append("- `opencode-output.ndjson`: raw JSON event stream from opencode")
    lines.append("- `opencode-stderr.log`: stderr from the opencode process")
    lines.append(
        "- `followup-prompt.txt`: second-phase validation prompt for continuations when enabled"
    )
    lines.append(
        "- `followup-opencode-output.ndjson`: raw JSON event stream from the follow-up continuation"
    )
    lines.append(
        "- `followup-opencode-stderr.log`: stderr from the follow-up continuation"
    )
    lines.append(
        "- `session-export.json`: exported opencode session snapshot when available"
    )
    lines.append("- `result.json`: normalized metadata used for this report")
    lines.append("")
    return "\n".join(lines) + "\n"


def _build_cli_report(
    config: dict[str, Any],
    results: list[dict[str, Any]],
    harness: str,
) -> str:
    """Build markdown for claude / cursor variant-based harnesses."""
    variant_slugs = [v["slug"] for v in config.get("variants", [])]
    harness_label = "Claude Code" if harness == "claude" else "Cursor CLI"
    runner_desc = (
        "`claude -p --output-format stream-json --dangerously-skip-permissions`"
        if harness == "claude"
        else "`agent -p --output-format stream-json --force --trust`"
    )

    lines = [
        f"# {harness_label} Benchmark Report — Python (Django + Channels)",
        "",
        f"Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`).",
        "",
        f"Variants: {', '.join(f'`{s}`' for s in variant_slugs) or '(none)'}",
        "",
        f"Runner: {runner_desc}",
        "",
        f"Each variant writes under `results/{harness}-<slug>/`.",
        "",
        "## Summary",
        "",
    ]

    # Summary table — columns depend on harness
    by_slug = {r.get("slug"): r for r in results if r.get("slug")}

    if harness == "claude":
        lines.append("| Variant | Status | Time | Files | Turns | Delegations |")
        lines.append("|---|---:|---:|---:|---:|")
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
    else:
        lines.append("| Variant | Model | Status | Time | Files | Turns |")
        lines.append("|---|---|---|---:|---:|---:|")
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

    # Phase Breakdown (shared by claude and cursor)
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

    # Harness-specific sections
    if harness == "claude":
        _append_claude_sections(lines, variant_slugs, by_slug)
    else:
        _append_cursor_sections(lines, variant_slugs, by_slug)

    return "\n".join(lines)


def _append_claude_sections(
    lines: list[str],
    variant_slugs: list[str],
    by_slug: dict[str, dict[str, Any]],
) -> None:
    # Token usage
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

    # Delegation details
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


def _append_cursor_sections(
    lines: list[str],
    variant_slugs: list[str],
    by_slug: dict[str, dict[str, Any]],
) -> None:
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
