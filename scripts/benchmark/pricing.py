"""Parse docs/PRICING.md and compute generation cost for audit dispatch."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.audit_rollup import cohort_slug
from benchmark.result_layout import split_target_slug
from benchmark.util import load_json, migrate_to_v2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRICING_PATH = REPO_ROOT / "docs" / "PRICING.md"

_TABLE_HEADER = (
    "| Slug | Provider | Model ID | Channel | Input $/1M | Output $/1M | "
    "Cache read $/1M | Cache write $/1M | Billable | Source | Snapshot |"
)

# OpenRouter id → registry slug for fetch script drift checks.
OPENROUTER_ID_TO_SLUG: dict[str, str] = {
    "openrouter/anthropic/claude-sonnet-4.6": "claude_sonnet_4_6",
    "openrouter/anthropic/claude-opus-4.7": "claude_opus_4_7",
    "moonshotai/kimi-k2.6": "kimi_k2_6",
    "deepseek/deepseek-v4-flash": "deepseek_v4_flash",
    "z-ai/glm-5.1": "glm_5_1",
    "qwen/qwen3.5-plus-02-15": "qwen3_5",
    "minimax/minimax-m2.7": "minimax_m2_7",
}


class PricingError(ValueError):
    """Raised when PRICING.md is malformed or a lookup fails."""


@dataclass(frozen=True)
class PricingRow:
    slug: str
    provider: str
    model_id: str
    channel: str
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None
    cache_write_per_million: float | None
    billable: bool
    source: str
    snapshot: str


@dataclass(frozen=True)
class TokenTotals:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cache_read_tokens: int
    cache_write_tokens: int
    harness_reported_cost_usd: float | None


def pricing_path(repo_root: Path | None = None) -> Path:
    return (repo_root or REPO_ROOT) / "docs" / "PRICING.md"


def parse_last_updated(text: str) -> str | None:
    match = re.search(r"^Last-Updated:\s*(\S+)", text, re.MULTILINE)
    return match.group(1) if match else None


def _parse_price(cell: str) -> float | None:
    cell = cell.strip()
    if not cell or cell.lower() in ("—", "-", "n/a"):
        return None
    return float(cell)


def _parse_billable(cell: str) -> bool:
    return cell.strip().lower() == "yes"


def _split_table_row(line: str) -> list[str]:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def load_pricing_table(path: Path | None = None) -> dict[tuple[str, str], PricingRow]:
    """Parse the main price table from PRICING.md.

    Returns ``{(slug, channel): PricingRow}``.
    """
    pricing_file = path or DEFAULT_PRICING_PATH
    text = pricing_file.read_text(encoding="utf-8")
    rows: dict[tuple[str, str], PricingRow] = {}
    in_table = False
    for line in text.splitlines():
        if line.strip() == _TABLE_HEADER:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if re.match(r"^\|\s*---", line):
            continue
        cells = _split_table_row(line)
        if len(cells) != 11:
            raise PricingError(
                f"expected 11 columns in price row, got {len(cells)}: {line!r}"
            )
        slug, provider, model_id, channel = cells[0], cells[1], cells[2], cells[3]
        inp = _parse_price(cells[4])
        out = _parse_price(cells[5])
        if inp is None or out is None:
            raise PricingError(f"missing input/output price for slug={slug!r}")
        row = PricingRow(
            slug=slug,
            provider=provider,
            model_id=model_id,
            channel=channel,
            input_per_million=inp,
            output_per_million=out,
            cache_read_per_million=_parse_price(cells[6]),
            cache_write_per_million=_parse_price(cells[7]),
            billable=_parse_billable(cells[8]),
            source=cells[9],
            snapshot=cells[10],
        )
        key = (slug, channel)
        if key in rows:
            raise PricingError(f"duplicate pricing row for slug={slug!r} channel={channel!r}")
        rows[key] = row
    if not rows:
        raise PricingError(f"no price rows parsed from {pricing_file}")
    return rows


def channel_for_harness(harness: str, *, provider: str | None = None) -> str:
    """Map benchmark harness (+ optional provider) to a PRICING.md channel key."""
    if provider == "ollama_cloud":
        return "ollama_cloud"
    if harness == "opencode":
        return "openrouter"
    if harness == "cursor":
        return "cursor_list"
    if harness in ("claude", "codex"):
        return "native"
    return "native"


def pricing_row_for_target(
    model_slug: str,
    harness: str,
    *,
    provider: str | None = None,
    table: dict[tuple[str, str], PricingRow] | None = None,
) -> PricingRow:
    """Return the pricing row for a benchmark target."""
    table = table or load_pricing_table()
    channel = channel_for_harness(harness, provider=provider)
    key = (model_slug, channel)
    if key in table:
        return table[key]
    cohort_key = (cohort_slug(model_slug), channel)
    if cohort_key in table:
        return table[cohort_key]
    # Fallback: any row for slug (e.g. unknown harness)
    matches = [r for (s, _), r in table.items() if s == model_slug]
    if not matches:
        matches = [
            r for (s, _), r in table.items() if s == cohort_slug(model_slug)
        ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise PricingError(
            f"ambiguous pricing for slug={model_slug!r} harness={harness!r}; "
            f"channels={[m.channel for m in matches]}"
        )
    raise PricingError(
        f"no pricing row for slug={model_slug!r} channel={channel!r}"
    )


def assert_registry_coverage(
    models: list[dict[str, Any]],
    *,
    table: dict[tuple[str, str], PricingRow] | None = None,
    pricing_path: Path | None = None,
) -> None:
    """Raise if any models.json slug lacks a billable pricing row."""
    if table is None:
        table = load_pricing_table(pricing_path)
    slugs_in_table = {slug for slug, _ in table}
    missing = []
    for m in models:
        if not isinstance(m, dict) or not m.get("slug"):
            continue
        slug = str(m["slug"])
        pricing_slug = cohort_slug(slug)
        if slug in slugs_in_table or pricing_slug in slugs_in_table:
            continue
        if slug.endswith("_opencode"):
            base = slug[: -len("_opencode")]
            if base in slugs_in_table:
                continue
        missing.append(slug)
    if missing:
        raise PricingError(
            f"models.json slugs missing from PRICING.md: {sorted(missing)}"
        )


def cursor_usage_to_model_entry(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize Cursor Agent CLI usage keys to Claude-style model_usage entry."""
    return {
        "inputTokens": int(usage.get("inputTokens") or 0),
        "outputTokens": int(usage.get("outputTokens") or 0),
        "cacheReadInputTokens": int(
            usage.get("cacheReadInputTokens")
            or usage.get("cacheReadTokens")
            or 0
        ),
        "cacheCreationInputTokens": int(
            usage.get("cacheCreationInputTokens")
            or usage.get("cacheWriteTokens")
            or 0
        ),
    }


def model_usage_from_cursor_final(
    main_model: str,
    final: dict[str, Any],
) -> dict[str, Any]:
    """Build model_usage from a Cursor stream-json final result event."""
    usage = final.get("usage")
    if not isinstance(usage, dict) or not usage:
        return {}
    return {main_model: cursor_usage_to_model_entry(usage)}


def merge_cursor_model_usage(
    base: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Sum token fields across two model_usage maps (e.g. phase 1 + phase 2)."""
    merged: dict[str, Any] = {k: dict(v) for k, v in base.items()}
    for model_id, p2_u in extra.items():
        if not isinstance(p2_u, dict):
            continue
        if model_id in merged:
            m = merged[model_id]
            for tok_key in (
                "inputTokens",
                "outputTokens",
                "cacheReadInputTokens",
                "cacheCreationInputTokens",
            ):
                m[tok_key] = int(m.get(tok_key) or 0) + int(p2_u.get(tok_key) or 0)
        else:
            merged[model_id] = dict(p2_u)
    return merged


def _read_cursor_usage_from_ndjson(path: Path) -> dict[str, Any] | None:
    """Return usage from the last result event in a Cursor stream.ndjson file."""
    if not path.is_file():
        return None
    last_usage: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result" and isinstance(event.get("usage"), dict):
            last_usage = event["usage"]
    return last_usage


def enrich_cursor_result_row(
    result_row: dict[str, Any],
    *,
    benchmark_result_path: Path | None = None,
) -> dict[str, Any]:
    """Backfill model_usage for cursor runs that predate usage persistence."""
    if result_row.get("harness") != "cursor":
        return result_row
    existing = result_row.get("model_usage")
    if isinstance(existing, dict) and existing:
        return result_row

    main_model = str(result_row.get("main_model") or "unknown")
    paths = result_row.get("paths")
    if not isinstance(paths, dict):
        paths = {}

    usages: list[dict[str, Any]] = []
    for key in ("stream_ndjson", "followup_stream_ndjson"):
        raw = paths.get(key)
        if not raw:
            continue
        usage = _read_cursor_usage_from_ndjson(Path(raw))
        if usage:
            usages.append(usage)

    if not usages and benchmark_result_path is not None:
        result_dir = benchmark_result_path.parent
        for name in ("stream.ndjson", "followup-stream.ndjson"):
            usage = _read_cursor_usage_from_ndjson(result_dir / name)
            if usage:
                usages.append(usage)

    if not usages:
        usage_total = result_row.get("usage_total") or result_row.get("usage")
        if isinstance(usage_total, dict) and usage_total:
            usages.append(usage_total)

    if not usages:
        return result_row

    merged_entry = {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
    }
    for usage in usages:
        entry = cursor_usage_to_model_entry(usage)
        for tok_key in merged_entry:
            merged_entry[tok_key] += entry[tok_key]

    return {
        **result_row,
        "model_usage": {main_model: merged_entry},
        "usage_total": usages[-1],
    }


def _token_totals_from_cursor_usage(
    usage: dict[str, Any],
    harness_cost: float | None,
) -> TokenTotals:
    entry = cursor_usage_to_model_entry(usage)
    in_tok = entry["inputTokens"]
    out_tok = entry["outputTokens"]
    total = in_tok + out_tok if (in_tok or out_tok) else None
    return TokenTotals(
        input_tokens=in_tok or None,
        output_tokens=out_tok or None,
        total_tokens=total,
        cache_read_tokens=entry["cacheReadInputTokens"],
        cache_write_tokens=entry["cacheCreationInputTokens"],
        harness_reported_cost_usd=harness_cost,
    )


def _sum_model_usage(model_usage: dict[str, Any]) -> TokenTotals:
    in_tok = out_tok = cache_read = cache_write = 0
    reported_cost = 0.0
    has_cost = False
    for usage in model_usage.values():
        if not isinstance(usage, dict):
            continue
        in_tok += int(usage.get("inputTokens") or 0)
        out_tok += int(usage.get("outputTokens") or 0)
        cache_read += int(usage.get("cacheReadInputTokens") or 0)
        cache_write += int(usage.get("cacheCreationInputTokens") or 0)
        cost = usage.get("costUSD")
        if isinstance(cost, (int, float)):
            reported_cost += float(cost)
            has_cost = True
    total = in_tok + out_tok if (in_tok or out_tok) else None
    return TokenTotals(
        input_tokens=in_tok or None,
        output_tokens=out_tok or None,
        total_tokens=total,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        harness_reported_cost_usd=reported_cost if has_cost else None,
    )


def extract_token_totals(
    result_row: dict[str, Any] | None,
    *,
    harness: str,
) -> TokenTotals:
    """Normalize token counts from a benchmark result.json row."""
    if not result_row:
        return TokenTotals(None, None, None, 0, 0, None)

    reported = result_row.get("total_cost_usd")
    harness_cost: float | None = None
    if isinstance(reported, (int, float)):
        harness_cost = float(reported)

    model_usage = result_row.get("model_usage")
    if isinstance(model_usage, dict) and model_usage:
        totals = _sum_model_usage(model_usage)
        if harness_cost is not None and totals.harness_reported_cost_usd is None:
            return TokenTotals(
                totals.input_tokens,
                totals.output_tokens,
                totals.total_tokens,
                totals.cache_read_tokens,
                totals.cache_write_tokens,
                harness_cost,
            )
        if totals.harness_reported_cost_usd is not None:
            return totals
        return totals

    tokens = result_row.get("tokens") or {}
    if isinstance(tokens, dict) and tokens:
        inp = tokens.get("input")
        out = tokens.get("output")
        total = tokens.get("total")
        if isinstance(inp, int) and isinstance(out, int):
            total = total if isinstance(total, int) else inp + out
        elif isinstance(total, int) and not isinstance(inp, int):
            inp = None
            out = None
        return TokenTotals(
            input_tokens=inp if isinstance(inp, int) else None,
            output_tokens=out if isinstance(out, int) else None,
            total_tokens=total if isinstance(total, int) else None,
            cache_read_tokens=0,
            cache_write_tokens=0,
            harness_reported_cost_usd=harness_cost,
        )

    usage = result_row.get("usage_total") or result_row.get("usage")
    if isinstance(usage, dict) and usage:
        return _token_totals_from_cursor_usage(usage, harness_cost)

    return TokenTotals(None, None, None, 0, 0, harness_cost)


def compute_estimated_cost(row: PricingRow, tokens: TokenTotals) -> float | None:
    """Apply PRICING.md formula; return None when not billable or tokens unknown."""
    if not row.billable:
        return None
    if tokens.input_tokens is None or tokens.output_tokens is None:
        return None

    cache_read_rate = row.cache_read_per_million
    if cache_read_rate is None and tokens.cache_read_tokens:
        cache_read_rate = row.input_per_million
    cache_write_rate = row.cache_write_per_million
    if cache_write_rate is None and tokens.cache_write_tokens:
        cache_write_rate = row.input_per_million

    cost = (
        tokens.input_tokens / 1_000_000 * row.input_per_million
        + tokens.output_tokens / 1_000_000 * row.output_per_million
    )
    if cache_read_rate is not None:
        cost += tokens.cache_read_tokens / 1_000_000 * cache_read_rate
    if cache_write_rate is not None:
        cost += tokens.cache_write_tokens / 1_000_000 * cache_write_rate
    return round(cost, 6)


def _harness_cli_fields_from_result(result_row: dict[str, Any] | None) -> dict[str, Any]:
    """Extract CLI version fields persisted by benchmark runners."""
    if result_row is None:
        return {
            "harness_cli_version": None,
            "harness_cli_probe_argv": None,
            "command_shim_version": None,
            "command_shim_probe_argv": None,
        }
    return {
        "harness_cli_version": result_row.get("harness_cli_version"),
        "harness_cli_probe_argv": result_row.get("harness_cli_probe_argv"),
        "command_shim_version": result_row.get("command_shim_version"),
        "command_shim_probe_argv": result_row.get("command_shim_probe_argv"),
    }


def build_generation_metrics(
    *,
    target_slug: str,
    model_slug: str,
    harness: str,
    benchmark_result_path: Path | None,
    provider: str | None = None,
    pricing_doc: Path | None = None,
) -> dict[str, Any]:
    """Build the generation-metrics dict written before audit dispatch."""
    doc = pricing_doc or DEFAULT_PRICING_PATH
    last_updated = parse_last_updated(doc.read_text(encoding="utf-8")) or "unknown"
    target_group = target_slug.split("/", 1)[0]
    prefix, _ = split_target_slug(target_group)
    effective_harness = harness if harness != "unknown" else (prefix or harness)

    result_row: dict[str, Any] | None = None
    if benchmark_result_path and benchmark_result_path.is_file():
        try:
            result_row = migrate_to_v2(load_json(benchmark_result_path))
            result_row = enrich_cursor_result_row(
                result_row, benchmark_result_path=benchmark_result_path
            )
        except Exception:
            result_row = None

    if result_row is None:
        return {
            "status": "missing_benchmark_result",
            "target_slug": target_slug,
            "harness": effective_harness,
            "model_slug": model_slug,
            "benchmark_result_path": str(benchmark_result_path) if benchmark_result_path else None,
            "generation_time_seconds": None,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "estimated_cost_usd": None,
            "cost_source": "n/a",
            "pricing_doc": str(doc.relative_to(REPO_ROOT)),
            "pricing_last_updated": last_updated,
            "pricing_row_slug": model_slug,
            "channel": channel_for_harness(effective_harness, provider=provider),
            "billable": None,
            **_harness_cli_fields_from_result(None),
        }

    tokens = extract_token_totals(result_row, harness=effective_harness)
    try:
        row = pricing_row_for_target(
            model_slug, effective_harness, provider=provider
        )
    except PricingError:
        return {
            "status": "missing_pricing_row",
            "target_slug": target_slug,
            "harness": effective_harness,
            "model_slug": model_slug,
            "benchmark_result_path": str(benchmark_result_path.resolve()),
            "generation_time_seconds": result_row.get("elapsed_seconds"),
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "total_tokens": tokens.total_tokens,
            "cache_read_tokens": tokens.cache_read_tokens,
            "cache_write_tokens": tokens.cache_write_tokens,
            "estimated_cost_usd": None,
            "cost_source": "n/a",
            "pricing_doc": str(doc.relative_to(REPO_ROOT)),
            "pricing_last_updated": last_updated,
            "pricing_row_slug": model_slug,
            "channel": channel_for_harness(effective_harness, provider=provider),
            "billable": None,
            **_harness_cli_fields_from_result(result_row),
        }

    if tokens.harness_reported_cost_usd is not None:
        cost = round(tokens.harness_reported_cost_usd, 6)
        cost_source = "harness_reported"
    else:
        cost = compute_estimated_cost(row, tokens)
        cost_source = "computed" if cost is not None else "n/a"

    return {
        "status": "ok",
        "target_slug": target_slug,
        "harness": effective_harness,
        "model_slug": model_slug,
        "benchmark_result_path": str(benchmark_result_path.resolve()),
        "generation_time_seconds": result_row.get("elapsed_seconds"),
        "input_tokens": tokens.input_tokens,
        "output_tokens": tokens.output_tokens,
        "total_tokens": tokens.total_tokens,
        "cache_read_tokens": tokens.cache_read_tokens,
        "cache_write_tokens": tokens.cache_write_tokens,
        "estimated_cost_usd": cost,
        "cost_source": cost_source,
        "harness_reported_cost_usd": tokens.harness_reported_cost_usd,
        "pricing_doc": str(doc.relative_to(REPO_ROOT)),
        "pricing_last_updated": last_updated,
        "pricing_row_slug": row.slug,
        "channel": row.channel,
        "billable": row.billable,
        "primary_prompt_sha256": result_row.get("prompt_sha256"),
        "followup_prompt_sha256": result_row.get("followup_prompt_sha256"),
        **_harness_cli_fields_from_result(result_row),
    }


def format_generation_metrics_block(metrics: dict[str, Any]) -> str:
    """Markdown snippet for audit section H — auditor copies verbatim."""

    def fmt_num(key: str) -> str:
        val = metrics.get(key)
        if val is None:
            return "n/a"
        if isinstance(val, float):
            return f"{val:.6f}".rstrip("0").rstrip(".")
        return str(val)

    cost = metrics.get("estimated_cost_usd")
    cost_str = fmt_num("estimated_cost_usd") if cost is not None else "n/a"
    pricing_source = (
        f"{metrics.get('pricing_doc', 'docs/PRICING.md')} @ "
        f"{metrics.get('pricing_last_updated', 'unknown')}"
    )
    shim_version = metrics.get("command_shim_version")
    shim_line = (
        [f"- Command-Shim-Version: {shim_version}"]
        if shim_version
        else []
    )
    return "\n".join(
        [
            "Precomputed generation metrics (copy verbatim into section H; do not recalculate):",
            f"- Model: {metrics.get('display_model_slug') or metrics.get('model_slug', 'n/a')}",
            f"- Harness: {metrics.get('harness', 'n/a')}",
            f"- Harness-CLI-Version: {metrics.get('harness_cli_version') or 'n/a'}",
            *shim_line,
            f"- Generation-Time: {fmt_num('generation_time_seconds')} seconds",
            f"- Input-Tokens: {fmt_num('input_tokens')}",
            f"- Output-Tokens: {fmt_num('output_tokens')}",
            f"- Total-Tokens: {fmt_num('total_tokens')}",
            f"- Estimated-Cost-USD: {cost_str}",
            f"- Pricing-Source: {pricing_source}",
            f"- Cost-Source: {metrics.get('cost_source', 'n/a')}",
            f"- Benchmark-Result: {metrics.get('benchmark_result_path', 'n/a')}",
            f"- Primary-Prompt-SHA256: {metrics.get('primary_prompt_sha256') or 'n/a'}",
            f"- Followup-Prompt-SHA256: {metrics.get('followup_prompt_sha256') or 'n/a'}",
        ]
    )


def validate_section_h_cost(
    report_text: str,
    metrics: dict[str, Any],
    *,
    tolerance: float = 0.01,
) -> list[str]:
    """Return mismatch messages comparing report section H to generation-metrics."""
    issues: list[str] = []
    expected = metrics.get("estimated_cost_usd")
    if expected is None:
        return issues
    match = re.search(
        r"Estimated-Cost-USD\s*[:\-—]\s*\$?([\d.]+|n/a)",
        report_text,
        re.IGNORECASE,
    )
    if not match:
        issues.append("section H missing Estimated-Cost-USD")
        return issues
    raw = match.group(1).strip()
    if raw.lower() == "n/a":
        issues.append(f"section H cost is n/a but metrics expect {expected}")
        return issues
    try:
        reported = float(raw)
    except ValueError:
        issues.append(f"section H cost not parseable: {raw!r}")
        return issues
    if abs(reported - float(expected)) > tolerance:
        issues.append(
            f"section H cost {reported} != generation-metrics {expected} "
            f"(tolerance {tolerance})"
        )
    return issues
