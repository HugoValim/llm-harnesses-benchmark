"""Statistical normalization for audit reports.

Consumes typed :class:`~benchmark.audit_report.ParsedReport` values. Produces
harness comparison, cross-harness model comparison, dimension breakdown, and
leader-relative normalized scores. These are auto-computed inputs for the AI
meta-analyst — not the final analysis.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean, median, stdev

from benchmark.audit_report import (
    NUM_DIMENSIONS,
    TIERS,
    ParsedReport,
    _collect_reports,
    _dimension_labels,
    _fmt,
)
from benchmark.result_layout import (
    BENCHMARK_CONTEST_HARNESSES,
    CURSOR_AGENT_PREFIX,
)
from benchmark.util import load_json, migrate_to_v2

# Model slug substrings that identify benchmark leader runs (substring match,
# case-insensitive), e.g. ``codex-gpt_5_5`` → ``gpt_5_5``, ``opencode-claude_opus_4_7``.
LEADER_MODEL_SLUG_SUBSTRINGS: tuple[str, ...] = ("gpt_5_5", "claude_opus_4_7")

_NORMALIZED_PCT_CAP = 150.0


def _display_slug(slug: str, display_slug_map: dict[str, str] | None) -> str:
    """Map canonical slug to human-facing slug when a display map is provided."""
    if display_slug_map is None:
        return slug
    return display_slug_map.get(slug, slug)


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
    *,
    display_slug_map: dict[str, str] | None = None,
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
        harnesses = _contest_harnesses_label(subset)
        lines.append(
            "| "
            + " | ".join(
                [
                    _display_slug(slug, display_slug_map),
                    str(len(subset)),
                    harnesses,
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
        harnesses = _contest_harnesses_label(subset)
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
            _display_slug(slug, display_slug_map),
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


def _is_benchmark_harness(harness: str) -> bool:
    return harness in BENCHMARK_CONTEST_HARNESSES


def _benchmark_reports(reports: list[ParsedReport]) -> list[ParsedReport]:
    return [r for r in reports if _is_benchmark_harness(r.harness)]


def _cursor_agent_reports(reports: list[ParsedReport]) -> list[ParsedReport]:
    return [r for r in reports if r.harness == CURSOR_AGENT_PREFIX]


def _contest_harnesses_label(reports: list[ParsedReport]) -> str:
    harnesses = sorted(
        {r.harness for r in reports if _is_benchmark_harness(r.harness)}
    )
    return ", ".join(harnesses) if harnesses else "-"


def _contest_harnesses_in_data(reports: list[ParsedReport]) -> list[str]:
    present = {r.harness for r in reports if _is_benchmark_harness(r.harness)}
    return sorted(present)


def _cross_harness_cohort_slugs(reports: list[ParsedReport]) -> frozenset[str]:
    """Model slugs audited under every contest harness present in ``reports``."""
    by_harness: dict[str, set[str]] = {}
    for r in reports:
        if not _is_benchmark_harness(r.harness):
            continue
        if r.model_slug and r.total is not None:
            by_harness.setdefault(r.harness, set()).add(r.model_slug)
    if not by_harness:
        return frozenset()
    cohort = set.intersection(*by_harness.values())
    return frozenset(cohort)


def _ranked_run_reports(reports: list[ParsedReport]) -> list[ParsedReport]:
    """Contest and cursor-agent reports with parseable totals, sorted by total desc."""
    eligible = [
        r
        for r in reports
        if r.total is not None
        and (
            _is_benchmark_harness(r.harness)
            or r.harness == CURSOR_AGENT_PREFIX
        )
    ]
    return sorted(eligible, key=lambda r: float(r.total), reverse=True)  # type: ignore[arg-type]


def _avg(values: list[float]) -> float | None:
    return mean(values) if values else None


_OLLAMA_CLOUD_SLUG_SUFFIX = "_ollama_cloud"
_CONTEST_HARNESS_COLUMN_ORDER: tuple[str, ...] = ("claude", "codex", "opencode")


def _is_ollama_cloud_slug(model_slug: str) -> bool:
    """Return True when ``model_slug`` is an Ollama Cloud open-source target."""
    return model_slug.endswith(_OLLAMA_CLOUD_SLUG_SUFFIX)


def _cell_avg_total(
    reports: list[ParsedReport],
    harness: str,
    slug: str,
) -> float | None:
    """Mean total for one ``(harness, model_slug)`` cell across auditors."""
    totals = [
        float(r.total)
        for r in reports
        if r.harness == harness and r.model_slug == slug and r.total is not None
    ]
    return mean(totals) if totals else None


def _tier_from_total(total: float) -> str:
    """Map a total score to rubric tier bands."""
    if total >= 81:
        return "A"
    if total >= 61:
        return "B"
    if total >= 41:
        return "C"
    return "D"


def _ollama_ranking_rows(
    reports: list[ParsedReport],
) -> list[dict[str, object]]:
    """Ranked Ollama Cloud models by cross-contest-harness mean total."""
    slugs = sorted(
        {
            r.model_slug
            for r in reports
            if r.model_slug and _is_ollama_cloud_slug(r.model_slug)
        }
    )
    rows: list[dict[str, object]] = []
    for slug in slugs:
        cell_avgs: dict[str, float] = {}
        for harness in _CONTEST_HARNESS_COLUMN_ORDER:
            cell_avg = _cell_avg_total(reports, harness, slug)
            if cell_avg is not None:
                cell_avgs[harness] = cell_avg
        if len(cell_avgs) < 2:
            continue
        values = list(cell_avgs.values())
        avg_total = mean(values)
        std = stdev(values) if len(values) >= 2 else None
        rows.append(
            {
                "slug": slug,
                "n_harnesses": len(cell_avgs),
                "avg_total": avg_total,
                "std_dev": std,
                "tier": _tier_from_total(avg_total),
                "cell_avgs": cell_avgs,
            }
        )

    def _sort_key(row: dict[str, object]) -> tuple[float, float]:
        avg = float(row["avg_total"])
        std = row["std_dev"]
        std_key = float(std) if isinstance(std, (int, float)) else float("inf")
        return (-avg, std_key)

    rows.sort(key=_sort_key)
    return rows


def _harness_section(reports: list[ParsedReport], dim_labels: list[str]) -> list[str]:
    """Per-harness rollup for the opencode/codex/claude contest only."""
    harnesses = _contest_harnesses_in_data(reports)
    if not harnesses:
        return []

    cohort = _cross_harness_cohort_slugs(reports)

    header = ["Harness", "Runs", "Avg Total"]
    header.extend(f"Tier {t}" for t in TIERS)
    header.extend(f"D{i}" for i in range(1, NUM_DIMENSIONS + 1))

    lines = [
        "## Harness comparison",
        "",
        "One row per **contest** harness (opencode, codex, claude). Cursor-agent",
        "runs are excluded — see **Cursor agent models**. Averages are taken",
        "only over the **cross-harness cohort**: model slugs audited under every",
        "contest harness present in the data (single-harness-only models such as",
        "leader anchors are excluded). `Tier X` columns count how many cohort runs",
        "landed in that tier.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]

    for harness in harnesses:
        subset = [
            r
            for r in reports
            if r.harness == harness and r.model_slug in cohort
        ]
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
            if r.harness == harness
            and r.model_slug in cohort
            and r.total is not None
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
    *,
    display_slug_map: dict[str, str] | None = None,
) -> list[str]:
    """For each model slug audited under >=2 harnesses, show scores side by side."""
    by_model: dict[str, list[ParsedReport]] = {}
    for r in reports:
        if r.model_slug:
            by_model.setdefault(r.model_slug, []).append(r)
    shared = {
        slug: rs
        for slug, rs in by_model.items()
        if len({r.harness for r in rs if _is_benchmark_harness(r.harness)}) >= 2
    }
    if not shared:
        return []

    lines = [
        "## Cross-harness model comparison",
        "",
        "Same model slug, different contest harness (opencode/codex/claude).",
        "Shows where harness choice moves the score for an otherwise identical",
        "target model. Cursor-agent runs are excluded.",
        "",
    ]

    header = ["Model slug", "Harness", "Total", "Tier"]
    header.extend(f"D{i}" for i in range(1, NUM_DIMENSIONS + 1))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for slug in sorted(shared):
        slug_reports = sorted(
            (r for r in shared[slug] if _is_benchmark_harness(r.harness)),
            key=lambda r: r.harness,
        )
        for r in slug_reports:
            row = [
                _display_slug(slug, display_slug_map),
                r.harness,
                _fmt(r.total),
                r.tier or "-",
            ]
            for i in range(1, NUM_DIMENSIONS + 1):
                row.append(_fmt(r.dim_score(i)))
            lines.append("| " + " | ".join(row) + " |")

    return lines


def _dimension_breakdown_section(
    reports: list[ParsedReport],
    dim_labels: list[str],
) -> list[str]:
    """Per-dimension average by contest harness (cursor excluded)."""
    harnesses = _contest_harnesses_in_data(reports)
    contest = _benchmark_reports(reports)
    if not harnesses:
        return []

    lines = [
        "## Dimension breakdown",
        "",
        "Average score per dimension, overall and per contest harness. Cursor-agent",
        "runs are excluded from **All avg** and per-harness columns.",
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
            float(r.dim_score(i))
            for r in contest
            if r.dim_score(i) is not None
        ]
        row = [f"D{i}. {label}", _fmt(max_score), _fmt(_avg(all_values))]
        for harness in harnesses:
            subset_values = [
                float(r.dim_score(i))
                for r in contest
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

    ``harnesses`` / ``harness_count`` count contest harnesses only (opencode,
    codex, claude). ``cursor_runs`` and ``cursor_avg_total`` cover Cursor-agent
    runs for the same slug. ``avg_total`` averages all runs with a parseable total.
    """
    by_model: dict[str, list[ParsedReport]] = {}
    for r in reports:
        if r.model_slug:
            by_model.setdefault(r.model_slug, []).append(r)

    out: dict[str, dict[str, object]] = {}
    for slug, subset in by_model.items():
        harnesses = sorted(
            {r.harness for r in subset if _is_benchmark_harness(r.harness)}
        )
        cursor_subset = [r for r in subset if r.harness == CURSOR_AGENT_PREFIX]
        cursor_totals = [
            float(r.total) for r in cursor_subset if r.total is not None
        ]
        totals = [float(r.total) for r in subset if r.total is not None]
        out[slug] = {
            "harnesses": harnesses,
            "runs": len(subset),
            "harness_count": len(harnesses),
            "cursor_runs": len(cursor_subset),
            "cursor_avg_total": mean(cursor_totals) if cursor_totals else None,
            "avg_total": mean(totals) if totals else None,
        }
    return out


def build_model_coverage_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: model slug → harness list → run count → avg total."""
    coverage = model_harness_coverage(reports)
    if not coverage:
        return "## Model coverage\n\n*(no reports parsed)*\n"

    lines = [
        "## Model coverage",
        "",
        "Per-model summary across contest harnesses (opencode, codex, claude). "
        "``harness_count`` is the number of distinct contest harnesses with a "
        "parseable total for that model slug. Cursor-only slugs have harness "
        "count `0` — see **Cursor agent models**. Used for appendix context; "
        "section 2 uses **All runs ranking**.",
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
            _display_slug(slug, display_slug_map),
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


def build_cursor_agent_models_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table of Cursor-agent model runs (excluded from harness contest)."""
    cursor_reports = _cursor_agent_reports(reports)
    if not cursor_reports:
        return "## Cursor agent models\n\n*(no cursor-agent reports parsed)*\n"

    by_slug: dict[str, list[ParsedReport]] = {}
    for r in cursor_reports:
        if r.model_slug:
            by_slug.setdefault(r.model_slug, []).append(r)

    lines = [
        "## Cursor agent models",
        "",
        "Runs under the ``cursor-`` path prefix (Cursor Agent CLI). **Excluded**",
        "from harness comparison and cross-harness pairings. Copy into",
        "meta-analysis appendix; do not rank as a harness.",
        "",
        "| Model slug | Runs | Avg total |",
        "|---|---:|---:|",
    ]
    rows: list[tuple[float, list[str]]] = []
    for slug, subset in by_slug.items():
        totals = [float(r.total) for r in subset if r.total is not None]
        avg = mean(totals) if totals else None
        cells = [
            _display_slug(slug, display_slug_map),
            str(len(subset)),
            _fmt(avg),
        ]
        sort_key = float(avg) if avg is not None else -1.0
        rows.append((sort_key, cells))
    rows.sort(key=lambda t: t[0], reverse=True)
    for _, cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def expected_section2_run_rows(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> list[tuple[str, str, float]]:
    """Return ``(harness, model_slug, total)`` tuples for section 2 validation."""
    return [
        (
            r.harness,
            _display_slug(r.model_slug or "-", display_slug_map),
            float(r.total),
        )
        for r in _ranked_run_reports(reports)
    ]


def build_all_runs_ranking_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: one row per contest or cursor run, sorted by total desc."""
    ranked = _ranked_run_reports(reports)
    if not ranked:
        return (
            "## All runs ranking\n\n"
            "*(no contest or cursor runs with parseable totals)*\n"
        )

    lines = [
        "## All runs ranking",
        "",
        "Authoritative rows for section 2. One row per contest or cursor-agent",
        "run with a parseable total, sorted by total descending.",
        "",
        "| Rank | Harness | Model slug | Total | Tier |",
        "|---:|---|---|---:|---|",
    ]
    for rank, report in enumerate(ranked, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    report.harness,
                    _display_slug(report.model_slug or "-", display_slug_map),
                    _fmt(float(report.total)),
                    report.tier or "-",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def expected_section2a_ollama_rows(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> list[tuple[str, int, float, float | None, str]]:
    """Return section-2a tuples: ``(slug, n_harnesses, avg, std_dev, tier)``."""
    out: list[tuple[str, int, float, float | None, str]] = []
    for row in _ollama_ranking_rows(reports):
        std = row["std_dev"]
        slug = str(row["slug"])
        out.append(
            (
                _display_slug(slug, display_slug_map),
                int(row["n_harnesses"]),  # type: ignore[arg-type]
                float(row["avg_total"]),  # type: ignore[arg-type]
                float(std) if isinstance(std, (int, float)) else None,
                str(row["tier"]),
            )
        )
    return out


def build_ollama_model_ranking_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: Ollama Cloud models ranked by cross-harness mean total."""
    ranked = _ollama_ranking_rows(reports)
    if not ranked:
        return (
            "## Ollama model ranking\n\n"
            "*(no Ollama Cloud models with >=2 contest-harness runs)*\n"
        )

    harness_headers = [
        harness.capitalize() for harness in _CONTEST_HARNESS_COLUMN_ORDER
    ]
    header = [
        "Rank",
        "Model slug",
        "N harnesses",
        "Avg total",
        "Std dev",
        "Tier",
        *harness_headers,
    ]
    lines = [
        "## Ollama model ranking",
        "",
        "Authoritative rows for section 2a. Open-source Ollama Cloud model slugs",
        "(``*_ollama_cloud``) ranked by mean total across contest harnesses",
        "(opencode, codex, claude). Per-harness columns are auditor-averaged cell",
        "totals. Models with fewer than two contest-harness runs are excluded.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for rank, row in enumerate(ranked, start=1):
        cell_avgs = row["cell_avgs"]
        assert isinstance(cell_avgs, dict)
        cells = [
            str(rank),
            _display_slug(str(row["slug"]), display_slug_map),
            str(row["n_harnesses"]),
            _fmt(float(row["avg_total"])),  # type: ignore[arg-type]
            _fmt(float(row["std_dev"])) if row["std_dev"] is not None else "-",
            str(row["tier"]),
        ]
        for harness in _CONTEST_HARNESS_COLUMN_ORDER:
            avg = cell_avgs.get(harness)
            cells.append(_fmt(avg) if avg is not None else "-")
        lines.append("| " + " | ".join(cells) + " |")

    best = ranked[0]
    best_slug = _display_slug(str(best["slug"]), display_slug_map)
    lines.extend(
        [
            "",
            f"**Best open-source model**: `{best_slug}` "
            f"({_fmt(float(best['avg_total']))}/100 across "  # type: ignore[arg-type]
            f"{best['n_harnesses']} harnesses).",
        ]
    )
    return "\n".join(lines) + "\n"


def _generation_metrics_path(
    report: ParsedReport, source_dirs: list[Path] | None
) -> Path | None:
    """Resolve ``generation-metrics.json`` for a parsed audit report."""
    if not source_dirs:
        return None
    for root in source_dirs:
        for candidate in (
            root / report.auditor / report.target / "generation-metrics.json",
            root / report.target / "generation-metrics.json",
        ):
            if candidate.is_file():
                return candidate
    return None


def _version_label(
    metrics: dict[str, object] | None,
    result_row: dict[str, object] | None,
) -> str:
    """Human-readable CLI version label for rollup tables."""
    version = None
    shim = None
    if metrics:
        version = metrics.get("harness_cli_version")
        shim = metrics.get("command_shim_version")
    if version is None and result_row:
        version = result_row.get("harness_cli_version")
        shim = result_row.get("command_shim_version")
    if version and shim:
        return f"{version} (shim: {shim})"
    if version:
        return str(version)
    return "unknown"


def _load_cli_version_for_report(
    report: ParsedReport,
    *,
    source_dirs: list[Path] | None,
) -> str:
    """Resolve harness CLI version for one audit target."""
    metrics_path = _generation_metrics_path(report, source_dirs)
    metrics: dict[str, object] | None = None
    result_row: dict[str, object] | None = None
    if metrics_path is not None:
        try:
            metrics = load_json(metrics_path)
        except Exception:
            metrics = None
    if metrics:
        bench_path = metrics.get("benchmark_result_path")
        if isinstance(bench_path, str):
            bench_file = Path(bench_path)
            if bench_file.is_file():
                try:
                    result_row = migrate_to_v2(load_json(bench_file))
                except Exception:
                    result_row = None
    return _version_label(metrics, result_row)


def collect_harness_cli_versions(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Per harness → version label → sorted target paths (``auditor/target``)."""
    by_harness: dict[str, dict[str, list[str]]] = {}
    for report in reports:
        if not report.harness or report.harness == "unknown":
            continue
        label = _load_cli_version_for_report(report, source_dirs=source_dirs)
        target_path = f"{report.auditor}/{report.target}"
        harness_bucket = by_harness.setdefault(report.harness, {})
        harness_bucket.setdefault(label, []).append(target_path)
    for harness in by_harness:
        for label in by_harness[harness]:
            by_harness[harness][label] = sorted(by_harness[harness][label])
    return by_harness


def build_harness_versions_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Markdown table of benchmark agent CLI versions per harness."""
    coverage = collect_harness_cli_versions(reports, source_dirs=source_dirs)
    if not coverage:
        return "## Harness CLI versions\n\n*(no harness versions resolved)*\n"

    lines = [
        "## Harness CLI versions",
        "",
        "Benchmark agent CLI builds used when generating each target. "
        "**Section 11 appendix must copy this table exactly.** When a harness "
        "shows multiple versions, treat as ``mixed-harness-version`` for "
        "cross-harness rankings (see meta-analysis guardrails).",
        "",
        "| Harness | Version(s) | Targets | Notes |",
        "|---|---|---|---|",
    ]
    for harness in sorted(coverage):
        version_map = coverage[harness]
        versions = sorted(version_map)
        targets: list[str] = []
        for v in versions:
            targets.extend(version_map[v])
        version_cell = "; ".join(versions)
        notes = ""
        if harness == CURSOR_AGENT_PREFIX:
            notes = "cursor-agent (excluded from harness contest)"
        elif len(versions) > 1:
            notes = "mixed-version"
        lines.append(
            "| "
            + " | ".join(
                [
                    harness,
                    version_cell,
                    str(len(targets)),
                    notes or "-",
                ]
            )
            + " |"
        )
        if len(versions) > 1:
            for v in versions:
                for t in version_map[v]:
                    lines.append(f"- `{t}` → {v}")
    return "\n".join(lines) + "\n"


def _top_contest_run(reports: list[ParsedReport]) -> ParsedReport | None:
    """Rank-1 contest-harness run by total (peak Phase-1 score on the brief)."""
    contest_runs = [
        r
        for r in _ranked_run_reports(reports)
        if _is_benchmark_harness(r.harness)
    ]
    return contest_runs[0] if contest_runs else None


def _harness_contest_stats(
    reports: list[ParsedReport], harness: str
) -> dict[str, float | int | None]:
    """Stats for one contest harness over the cross-harness cohort."""
    cohort = _cross_harness_cohort_slugs(reports)
    subset = [
        r
        for r in reports
        if r.harness == harness
        and r.model_slug in cohort
        and r.total is not None
    ]
    totals = [float(r.total) for r in subset]
    std: float | None = None
    if len(totals) >= 2:
        std = stdev(totals)
    return {
        "n": len(subset),
        "avg": _avg(totals),
        "median": median(totals) if totals else None,
        "std_dev": std,
    }


def _contest_harness_rankings(
    reports: list[ParsedReport],
) -> list[tuple[str, dict[str, float | int | None]]]:
    """Contest harnesses sorted by cross-harness-cohort avg total descending."""
    rows: list[tuple[str, dict[str, float | int | None]]] = []
    for harness in _contest_harnesses_in_data(reports):
        stats = _harness_contest_stats(reports, harness)
        if stats["avg"] is not None:
            rows.append((harness, stats))
    rows.sort(key=lambda item: float(item[1]["avg"]), reverse=True)  # type: ignore[arg-type]
    return rows


def _single_harness_run_note(
    reports: list[ParsedReport], model_slug: str
) -> str:
    """Short clause when a model slug appears under only one contest harness."""
    harnesses = sorted(
        {
            r.harness
            for r in reports
            if r.model_slug == model_slug
            and _is_benchmark_harness(r.harness)
            and r.total is not None
        }
    )
    if len(harnesses) > 1:
        return ""
    if _is_leader_slug(model_slug):
        return "single-harness anchor — not on the shared Ollama grid"
    return "single-harness run — not on the shared Ollama grid"


def _lowest_dimension_candidate(
    reports: list[ParsedReport],
) -> dict[str, object] | None:
    """Dimension with the lowest contest-cohort all-harness average."""
    harnesses = _contest_harnesses_in_data(reports)
    contest = _benchmark_reports(reports)
    if not harnesses or not contest:
        return None

    dim_labels = _dimension_labels(reports)
    candidate: dict[str, object] | None = None
    lowest_all_avg = float("inf")

    for i in range(1, NUM_DIMENSIONS + 1):
        all_values = [
            float(r.dim_score(i))
            for r in contest
            if r.dim_score(i) is not None
        ]
        all_avg = _avg(all_values)
        if all_avg is None or all_avg >= lowest_all_avg:
            continue
        lowest_all_avg = all_avg
        per_harness: dict[str, float | None] = {}
        for harness in harnesses:
            subset_values = [
                float(r.dim_score(i))
                for r in contest
                if r.harness == harness and r.dim_score(i) is not None
            ]
            per_harness[harness] = _avg(subset_values)
        label = dim_labels[i - 1] if i - 1 < len(dim_labels) else f"D{i}"
        candidate = {
            "index": i,
            "label": label,
            "max": _max_for_dimension(reports, i),
            "all_avg": all_avg,
            "per_harness": per_harness,
        }
    return candidate


def _mixed_version_contest_harnesses(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> list[str]:
    """Contest harnesses whose CLI version labels differ across targets."""
    coverage = collect_harness_cli_versions(reports, source_dirs=source_dirs)
    mixed: list[str] = []
    for harness, version_map in coverage.items():
        if harness == CURSOR_AGENT_PREFIX:
            continue
        if not _is_benchmark_harness(harness):
            continue
        if len(version_map) > 1:
            mixed.append(harness)
    return sorted(mixed)


def executive_summary_expectations(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> dict[str, object]:
    """Key verdict fields the executive summary must contain."""
    expectations: dict[str, object] = {}

    harness_rows = _contest_harness_rankings(reports)
    if harness_rows:
        best_harness, best_stats = harness_rows[0]
        expectations["best_harness"] = best_harness
        expectations["best_harness_avg"] = best_stats["avg"]

    top_run = _top_contest_run(reports)
    if top_run is not None and top_run.total is not None:
        expectations["top_model_slug"] = _display_slug(
            top_run.model_slug or "-", display_slug_map
        )
        expectations["top_model_total"] = float(top_run.total)
        expectations["top_model_harness"] = top_run.harness

    ollama_rows = _ollama_ranking_rows(reports)
    if ollama_rows:
        best = ollama_rows[0]
        expectations["best_ollama_slug"] = _display_slug(
            str(best["slug"]), display_slug_map
        )
        expectations["best_ollama_avg"] = best["avg_total"]
        expectations["best_ollama_n_harnesses"] = best["n_harnesses"]

    expectations["mixed_version_harnesses"] = _mixed_version_contest_harnesses(
        reports, source_dirs=source_dirs
    )
    return expectations


def build_executive_summary_skeleton(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Deterministic verdict bullets for meta-analysis section 1."""
    lines = [
        "## Executive summary skeleton",
        "",
        "Copy these verdict bullets into section 1 **verbatim** (numbers and slugs).",
        "Add at most three narrative bullets after them (harness pattern, universal",
        "blind spot, calibration). No ``report.md:line`` citations in section 1.",
        "",
    ]

    harness_rows = _contest_harness_rankings(reports)
    if harness_rows:
        best_harness, best_stats = harness_rows[0]
        avg = float(best_stats["avg"])  # type: ignore[arg-type]
        n = int(best_stats["n"])  # type: ignore[arg-type]
        std = best_stats["std_dev"]
        std_clause = f", std dev {_fmt(float(std))}" if std is not None else ""
        runners = [
            f"{name} {_fmt(float(stats['avg']))}"  # type: ignore[arg-type]
            for name, stats in harness_rows[1:3]
            if stats["avg"] is not None
        ]
        tie_note = ""
        if len(harness_rows) >= 2:
            second_avg = float(harness_rows[1][1]["avg"])  # type: ignore[arg-type]
            second_n = int(harness_rows[1][1]["n"])  # type: ignore[arg-type]
            if abs(avg - second_avg) <= 3 and (n <= 8 or second_n <= 8):
                tie_note = " *Statistical tie* (margin ≤3 on N≤8)."
        runner_clause = (
            f" Runners-up: {', '.join(runners)}." if runners else ""
        )
        lines.append(
            f"- **Best harness overall**: `{best_harness}` — "
            f"{_fmt(avg)}/100 avg (N={n}{std_clause})."
            f"{runner_clause}{tie_note}"
        )
    else:
        lines.append(
            "- **Best harness overall**: insufficient cross-model coverage — "
            "harness verdict suppressed."
        )

    top_run = _top_contest_run(reports)
    if top_run is not None and top_run.total is not None:
        note = _single_harness_run_note(reports, top_run.model_slug or "")
        note_clause = f" ({note})" if note else ""
        display_slug = _display_slug(top_run.model_slug or "-", display_slug_map)
        lines.append(
            f"- **Best model overall**: `{display_slug}` — "
            f"{_fmt(float(top_run.total))}/100 under `{top_run.harness}` "
            f"(top contest-harness run{note_clause})."
        )
    else:
        lines.append(
            "- **Best model overall**: no contest-harness runs with parseable totals."
        )

    ollama_rows = _ollama_ranking_rows(reports)
    if ollama_rows:
        best = ollama_rows[0]
        avg_total = float(best["avg_total"])  # type: ignore[arg-type]
        n_harnesses = int(best["n_harnesses"])  # type: ignore[arg-type]
        std = best["std_dev"]
        std_clause = f" (std dev {_fmt(float(std))})" if std is not None else ""
        lines.append(
            f"- **Best open-source model overall**: "
            f"`{_display_slug(str(best['slug']), display_slug_map)}` — "
            f"{_fmt(avg_total)}/100 cross-harness avg across {n_harnesses} "
            f"contest harnesses{std_clause}; best on the shared Ollama Cloud grid."
        )
    else:
        lines.append(
            "- **Best open-source model overall**: no open-source model has "
            "cross-harness coverage — open-source verdict suppressed."
        )

    cursor_reports = _cursor_agent_reports(reports)
    if cursor_reports:
        cursor_totals = [
            float(r.total) for r in cursor_reports if r.total is not None
        ]
        cursor_avg = mean(cursor_totals) if cursor_totals else None
        lines.append(
            f"- **Cursor agent runs**: N={len(cursor_reports)}, "
            f"avg {_fmt(cursor_avg)} — model-only benchmarks; excluded from "
            "harness contest."
        )

    mixed = _mixed_version_contest_harnesses(reports, source_dirs=source_dirs)
    if mixed:
        harness_list = ", ".join(f"`{h}`" for h in mixed)
        lines.append(
            f"- **Harness CLI versions**: cohort spans multiple CLI builds for "
            f"{harness_list}; cross-harness rankings for those harnesses are "
            "caveated (see appendix)."
        )

    blind_spot = _lowest_dimension_candidate(reports)
    if blind_spot is not None:
        per_harness = blind_spot["per_harness"]
        assert isinstance(per_harness, dict)
        dim_index = int(blind_spot["index"])  # type: ignore[arg-type]
        dim_label = str(blind_spot["label"])
        dim_max = blind_spot["max"]
        all_avg = float(blind_spot["all_avg"])  # type: ignore[arg-type]
        harness_parts = " / ".join(
            f"{h} {_fmt(v) if v is not None else 'n/a'}"
            for h, v in sorted(per_harness.items())
        )
        max_display = dim_max if dim_max is not None else "?"
        lines.append(
            f"- **Universal blind spot candidate**: D{dim_index} {dim_label} — "
            f"all avg {_fmt(all_avg)}/{max_display}; {harness_parts}."
        )

    return "\n".join(lines) + "\n"


def build_precomputed_rollup(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
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
        "Harness-computed from parsed ``report.md`` files. **Section 1 verdict "
        "bullets, section 2, 2a, 3, 4 numeric tables, and the harness CLI "
        "versions table in meta-analysis.md MUST match these values.** Use "
        "individual reports only for citations and narrative.",
        "",
        build_executive_summary_skeleton(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_model_coverage_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_all_runs_ranking_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_ollama_model_ranking_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_cursor_agent_models_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_harness_versions_table(reports, source_dirs=source_dirs).rstrip(),
        "",
        build_statistical_summary(
            reports_dir,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
    ]
    return "\n".join(parts) + "\n"


def validate_meta_analysis_coverage(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> list[str]:
    """Compare section-2 per-run rows in meta-analysis.md to the rollup."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    expected = expected_section2_run_rows(
        reports, display_slug_map=display_slug_map
    )
    if not expected or not meta_path.is_file():
        return []

    text = meta_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"#{2,3}\s*2\.\s*Best model overall(.*?)(?=\n#{2,3}\s+2a\.|\n#{2,3}\s+\d+\.|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return ["section 2 (Best model overall) not found in meta-analysis.md"]

    section = section_match.group(1)
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([\d.]+)\s*\|",
        re.MULTILINE,
    )
    reported: list[tuple[str, str, float]] = []
    for match in row_re.finditer(section):
        harness = match.group(1).strip()
        slug = match.group(2).strip()
        total = float(match.group(3))
        reported.append((harness, slug, total))

    errors: list[str] = []
    if len(reported) != len(expected):
        errors.append(
            f"section 2 has {len(reported)} run rows but rollup has {len(expected)}"
        )

    for index, (exp_row, got_row) in enumerate(
        zip(expected, reported), start=1
    ):
        exp_harness, exp_slug, exp_total = exp_row
        got_harness, got_slug, got_total = got_row
        if (
            exp_harness != got_harness
            or exp_slug != got_slug
            or exp_total != got_total
        ):
            errors.append(
                f"row {index}: expected "
                f"{exp_harness}/{exp_slug}={exp_total} but meta-analysis has "
                f"{got_harness}/{got_slug}={got_total}"
            )

    if len(reported) > len(expected):
        for extra in reported[len(expected) :]:
            errors.append(
                f"unexpected extra row: {extra[0]}/{extra[1]}={extra[2]}"
            )

    return errors


def validate_meta_analysis_ollama_ranking(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> list[str]:
    """Compare section-2a Ollama ranking rows in meta-analysis.md to the rollup."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    expected = expected_section2a_ollama_rows(
        reports, display_slug_map=display_slug_map
    )
    if not expected or not meta_path.is_file():
        return []

    text = meta_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"#{2,3}\s*2a\.\s*Open-source \(Ollama\) model ranking"
        r"(.*?)(?=\n#{2,3}\s+\d+\.|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return [
            "section 2a (Open-source Ollama model ranking) not found in meta-analysis.md"
        ]

    section = section_match.group(1)
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^\|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.-]+)\s*\|\s*([^\|]+?)\s*\|",
        re.MULTILINE,
    )
    reported: list[tuple[str, int, float, float | None, str]] = []
    for match in row_re.finditer(section):
        slug = match.group(1).strip()
        n_harnesses = int(match.group(2))
        avg_total = float(match.group(3))
        std_raw = match.group(4).strip()
        std_dev = None if std_raw == "-" else float(std_raw)
        tier = match.group(5).strip()
        reported.append((slug, n_harnesses, avg_total, std_dev, tier))

    errors: list[str] = []
    if len(reported) != len(expected):
        errors.append(
            f"section 2a has {len(reported)} Ollama rows but rollup has {len(expected)}"
        )

    for index, (exp_row, got_row) in enumerate(zip(expected, reported), start=1):
        exp_slug, exp_n, exp_avg, exp_std, exp_tier = exp_row
        got_slug, got_n, got_avg, got_std, got_tier = got_row
        if (
            exp_slug != got_slug
            or exp_n != got_n
            or exp_avg != got_avg
            or exp_std != got_std
            or exp_tier != got_tier
        ):
            errors.append(
                f"section 2a row {index}: expected "
                f"{exp_slug} n={exp_n} avg={exp_avg} std={exp_std} tier={exp_tier} "
                f"but meta-analysis has "
                f"{got_slug} n={got_n} avg={got_avg} std={got_std} tier={got_tier}"
            )

    if len(reported) > len(expected):
        for extra in reported[len(expected) :]:
            errors.append(f"section 2a unexpected extra row: {extra[0]}")

    return errors


def validate_meta_analysis_executive_summary(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> list[str]:
    """Compare section-1 verdict bullets in meta-analysis.md to the skeleton."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    if not reports or not meta_path.is_file():
        return []

    expectations = executive_summary_expectations(
        reports,
        source_dirs=source_dirs,
        display_slug_map=display_slug_map,
    )
    text = meta_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"#{2,3}\s*1\.\s*Executive summary(.*?)(?=\n#{2,3}\s+\d+\.|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return ["section 1 (Executive summary) not found in meta-analysis.md"]

    section = section_match.group(1).strip()
    errors: list[str] = []

    if not re.search(r"^\s*-\s+\*\*", section, re.MULTILINE):
        errors.append(
            "section 1 is not a bullet list (expected markdown `- **Label**: …` bullets)"
        )

    if "report.md:" in section:
        errors.append("section 1 contains report.md citations (move to later sections)")

    best_harness = expectations.get("best_harness")
    best_harness_avg = expectations.get("best_harness_avg")
    if isinstance(best_harness, str) and isinstance(best_harness_avg, float):
        if best_harness not in section:
            errors.append(
                f"section 1 missing best harness slug {best_harness!r}"
            )
        avg_token = _fmt(best_harness_avg)
        if avg_token not in section:
            errors.append(
                f"section 1 missing best harness avg {avg_token} "
                f"for {best_harness!r}"
            )

    top_slug = expectations.get("top_model_slug")
    top_total = expectations.get("top_model_total")
    if isinstance(top_slug, str) and isinstance(top_total, float):
        if top_slug not in section:
            errors.append(
                f"section 1 missing best model overall slug {top_slug!r}"
            )
        total_token = _fmt(top_total)
        if total_token not in section:
            errors.append(
                f"section 1 missing best model overall total {total_token} "
                f"for {top_slug!r}"
            )

    ollama_slug = expectations.get("best_ollama_slug")
    ollama_avg = expectations.get("best_ollama_avg")
    if isinstance(ollama_slug, str) and isinstance(ollama_avg, float):
        if ollama_slug not in section:
            errors.append(
                f"section 1 missing best open-source model slug {ollama_slug!r}"
            )
        avg_token = _fmt(ollama_avg)
        if avg_token not in section:
            errors.append(
                f"section 1 missing best open-source avg {avg_token} "
                f"for {ollama_slug!r}"
            )

    return errors


def build_statistical_summary(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
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
        _cross_harness_model_section(
            reports, dim_labels, display_slug_map=display_slug_map
        ),
        _dimension_breakdown_section(reports, dim_labels),
        _normalized_scores_section(
            reports, dim_labels, display_slug_map=display_slug_map
        ),
    ]
    for section in sections:
        if section:
            lines.extend(section)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
