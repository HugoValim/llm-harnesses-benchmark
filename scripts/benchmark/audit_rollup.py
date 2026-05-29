"""Statistical normalization for audit reports.

Consumes typed :class:`~benchmark.audit_report.ParsedReport` values. Produces
harness comparison, cross-harness model comparison, dimension breakdown, and
leader-relative normalized scores. These are auto-computed inputs for the AI
meta-analyst — not the final analysis.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean

from benchmark.audit_report import (
    NUM_DIMENSIONS,
    TIERS,
    ParsedReport,
    _collect_reports,
    _dimension_labels,
    _fmt,
)

# Model slug substrings that identify benchmark leader runs (substring match,
# case-insensitive), e.g. ``codex-gpt_5_5`` → ``gpt_5_5``, ``opencode-claude_opus_4_7``.
LEADER_MODEL_SLUG_SUBSTRINGS: tuple[str, ...] = ("gpt_5_5", "claude_opus_4_7")

_NORMALIZED_PCT_CAP = 150.0


def _is_leader_slug(model_slug: str) -> bool:
    """Return True when ``model_slug`` matches a configured leader substring."""
    lowered = model_slug.lower()
    return any(s.lower() in lowered for s in LEADER_MODEL_SLUG_SUBSTRINGS)


def _leader_ceiling(reports: list[ParsedReport]) -> dict[str, float | None]:
    """Mean total and per-dimension scores across all leader-target reports.

    Keys: ``"total"`` and ``"1"``..``"9"`` for D1..D9. When no leader
    reports exist, every value is ``None``.
    """
    keys = ["total", *[str(i) for i in range(1, NUM_DIMENSIONS + 1)]]
    leaders = [r for r in reports if _is_leader_slug(r.model_slug)]
    if not leaders:
        return dict.fromkeys(keys, None)

    out: dict[str, float | None] = {}
    totals = [float(r.total) for r in leaders if r.total is not None]
    out["total"] = mean(totals) if totals else None
    for i in range(1, NUM_DIMENSIONS + 1):
        vals = [float(r.dim_score(i)) for r in leaders if r.dim_score(i) is not None]
        out[str(i)] = mean(vals) if vals else None
    return out


def _pct_of_ceiling(numer: float, ceiling: float | None) -> str:
    """Format ``numer/ceiling`` as a percentage capped at 150%, or ``-``."""
    if ceiling is None or ceiling <= 0:
        return "-"
    pct = min(_NORMALIZED_PCT_CAP, (numer / ceiling) * 100.0)
    return f"{pct:.1f}%"


def _normalized_scores_section(
    reports: list[ParsedReport],
    dim_labels: list[str],
) -> list[str]:
    """Markdown block: leader ceiling + non-leader scores as % of leaders."""
    lines: list[str] = [
        "## Normalized scores",
        "",
        "Non-leader model slugs vs mean totals/dimensions of benchmark leader "
        f"runs (substring match on slugs: {', '.join(repr(s) for s in LEADER_MODEL_SLUG_SUBSTRINGS)}). "
        "Percentages are capped at 150% of the leader mean for that column.",
        "",
    ]
    leader_reports = [r for r in reports if _is_leader_slug(r.model_slug)]
    if not leader_reports:
        lines.append("*(no leader runs found — normalization skipped)*")
        return lines

    ceiling = _leader_ceiling(reports)
    if ceiling.get("total") is None:
        lines.append(
            "*(leader runs present but no parseable totals — normalization skipped)*"
        )
        return lines

    leader_slugs = sorted({r.model_slug for r in leader_reports})
    lines.append("### Benchmark leaders (ceiling)")
    lines.append("")
    lh_header = ["Model slug", "Reports", "Harnesses", "Avg total"]
    lines.append("| " + " | ".join(lh_header) + " |")
    lines.append("|" + "|".join(["---"] * len(lh_header)) + "|")
    for slug in leader_slugs:
        subset = [r for r in reports if r.model_slug == slug]
        totals_l = [float(r.total) for r in subset if r.total is not None]
        avg_l = mean(totals_l) if totals_l else None
        harnesses = ", ".join(sorted({r.harness for r in subset}))
        lines.append(
            "| "
            + " | ".join(
                [
                    slug,
                    str(len(subset)),
                    harnesses or "-",
                    _fmt(avg_l),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append(
        f"**Ceiling (leader mean)**: total={_fmt(ceiling['total'])}; "
        + "; ".join(
            f"D{i}={_fmt(ceiling[str(i)])}" for i in range(1, NUM_DIMENSIONS + 1)
        )
    )
    lines.append("")

    by_slug: dict[str, list[ParsedReport]] = {}
    for r in reports:
        if _is_leader_slug(r.model_slug):
            continue
        by_slug.setdefault(r.model_slug, []).append(r)

    rows: list[tuple[float, list[str]]] = []
    for slug, subset in by_slug.items():
        totals_m = [float(r.total) for r in subset if r.total is not None]
        if not totals_m:
            continue
        raw_avg = mean(totals_m)
        harnesses = ", ".join(sorted({r.harness for r in subset}))
        pct_total = _pct_of_ceiling(raw_avg, ceiling["total"])
        dim_pcts: list[str] = []
        for i in range(1, NUM_DIMENSIONS + 1):
            dim_vals = [float(r.dim_score(i)) for r in subset if r.dim_score(i) is not None]
            dim_avg = mean(dim_vals) if dim_vals else None
            dim_pcts.append(
                _pct_of_ceiling(dim_avg, ceiling[str(i)])
                if dim_avg is not None
                else "-"
            )
        row_cells = [
            slug,
            harnesses or "-",
            _fmt(raw_avg),
            pct_total,
            *dim_pcts,
        ]
        rows.append((raw_avg, row_cells))

    rows.sort(key=lambda t: t[0], reverse=True)

    nh_header = ["Model slug", "Harnesses", "Raw avg", "% of ceiling"]
    nh_header.extend(f"D{i} %" for i in range(1, NUM_DIMENSIONS + 1))
    lines.append("### Non-leader models (vs ceiling)")
    lines.append("")
    lines.append("| " + " | ".join(nh_header) + " |")
    lines.append("|" + "|".join(["---"] * len(nh_header)) + "|")
    if not rows:
        lines.append(
            "| *(no non-leader reports with a parseable total)* | "
            + " | ".join([""] * (len(nh_header) - 1))
            + " |"
        )
    else:
        for _, cells in rows:
            lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("Dimension legend (for D% columns):")
    lines.append("")
    for i, label in enumerate(dim_labels, 1):
        lines.append(f"- **D{i}**: {label}")
    return lines


# ── harness / model / dimension rollups ──────────────────────────────────────


def _avg(values: list[float]) -> float | None:
    return mean(values) if values else None


def _harness_section(reports: list[ParsedReport], dim_labels: list[str]) -> list[str]:
    """Per-harness rollup table — the primary signal this skill cares about."""
    harnesses = sorted({r.harness for r in reports if r.harness != "unknown"})
    if not harnesses:
        return []

    header = ["Harness", "Runs", "Avg Total"]
    header.extend(f"Tier {t}" for t in TIERS)
    header.extend(f"D{i}" for i in range(1, NUM_DIMENSIONS + 1))

    lines = [
        "## Harness comparison",
        "",
        "One row per harness. Averages are taken across every audited target",
        "under that harness (i.e. across all model slugs). `Tier X` columns",
        "count how many runs landed in that tier.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]

    for harness in harnesses:
        subset = [r for r in reports if r.harness == harness]
        totals = [r.total for r in subset if r.total is not None]
        tier_counts = {t: sum(1 for r in subset if r.tier == t) for t in TIERS}
        row = [
            harness,
            str(len(subset)),
            _fmt(_avg([float(t) for t in totals])),
        ]
        row.extend(str(tier_counts[t]) for t in TIERS)
        for i in range(1, NUM_DIMENSIONS + 1):
            dim_values = [
                float(r.dim_score(i))
                for r in subset
                if r.dim_score(i) is not None
            ]
            row.append(_fmt(_avg(dim_values)))
        lines.append("| " + " | ".join(row) + " |")

    best_avg: float | None = None
    best_names: list[str] = []
    for harness in harnesses:
        totals = [
            float(r.total)
            for r in reports
            if r.harness == harness and r.total is not None
        ]
        avg = _avg(totals)
        if avg is None:
            continue
        if best_avg is None or avg > best_avg:
            best_avg = avg
            best_names = [harness]
        elif avg == best_avg:
            best_names.append(harness)

    if best_names and best_avg is not None:
        lines.extend(
            [
                "",
                f"**Best harness by average total**: "
                f"{', '.join(f'`{n}`' for n in best_names)} "
                f"({_fmt(best_avg)}/100).",
            ]
        )

    lines.append("")
    lines.append("Dimension legend:")
    lines.append("")
    for i, label in enumerate(dim_labels, 1):
        lines.append(f"- **D{i}**: {label}")
    return lines


def _cross_harness_model_section(
    reports: list[ParsedReport],
    dim_labels: list[str],
) -> list[str]:
    """For each model slug audited under >=2 harnesses, show scores side by side."""
    by_model: dict[str, list[ParsedReport]] = {}
    for r in reports:
        if r.model_slug:
            by_model.setdefault(r.model_slug, []).append(r)
    shared = {slug: rs for slug, rs in by_model.items() if len({r.harness for r in rs}) >= 2}
    if not shared:
        return []

    lines = [
        "## Cross-harness model comparison",
        "",
        "Same model slug, different harness. Shows where harness choice",
        "moves the score for an otherwise identical target model.",
        "",
    ]

    header = ["Model slug", "Harness", "Total", "Tier"]
    header.extend(f"D{i}" for i in range(1, NUM_DIMENSIONS + 1))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for slug in sorted(shared):
        slug_reports = sorted(shared[slug], key=lambda r: r.harness)
        for r in slug_reports:
            row = [slug, r.harness, _fmt(r.total), r.tier or "-"]
            for i in range(1, NUM_DIMENSIONS + 1):
                row.append(_fmt(r.dim_score(i)))
            lines.append("| " + " | ".join(row) + " |")

    return lines


def _dimension_breakdown_section(
    reports: list[ParsedReport],
    dim_labels: list[str],
) -> list[str]:
    """Per-dimension average by harness — surfaces universal vs harness-specific weaknesses."""
    harnesses = sorted({r.harness for r in reports if r.harness != "unknown"})
    if not harnesses:
        return []

    lines = [
        "## Dimension breakdown",
        "",
        "Average score per dimension, overall and per harness. A dimension",
        "where every harness scores low is a universal blind spot (likely a",
        "prompt or model-family issue). A dimension where only one harness",
        "scores low is harness-attributable.",
        "",
    ]

    header = ["Dimension", "Max", "All avg"]
    header.extend(f"{h} avg" for h in harnesses)
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for i in range(1, NUM_DIMENSIONS + 1):
        label = dim_labels[i - 1] if i - 1 < len(dim_labels) else f"D{i}"
        max_score = _max_for_dimension(reports, i)
        all_values = [
            float(r.dim_score(i)) for r in reports if r.dim_score(i) is not None
        ]
        row = [f"D{i}. {label}", _fmt(max_score), _fmt(_avg(all_values))]
        for harness in harnesses:
            subset_values = [
                float(r.dim_score(i))
                for r in reports
                if r.harness == harness and r.dim_score(i) is not None
            ]
            row.append(_fmt(_avg(subset_values)))
        lines.append("| " + " | ".join(row) + " |")

    return lines


def _max_for_dimension(reports: list[ParsedReport], index: int) -> int | None:
    """Look up the rubric max for a 1-indexed dimension from any parsed report."""
    for r in reports:
        for d in r.dimensions:
            if d.index == index:
                return d.max_score
    return None


def model_harness_coverage(reports: list[ParsedReport]) -> dict[str, dict[str, object]]:
    """Per-model harness coverage keyed by model slug.

    Values: ``harnesses`` (sorted list), ``runs`` (int), ``avg_total`` (float|None).
    Only reports with a parseable total contribute to ``avg_total``.
    """
    by_model: dict[str, list[ParsedReport]] = {}
    for r in reports:
        if r.model_slug:
            by_model.setdefault(r.model_slug, []).append(r)

    out: dict[str, dict[str, object]] = {}
    for slug, subset in by_model.items():
        harnesses = sorted({r.harness for r in subset if r.harness != "unknown"})
        totals = [float(r.total) for r in subset if r.total is not None]
        out[slug] = {
            "harnesses": harnesses,
            "runs": len(subset),
            "harness_count": len(harnesses),
            "avg_total": mean(totals) if totals else None,
        }
    return out


def build_model_coverage_table(reports: list[ParsedReport]) -> str:
    """Markdown table: model slug → harness list → run count → avg total."""
    coverage = model_harness_coverage(reports)
    if not coverage:
        return "## Model coverage\n\n*(no reports parsed)*\n"

    lines = [
        "## Model coverage",
        "",
        "Authoritative harness counts for section 2 **Harnesses seen**. "
        "``harness_count`` is the number of distinct harness prefixes with "
        "a parseable total for that model slug.",
        "",
        "| Model slug | Harnesses | Harness count | Runs | Avg total |",
        "|---|---|---:|---:|---:|",
    ]
    rows: list[tuple[float, list[str]]] = []
    for slug, info in coverage.items():
        harnesses = info["harnesses"]
        harness_list = ", ".join(harnesses) if harnesses else "-"
        avg = info["avg_total"]
        cells = [
            slug,
            harness_list,
            str(info["harness_count"]),
            str(info["runs"]),
            _fmt(avg if isinstance(avg, float) else None),
        ]
        sort_key = float(avg) if isinstance(avg, float) else -1.0
        rows.append((sort_key, cells))

    rows.sort(key=lambda t: t[0], reverse=True)
    for _, cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build_precomputed_rollup(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Full deterministic rollup injected into the meta-analysis prompt."""
    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    if not reports:
        return (
            "## Precomputed rollup\n\n"
            "*(no reports parsed — meta-analysis cannot rank models)*\n"
        )

    parts = [
        "## Precomputed rollup",
        "",
        "Harness-computed from parsed ``report.md`` files. **Section 2–4 numeric "
        "tables in meta-analysis.md MUST match these values.** Use individual "
        "reports only for citations and narrative.",
        "",
        build_model_coverage_table(reports).rstrip(),
        "",
        build_statistical_summary(reports_dir, source_dirs=source_dirs).rstrip(),
    ]
    return "\n".join(parts) + "\n"


def validate_meta_analysis_coverage(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
) -> list[str]:
    """Compare section-2 harness counts in meta-analysis.md to the rollup."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    expected = model_harness_coverage(reports)
    if not expected or not meta_path.is_file():
        return []

    text = meta_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"###\s*2\.\s*Best model overall(.*?)(?=\n###\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return ["section 2 (Best model overall) not found in meta-analysis.md"]

    section = section_match.group(1)
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^\|]+?)\s*\|\s*(\d+)\s*\|",
        re.MULTILINE,
    )
    errors: list[str] = []
    for match in row_re.finditer(section):
        slug = match.group(1).strip()
        reported = int(match.group(2))
        exp = expected.get(slug)
        if exp is None:
            continue
        exp_count = int(exp["harness_count"])
        if reported != exp_count:
            harnesses = ", ".join(exp["harnesses"])  # type: ignore[arg-type]
            errors.append(
                f"{slug}: meta-analysis reports {reported} harnesses but "
                f"rollup has {exp_count} ({harnesses})"
            )
    return errors


def build_statistical_summary(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Regex-derived harness / model / dimension rollups.

    This is **input** for the AI meta-analyst, not the final analysis. The
    LLM uses it as pre-aggregated context so it doesn't have to redo the
    arithmetic — but the LLM is still expected to read individual reports
    to find evidence behind the numbers.
    """
    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    if not reports:
        return "## Statistical summary\n\n*(no reports parsed)*\n"

    dim_labels = _dimension_labels(reports)

    lines: list[str] = ["## Statistical summary", ""]
    parsed_count = sum(1 for r in reports if r.total is not None)
    lines.append(
        f"Parsed `{parsed_count}` of `{len(reports)}` reports with a total score "
        f"(reports missing a total are excluded from averages but kept in counts)."
    )
    lines.append(
        "*This block is auto-computed via regex; treat it as a numeric "
        "starting point. The AI meta-analysis below interprets it.*"
    )
    lines.append("")

    sections = [
        _harness_section(reports, dim_labels),
        _cross_harness_model_section(reports, dim_labels),
        _dimension_breakdown_section(reports, dim_labels),
        _normalized_scores_section(reports, dim_labels),
    ]
    for section in sections:
        if section:
            lines.extend(section)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
