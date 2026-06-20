"""Statistical normalization for audit reports.

Consumes typed :class:`~benchmark.audit_report.ParsedReport` values. Produces
harness comparison, cross-harness model comparison, dimension breakdown, and
leader-relative normalized scores. These are auto-computed inputs for the AI
meta-analyst — not the final analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from benchmark.model_identity import cohort_slug
from benchmark.result_layout import (
    BENCHMARK_CONTEST_HARNESSES,
    CURSOR_AGENT_PREFIX,
)
from benchmark.util import load_json, migrate_to_v2

# Model slug substrings that identify benchmark leader runs (substring match,
# case-insensitive), e.g. ``codex-gpt_5_5`` → ``gpt_5_5``, ``opencode-claude_opus_4_7``.
LEADER_MODEL_SLUG_SUBSTRINGS: tuple[str, ...] = ("gpt_5_5", "claude_opus_4_7")

_NORMALIZED_PCT_CAP = 150.0
_SATURATION_FULL_MARKS_RATIO = 0.80
_BLIND_SPOT_MAX_AVG_RATIO = 0.70
_BLIND_SPOT_MAX_HARNESS_SPREAD = 1.0
_HARNESS_ATTRIBUTABLE_MIN_SPREAD = 2.0
_CLEAN_NEAR_MAX_RATIO = 0.75


@dataclass(frozen=True)
class AggregatedRunRankingRow:
    rank: int
    harness: str
    model_slug: str
    mean_total: float
    sample_n: int
    std_dev: float | None
    tier: str


@dataclass(frozen=True)
class ModelCoverageRow:
    model_slug: str
    harnesses: tuple[str, ...]
    harness_count: int
    runs: int
    cursor_runs: int
    cursor_avg_total: float | None
    avg_total: float | None


@dataclass(frozen=True)
class HarnessAverage:
    harness: str
    avg_total: float


@dataclass(frozen=True)
class TierCount:
    tier: str
    count: int


@dataclass(frozen=True)
class DimensionAverage:
    index: int
    label: str
    avg_score: float | None


@dataclass(frozen=True)
class HarnessComparisonRow:
    harness: str
    runs: int
    avg_total: float | None
    tier_counts: tuple[TierCount, ...]
    dimension_averages: tuple[DimensionAverage, ...]


@dataclass(frozen=True)
class HarnessComparisonResult:
    cohort_model_slugs: frozenset[str]
    rows: tuple[HarnessComparisonRow, ...]
    best_harnesses: tuple[str, ...]
    best_avg_total: float | None


@dataclass(frozen=True)
class HarnessRankingRow:
    rank: int
    harness: str
    sample_n: int
    avg_total: float
    median_total: float | None
    std_dev: float | None


@dataclass(frozen=True)
class TopModelExpectation:
    harness: str
    model_slug: str
    total: float
    note: str


@dataclass(frozen=True)
class BestOllamaExpectation:
    model_slug: str
    avg_total: float
    n_harnesses: int
    std_dev: float | None


@dataclass(frozen=True)
class CursorRunExpectation:
    runs: int
    avg_total: float | None


@dataclass(frozen=True)
class DimensionHarnessAverage:
    harness: str
    avg_score: float | None


@dataclass(frozen=True)
class DimensionBlindSpot:
    index: int
    label: str
    max_score: int | None
    all_avg: float
    harness_averages: tuple[DimensionHarnessAverage, ...]


@dataclass(frozen=True)
class DimensionSignalRow:
    index: int
    label: str
    max_score: int | None
    all_avg: float | None
    harness_averages: tuple[DimensionHarnessAverage, ...]
    full_marks_count: int
    scored_count: int
    full_marks_ratio: float | None
    harness_spread: float | None
    classification: str


@dataclass(frozen=True)
class ExecutiveSummaryExpectations:
    harness_rankings: tuple[HarnessRankingRow, ...]
    top_model: TopModelExpectation | None
    best_ollama: BestOllamaExpectation | None
    cursor_runs: CursorRunExpectation | None
    mixed_version_harnesses: tuple[str, ...]
    blind_spot: DimensionBlindSpot | None


@dataclass(frozen=True)
class OllamaModelRankingRow:
    rank: int
    model_slug: str
    n_harnesses: int
    avg_total: float
    std_dev: float | None
    tier: str
    harness_averages: tuple[HarnessAverage, ...]


def _display_slug(slug: str, display_slug_map: dict[str, str] | None) -> str:
    """Map canonical slug to human-facing slug when a display map is provided."""
    canonical = cohort_slug(slug)
    if display_slug_map is None:
        return canonical
    return display_slug_map.get(canonical, display_slug_map.get(slug, canonical))


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
            by_harness.setdefault(r.harness, set()).add(cohort_slug(r.model_slug))
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


def _aggregated_cell_stats(
    reports: list[ParsedReport],
    harness: str,
    slug: str,
) -> tuple[float | None, int, float | None]:
    """Mean total, sample count, and std dev for one ``(harness, model_slug)`` cell."""
    totals = [
        float(r.total)
        for r in reports
        if r.harness == harness and r.model_slug == slug and r.total is not None
    ]
    if not totals:
        return None, 0, None
    avg = mean(totals)
    std = stdev(totals) if len(totals) >= 2 else None
    return avg, len(totals), std


def _aggregated_contest_ranking_rows(
    reports: list[ParsedReport],
) -> list[tuple[str, str, float, int, float | None]]:
    """One row per ``(harness, model_slug)`` with mean total across replicates."""
    cells: set[tuple[str, str]] = set()
    for report in reports:
        if report.total is None or not report.model_slug:
            continue
        if not (
            _is_benchmark_harness(report.harness)
            or report.harness == CURSOR_AGENT_PREFIX
        ):
            continue
        cells.add((report.harness, report.model_slug))
    rows: list[tuple[str, str, float, int, float | None]] = []
    for harness, slug in cells:
        avg, sample_n, std = _aggregated_cell_stats(reports, harness, slug)
        if avg is not None:
            rows.append((harness, slug, avg, sample_n, std))
    rows.sort(key=lambda item: item[2], reverse=True)
    return rows


_CONTEST_HARNESS_COLUMN_ORDER: tuple[str, ...] = ("claude", "codex", "opencode")


def _is_ollama_cloud_slug(model_slug: str) -> bool:
    """Return True when ``model_slug`` is an Ollama Cloud open-source target."""
    return cohort_slug(model_slug) != model_slug


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


def _contest_cell_avg_total(
    reports: list[ParsedReport],
    harness: str,
    base_slug: str,
) -> float | None:
    """Mean total for one contest cell; supports legacy suffixed slugs."""
    avg = _cell_avg_total(reports, harness, base_slug)
    if avg is not None:
        return avg
    legacy_slug = f"{base_slug}_{harness}"
    return _cell_avg_total(reports, harness, legacy_slug)


def _default_ollama_cloud_registry_slugs() -> frozenset[str]:
    from benchmark.config import _normalize_registry_models, ollama_cloud_registry_slugs
    from benchmark.util import load_json

    models_path = Path(__file__).resolve().parents[2] / "config" / "models.json"
    config = load_json(models_path)
    models = _normalize_registry_models(config.get("models"))
    return ollama_cloud_registry_slugs(models)


def _ollama_ranking_base_slugs(
    reports: list[ParsedReport],
    ollama_slugs: frozenset[str],
) -> list[str]:
    bases = set(ollama_slugs)
    for report in reports:
        if report.model_slug and _is_ollama_cloud_slug(report.model_slug):
            bases.add(cohort_slug(report.model_slug))
    return sorted(bases)


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
    *,
    ollama_slugs: frozenset[str] | None = None,
) -> list[dict[str, object]]:
    """Ranked Ollama Cloud models by cross-contest-harness mean total."""
    if ollama_slugs is None:
        ollama_slugs = _default_ollama_cloud_registry_slugs()
    bases = _ollama_ranking_base_slugs(reports, ollama_slugs)
    rows: list[dict[str, object]] = []
    for base in bases:
        cell_avgs: dict[str, float] = {}
        for harness in _CONTEST_HARNESS_COLUMN_ORDER:
            cell_avg = _contest_cell_avg_total(reports, harness, base)
            if cell_avg is not None:
                cell_avgs[harness] = cell_avg
        if len(cell_avgs) < 2:
            continue
        values = list(cell_avgs.values())
        avg_total = mean(values)
        std = stdev(values) if len(values) >= 2 else None
        rows.append(
            {
                "slug": base,
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


def calculate_harness_comparison(
    reports: list[ParsedReport],
    dim_labels: list[str] | None = None,
) -> HarnessComparisonResult:
    """Return harness comparison rows before Markdown rendering.

    Example:
        result = calculate_harness_comparison(reports)
        best_harness = result.best_harnesses[0]
    """
    labels = dim_labels if dim_labels is not None else _dimension_labels(reports)
    cohort = _cross_harness_cohort_slugs(reports)
    rows = tuple(
        _harness_comparison_row(reports, harness, cohort, labels)
        for harness in _contest_harnesses_in_data(reports)
    )
    best_harnesses, best_avg = _best_harness_comparison(rows)
    return HarnessComparisonResult(cohort, rows, best_harnesses, best_avg)


def _harness_comparison_row(
    reports: list[ParsedReport],
    harness: str,
    cohort: frozenset[str],
    dim_labels: list[str],
) -> HarnessComparisonRow:
    subset = [
        r
        for r in reports
        if r.harness == harness and cohort_slug(r.model_slug) in cohort
    ]
    totals = [float(r.total) for r in subset if r.total is not None]
    return HarnessComparisonRow(
        harness=harness,
        runs=len(subset),
        avg_total=_avg(totals),
        tier_counts=tuple(TierCount(t, sum(1 for r in subset if r.tier == t)) for t in TIERS),
        dimension_averages=_harness_dimension_averages(subset, dim_labels),
    )


def _harness_dimension_averages(
    subset: list[ParsedReport], dim_labels: list[str]
) -> tuple[DimensionAverage, ...]:
    rows: list[DimensionAverage] = []
    for index in range(1, NUM_DIMENSIONS + 1):
        values = [float(r.dim_score(index)) for r in subset if r.dim_score(index) is not None]
        label = dim_labels[index - 1] if index - 1 < len(dim_labels) else f"D{index}"
        rows.append(DimensionAverage(index, label, _avg(values)))
    return tuple(rows)


def _best_harness_comparison(
    rows: tuple[HarnessComparisonRow, ...]
) -> tuple[tuple[str, ...], float | None]:
    best_avg: float | None = None
    best_names: list[str] = []
    for row in rows:
        if row.avg_total is None:
            continue
        if best_avg is None or row.avg_total > best_avg:
            best_avg = row.avg_total
            best_names = [row.harness]
        elif row.avg_total == best_avg:
            best_names.append(row.harness)
    return tuple(best_names), best_avg


def _harness_section(reports: list[ParsedReport], dim_labels: list[str]) -> list[str]:
    """Per-harness rollup for the opencode/codex/claude contest only."""
    comparison = calculate_harness_comparison(reports, dim_labels)
    if not comparison.rows:
        return []

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

    for result_row in comparison.rows:
        tier_counts = {item.tier: item.count for item in result_row.tier_counts}
        row = [
            result_row.harness,
            str(result_row.runs),
            _fmt(result_row.avg_total),
        ]
        row.extend(str(tier_counts[t]) for t in TIERS)
        row.extend(_fmt(d.avg_score) for d in result_row.dimension_averages)
        lines.append("| " + " | ".join(row) + " |")

    if comparison.best_harnesses and comparison.best_avg_total is not None:
        lines.extend(
            [
                "",
                f"**Best harness by average total**: "
                f"{', '.join(f'`{n}`' for n in comparison.best_harnesses)} "
                f"({_fmt(comparison.best_avg_total)}/100).",
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
            by_model.setdefault(cohort_slug(r.model_slug), []).append(r)
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


def calculate_model_coverage(reports: list[ParsedReport]) -> list[ModelCoverageRow]:
    """Return per-model coverage rows before Markdown rendering.

    Example:
        rows = calculate_model_coverage(reports)
        covered_harnesses = rows[0].harnesses
    """
    rows = [_model_coverage_row(slug, subset) for slug, subset in _reports_by_model(reports).items()]
    rows.sort(key=lambda row: row.avg_total if row.avg_total is not None else -1.0, reverse=True)
    return rows


def _reports_by_model(reports: list[ParsedReport]) -> dict[str, list[ParsedReport]]:
    by_model: dict[str, list[ParsedReport]] = {}
    for report in reports:
        if report.model_slug:
            by_model.setdefault(cohort_slug(report.model_slug), []).append(report)
    return by_model


def _model_coverage_row(slug: str, subset: list[ParsedReport]) -> ModelCoverageRow:
    harnesses = tuple(sorted({r.harness for r in subset if _is_benchmark_harness(r.harness)}))
    cursor_subset = [r for r in subset if r.harness == CURSOR_AGENT_PREFIX]
    cursor_totals = [float(r.total) for r in cursor_subset if r.total is not None]
    totals = [float(r.total) for r in subset if r.total is not None]
    return ModelCoverageRow(
        model_slug=slug,
        harnesses=harnesses,
        harness_count=len(harnesses),
        runs=len(subset),
        cursor_runs=len(cursor_subset),
        cursor_avg_total=mean(cursor_totals) if cursor_totals else None,
        avg_total=mean(totals) if totals else None,
    )


def model_harness_coverage(reports: list[ParsedReport]) -> dict[str, dict[str, object]]:
    """Per-model harness coverage keyed by model slug.

    ``harnesses`` / ``harness_count`` count contest harnesses only (opencode,
    codex, claude). ``cursor_runs`` and ``cursor_avg_total`` cover Cursor-agent
    runs for the same slug. ``avg_total`` averages all runs with a parseable total.
    """
    out: dict[str, dict[str, object]] = {}
    for row in calculate_model_coverage(reports):
        out[row.model_slug] = {
            "harnesses": list(row.harnesses),
            "runs": row.runs,
            "harness_count": row.harness_count,
            "cursor_runs": row.cursor_runs,
            "cursor_avg_total": row.cursor_avg_total,
            "avg_total": row.avg_total,
        }
    return out


def build_model_coverage_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: model slug → harness list → run count → avg total."""
    coverage_rows = calculate_model_coverage(reports)
    if not coverage_rows:
        return "## Model coverage\n\n*(no reports parsed)*\n"

    lines = [
        "## Model coverage",
        "",
        "Per-model summary across contest harnesses (opencode, codex, claude). "
        "``harness_count`` is the number of distinct contest harnesses with a "
        "parseable total for that model slug. Cursor-only slugs have harness "
        "count `0` — see **Cursor agent models**. Used for appendix context; "
        "section 2 uses **Aggregated runs ranking**.",
        "",
        "| Model slug | Harnesses | Harness count | Runs | Avg total |",
        "|---|---|---:|---:|---:|",
    ]
    for row in coverage_rows:
        harness_list = ", ".join(row.harnesses) if row.harnesses else "-"
        cells = [
            _display_slug(row.model_slug, display_slug_map),
            harness_list,
            str(row.harness_count),
            str(row.runs),
            _fmt(row.avg_total),
        ]
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


def calculate_aggregated_runs_ranking(
    reports: list[ParsedReport],
) -> list[AggregatedRunRankingRow]:
    """Return section-2 ranking rows before Markdown rendering.

    Example:
        rows = calculate_aggregated_runs_ranking(reports)
        top_total = rows[0].mean_total
    """
    rows: list[AggregatedRunRankingRow] = []
    for rank, item in enumerate(_aggregated_contest_ranking_rows(reports), start=1):
        harness, slug, avg, sample_n, std = item
        rows.append(
            AggregatedRunRankingRow(
                rank=rank,
                harness=harness,
                model_slug=cohort_slug(slug),
                mean_total=avg,
                sample_n=sample_n,
                std_dev=std,
                tier=_tier_from_total(avg),
            )
        )
    return rows


def expected_section2_run_rows(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> list[tuple[str, str, float]]:
    """Return aggregated ``(harness, model_slug, mean_total)`` tuples for section 2."""
    return [
        (
            row.harness,
            _display_slug(row.model_slug, display_slug_map),
            row.mean_total,
        )
        for row in calculate_aggregated_runs_ranking(reports)
    ]


def build_aggregated_runs_ranking_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: mean total per ``(harness, model)`` across replicate audits."""
    rows = calculate_aggregated_runs_ranking(reports)
    if not rows:
        return (
            "## Aggregated runs ranking\n\n"
            "*(no contest or cursor runs with parseable totals)*\n"
        )

    lines = [
        "## Aggregated runs ranking",
        "",
        "Primary ranking table for section 2 verdicts. One row per "
        "``(harness, model_slug)`` with mean total across replicate audits "
        "(N includes every parseable replicate report for that cell).",
        "",
        "| Rank | Harness | Model slug | Mean total | N | Std dev | Tier |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.rank),
                    row.harness,
                    _display_slug(row.model_slug, display_slug_map),
                    _fmt(row.mean_total),
                    str(row.sample_n),
                    _fmt(row.std_dev),
                    row.tier,
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


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
        "## All runs ranking (detail)",
        "",
        "Individual replicate audits. Section 2 primary verdicts use "
        "**Aggregated runs ranking** (mean across replicates).",
        "",
        "| Rank | Harness | Model slug | Replicate | Total | Tier |",
        "|---:|---|---|---|---:|---|",
    ]
    for rank, report in enumerate(ranked, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    report.harness,
                    _display_slug(report.model_slug or "-", display_slug_map),
                    report.replicate_id or "-",
                    _fmt(float(report.total)),
                    report.tier or "-",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _load_generation_metrics(
    report: ParsedReport,
    *,
    source_dirs: list[Path] | None,
) -> dict[str, object] | None:
    """Load ``generation-metrics.json`` for one parsed audit report."""
    metrics_path = _generation_metrics_path(report, source_dirs)
    if metrics_path is None:
        return None
    try:
        payload = load_json(metrics_path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _report_gen_minutes(
    report: ParsedReport,
    *,
    source_dirs: list[Path] | None,
) -> float | None:
    metrics = _load_generation_metrics(report, source_dirs=source_dirs)
    if not metrics:
        return None
    seconds = metrics.get("generation_time_seconds")
    if isinstance(seconds, (int, float)):
        return float(seconds) / 60.0
    return None


def _report_tokens_millions(
    report: ParsedReport,
    *,
    source_dirs: list[Path] | None,
) -> float | None:
    metrics = _load_generation_metrics(report, source_dirs=source_dirs)
    if not metrics:
        return None
    tokens = metrics.get("total_tokens")
    if isinstance(tokens, (int, float)):
        return float(tokens) / 1_000_000.0
    return None


def _report_cost_usd(
    report: ParsedReport,
    *,
    source_dirs: list[Path] | None,
) -> float | None:
    metrics = _load_generation_metrics(report, source_dirs=source_dirs)
    if not metrics:
        return None
    cost = metrics.get("estimated_cost_usd")
    if isinstance(cost, (int, float)):
        return float(cost)
    return None


def _mean_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def _quality_per_dollar(mean_total: float, mean_cost: float | None) -> str:
    if mean_cost is None or mean_cost == 0:
        return "n/a"
    return f"{mean_total / mean_cost:.2f}"


def _quality_per_minute(mean_total: float, mean_gen_minutes: float | None) -> str:
    if mean_gen_minutes is None or mean_gen_minutes == 0:
        return "n/a"
    return f"{mean_total / mean_gen_minutes:.2f}"


def _group_reports_by_harness_model(
    reports: list[ParsedReport],
) -> dict[tuple[str, str], list[ParsedReport]]:
    groups: dict[tuple[str, str], list[ParsedReport]] = {}
    for report in reports:
        if report.total is None or not report.model_slug:
            continue
        if not (
            _is_benchmark_harness(report.harness)
            or report.harness == CURSOR_AGENT_PREFIX
        ):
            continue
        key = (report.harness, report.model_slug)
        groups.setdefault(key, []).append(report)
    return groups


def _group_reports_by_auditor_harness_model(
    reports: list[ParsedReport],
) -> dict[tuple[str, str, str], list[ParsedReport]]:
    groups: dict[tuple[str, str, str], list[ParsedReport]] = {}
    for report in reports:
        if not report.model_slug:
            continue
        key = (report.auditor, report.harness, report.model_slug)
        groups.setdefault(key, []).append(report)
    return groups


def _mean_dimension_score(reports: list[ParsedReport], index: int) -> float | None:
    scores = [float(score) for report in reports if (score := report.dim_score(index)) is not None]
    return mean(scores) if scores else None


def _classify_dimension_signal(
    *,
    max_score: int | None,
    all_avg: float | None,
    full_marks_ratio: float | None,
    harness_spread: float | None,
) -> str:
    """Classify one dimension for meta-analysis section 5."""
    if (
        full_marks_ratio is not None
        and full_marks_ratio >= _SATURATION_FULL_MARKS_RATIO
    ):
        return "saturated"
    if (
        max_score is not None
        and max_score > 0
        and all_avg is not None
        and all_avg / max_score < _BLIND_SPOT_MAX_AVG_RATIO
        and harness_spread is not None
        and harness_spread < _BLIND_SPOT_MAX_HARNESS_SPREAD
    ):
        return "universal blind spot"
    if (
        harness_spread is not None
        and harness_spread >= _HARNESS_ATTRIBUTABLE_MIN_SPREAD
    ):
        return "harness-attributable"
    if (
        max_score is not None
        and max_score > 0
        and all_avg is not None
        and all_avg / max_score >= _CLEAN_NEAR_MAX_RATIO
    ):
        return "clean"
    return "discriminating"


def calculate_dimension_signals(
    reports: list[ParsedReport],
) -> tuple[DimensionSignalRow, ...]:
    """Return per-dimension signal rows for contest-cohort meta-analysis section 5.

    Example:
        signals = calculate_dimension_signals(reports)
        saturated = [row for row in signals if row.classification == "saturated"]
    """
    harnesses = _contest_harnesses_in_data(reports)
    contest = _benchmark_reports(reports)
    if not contest:
        return ()

    dim_labels = _dimension_labels(reports)
    rows: list[DimensionSignalRow] = []
    for index in range(1, NUM_DIMENSIONS + 1):
        max_score = _max_for_dimension(reports, index)
        scored = [
            float(r.dim_score(index))
            for r in contest
            if r.dim_score(index) is not None
        ]
        all_avg = _avg(scored)
        full_marks_count = sum(
            1 for score in scored if max_score is not None and score >= max_score
        )
        scored_count = len(scored)
        full_marks_ratio = (
            full_marks_count / scored_count if scored_count else None
        )
        harness_avgs: list[float] = []
        harness_averages: list[DimensionHarnessAverage] = []
        for harness in harnesses:
            subset = [
                float(r.dim_score(index))
                for r in contest
                if r.harness == harness and r.dim_score(index) is not None
            ]
            harness_avg = _avg(subset)
            harness_averages.append(DimensionHarnessAverage(harness, harness_avg))
            if harness_avg is not None:
                harness_avgs.append(harness_avg)
        harness_spread = (
            max(harness_avgs) - min(harness_avgs) if len(harness_avgs) >= 2 else None
        )
        label = dim_labels[index - 1] if index - 1 < len(dim_labels) else f"D{index}"
        rows.append(
            DimensionSignalRow(
                index=index,
                label=label,
                max_score=max_score,
                all_avg=all_avg,
                harness_averages=tuple(harness_averages),
                full_marks_count=full_marks_count,
                scored_count=scored_count,
                full_marks_ratio=full_marks_ratio,
                harness_spread=harness_spread,
                classification=_classify_dimension_signal(
                    max_score=max_score,
                    all_avg=all_avg,
                    full_marks_ratio=full_marks_ratio,
                    harness_spread=harness_spread,
                ),
            )
        )
    return tuple(rows)


def _format_dimension_signal_harness_avgs(
    harness_averages: tuple[DimensionHarnessAverage, ...],
) -> str:
    parts = [
        f"{item.harness}={_fmt(item.avg_score)}"
        for item in harness_averages
        if item.avg_score is not None
    ]
    return " / ".join(parts)


def build_dimension_signal_section(reports: list[ParsedReport]) -> str:
    """Precomputed section-5 dimension lines for the meta-analysis prompt."""
    signals = calculate_dimension_signals(reports)
    if not signals:
        return "## Dimension-level signal (precomputed)\n\n*(no contest reports parsed)*\n"

    lines = [
        "## Dimension-level signal (precomputed)",
        "",
        "Copy these lines into section 5 verbatim (averages and Classify labels).",
        "",
    ]
    for row in signals:
        harness_parts = _format_dimension_signal_harness_avgs(row.harness_averages)
        max_display = row.max_score if row.max_score is not None else "?"
        lines.append(
            f"- **D{row.index} — {row.label}** (max {max_display}): "
            f"universal-avg {_fmt(row.all_avg)}; per-harness avg {harness_parts}. "
            f"Classify: **{row.classification}**."
        )
    return "\n".join(lines) + "\n"


def saturated_dimension_warnings(
    reports: list[ParsedReport],
) -> list[tuple[int, int, int, int | None]]:
    """Return saturated dimensions as ``(index, full_count, scored_count, max_score)``."""
    return [
        (row.index, row.full_marks_count, row.scored_count, row.max_score)
        for row in calculate_dimension_signals(reports)
        if row.classification == "saturated"
    ]


def build_aggregated_performance_cost_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: mean performance/cost per ``(harness, model_slug)`` cell."""
    groups = _group_reports_by_harness_model(reports)
    if not groups:
        return (
            "## Aggregated performance & cost\n\n"
            "*(no contest or cursor runs with parseable totals)*\n"
        )

    rows: list[tuple[float, float | None, list[str]]] = []
    for (harness, slug), subset in groups.items():
        totals = [float(r.total) for r in subset if r.total is not None]
        mean_total = mean(totals)
        mean_gen = _mean_optional(
            [_report_gen_minutes(r, source_dirs=source_dirs) for r in subset]
        )
        mean_tokens = _mean_optional(
            [_report_tokens_millions(r, source_dirs=source_dirs) for r in subset]
        )
        mean_cost = _mean_optional(
            [_report_cost_usd(r, source_dirs=source_dirs) for r in subset]
        )
        target_label = f"{harness}-{_display_slug(slug, display_slug_map)}"
        cells = [
            target_label,
            _fmt(mean_gen) if mean_gen is not None else "n/a",
            f"{mean_tokens:.2f}" if mean_tokens is not None else "n/a",
            f"{mean_cost:.2f}" if mean_cost is not None else "n/a",
            _fmt(mean_total),
            _quality_per_dollar(mean_total, mean_cost),
            _quality_per_minute(mean_total, mean_gen),
        ]
        rows.append((mean_total, mean_cost, cells))

    rows.sort(key=lambda item: (-item[0], item[1] if item[1] is not None else float("inf")))
    lines = [
        "## Aggregated performance & cost",
        "",
        "Authoritative rows for section 6. One row per ``(harness, model_slug)``",
        "with mean generation time, tokens, cost, and total across replicate",
        "audits. Use **Performance & cost (detail)** for per-replicate citations.",
        "",
        "| Target (harness-model) | Gen-time (min) | Tokens (M) | Cost (USD) | "
        "Mean total | Quality per $ | Quality per minute |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, _, cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build_performance_cost_detail_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: per-replicate performance/cost rows for citations."""
    eligible = [
        r
        for r in reports
        if r.total is not None
        and r.model_slug
        and (
            _is_benchmark_harness(r.harness)
            or r.harness == CURSOR_AGENT_PREFIX
        )
    ]
    if not eligible:
        return "## Performance & cost (detail)\n\n*(no parseable runs)*\n"

    ranked = sorted(eligible, key=lambda r: float(r.total), reverse=True)  # type: ignore[arg-type]
    lines = [
        "## Performance & cost (detail)",
        "",
        "Individual replicate audits. Section 6 primary table uses "
        "**Aggregated performance & cost**.",
        "",
        "| Target (harness-model) | Replicate | Gen-time (min) | Tokens (M) | "
        "Cost (USD) | Total score | Quality per $ | Quality per minute |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for report in ranked:
        gen_min = _report_gen_minutes(report, source_dirs=source_dirs)
        tokens_m = _report_tokens_millions(report, source_dirs=source_dirs)
        cost = _report_cost_usd(report, source_dirs=source_dirs)
        total = float(report.total)  # type: ignore[arg-type]
        target_label = (
            f"{report.harness}-{_display_slug(report.model_slug or '-', display_slug_map)}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    target_label,
                    report.replicate_id or "-",
                    _fmt(gen_min) if gen_min is not None else "n/a",
                    f"{tokens_m:.2f}" if tokens_m is not None else "n/a",
                    f"{cost:.2f}" if cost is not None else "n/a",
                    _fmt(total),
                    _quality_per_dollar(total, cost),
                    _quality_per_minute(total, gen_min),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def build_aggregated_dimension_matrix_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: mean dimension scores per ``(auditor, harness, model)`` cell."""
    groups = _group_reports_by_auditor_harness_model(reports)
    if not groups:
        return "## Aggregated dimension score matrix\n\n*(no reports parsed)*\n"

    rows: list[tuple[str, str, str, float | None, list[str]]] = []
    for (auditor, harness, slug), subset in sorted(groups.items()):
        mean_total = _mean_optional(
            [float(r.total) if r.total is not None else None for r in subset]
        )
        cells = [
            auditor,
            harness,
            _display_slug(slug, display_slug_map),
            str(len(subset)),
        ]
        for index in range(1, NUM_DIMENSIONS + 1):
            dim_avg = _mean_dimension_score(subset, index)
            cells.append(_fmt(dim_avg) if dim_avg is not None else "n/a")
        cells.append(_fmt(mean_total) if mean_total is not None else "n/a")
        rows.append((auditor, harness, slug, mean_total, cells))

    rows.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            -(item[3] if item[3] is not None else -1.0),
        )
    )
    header = (
        ["Auditor", "Harness", "Model", "N"]
        + [f"D{i}" for i in range(1, NUM_DIMENSIONS + 1)]
        + ["Mean total"]
    )
    lines = [
        "## Aggregated dimension score matrix",
        "",
        "Authoritative appendix rows: one mean score row per "
        "``(auditor, harness, model_slug)`` across replicate audits. "
        "Use **Dimension score matrix (detail)** for per-replicate evidence.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for _, _, _, _, cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build_dimension_matrix_detail_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: per-replicate dimension scores for appendix citations."""
    if not reports:
        return "## Dimension score matrix (detail)\n\n*(no reports parsed)*\n"

    header = (
        ["Auditor", "Harness", "Model", "Replicate"]
        + [f"D{i}" for i in range(1, NUM_DIMENSIONS + 1)]
        + ["Total"]
    )
    lines = [
        "## Dimension score matrix (detail)",
        "",
        "Individual replicate audits. Appendix primary matrix uses "
        "**Aggregated dimension score matrix**.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for report in sorted(
        reports,
        key=lambda r: (
            r.auditor,
            r.harness,
            r.model_slug or "",
            r.replicate_id or "",
        ),
    ):
        cells = [
            report.auditor,
            report.harness,
            _display_slug(report.model_slug or "-", display_slug_map),
            report.replicate_id or "-",
        ]
        for index in range(1, NUM_DIMENSIONS + 1):
            score = report.dim_score(index)
            cells.append(str(score) if score is not None else "n/a")
        cells.append(str(report.total) if report.total is not None else "n/a")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def expected_section2a_ollama_rows(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> list[tuple[str, int, float, float | None, str]]:
    """Return section-2a tuples: ``(slug, n_harnesses, avg, std_dev, tier)``."""
    return [
        (
            _display_slug(row.model_slug, display_slug_map),
            row.n_harnesses,
            row.avg_total,
            row.std_dev,
            row.tier,
        )
        for row in calculate_ollama_model_ranking(reports)
    ]


def calculate_ollama_model_ranking(
    reports: list[ParsedReport],
    *,
    ollama_slugs: frozenset[str] | None = None,
) -> list[OllamaModelRankingRow]:
    """Return section-2a Ollama ranking rows before Markdown rendering.

    Example:
        rows = calculate_ollama_model_ranking(reports)
        best_slug = rows[0].model_slug
    """
    rows: list[OllamaModelRankingRow] = []
    for rank, raw in enumerate(
        _ollama_ranking_rows(reports, ollama_slugs=ollama_slugs),
        start=1,
    ):
        rows.append(_ollama_ranking_row_from_dict(rank, raw))
    return rows


def _ollama_ranking_row_from_dict(
    rank: int, raw: dict[str, object]
) -> OllamaModelRankingRow:
    cell_avgs = raw["cell_avgs"]
    assert isinstance(cell_avgs, dict)
    harness_averages = tuple(
        HarnessAverage(harness, float(cell_avgs[harness]))
        for harness in _CONTEST_HARNESS_COLUMN_ORDER
        if harness in cell_avgs
    )
    std = raw["std_dev"]
    return OllamaModelRankingRow(
        rank=rank,
        model_slug=str(raw["slug"]),
        n_harnesses=int(raw["n_harnesses"]),  # type: ignore[arg-type]
        avg_total=float(raw["avg_total"]),  # type: ignore[arg-type]
        std_dev=float(std) if isinstance(std, (int, float)) else None,
        tier=str(raw["tier"]),
        harness_averages=harness_averages,
    )


def build_ollama_model_ranking_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Markdown table: Ollama Cloud models ranked by cross-harness mean total."""
    ranked = calculate_ollama_model_ranking(reports)
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
    for row in ranked:
        cell_avgs = {cell.harness: cell.avg_total for cell in row.harness_averages}
        cells = [
            str(row.rank),
            _display_slug(row.model_slug, display_slug_map),
            str(row.n_harnesses),
            _fmt(row.avg_total),
            _fmt(row.std_dev),
            row.tier,
        ]
        for harness in _CONTEST_HARNESS_COLUMN_ORDER:
            avg = cell_avgs.get(harness)
            cells.append(_fmt(avg) if avg is not None else "-")
        lines.append("| " + " | ".join(cells) + " |")

    best = ranked[0]
    best_slug = _display_slug(best.model_slug, display_slug_map)
    lines.extend(
        [
            "",
            f"**Best open-source model**: `{best_slug}` "
            f"({_fmt(best.avg_total)}/100 across "
            f"{best.n_harnesses} harnesses).",
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
        and cohort_slug(r.model_slug) in cohort
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


def calculate_harness_rankings(
    reports: list[ParsedReport],
) -> tuple[HarnessRankingRow, ...]:
    """Return executive-summary harness rankings before Markdown rendering.

    Example:
        rows = calculate_harness_rankings(reports)
        best_avg = rows[0].avg_total
    """
    rows: list[HarnessRankingRow] = []
    for rank, (harness, stats) in enumerate(_contest_harness_rankings(reports), 1):
        rows.append(_harness_ranking_row(rank, harness, stats))
    return tuple(rows)


def _harness_ranking_row(
    rank: int, harness: str, stats: dict[str, float | int | None]
) -> HarnessRankingRow:
    return HarnessRankingRow(
        rank=rank,
        harness=harness,
        sample_n=int(stats["n"]),  # type: ignore[arg-type]
        avg_total=float(stats["avg"]),  # type: ignore[arg-type]
        median_total=float(stats["median"]) if stats["median"] is not None else None,
        std_dev=float(stats["std_dev"]) if stats["std_dev"] is not None else None,
    )


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
) -> DimensionBlindSpot | None:
    """Dimension with the lowest contest-cohort all-harness average."""
    harnesses = _contest_harnesses_in_data(reports)
    contest = _benchmark_reports(reports)
    if not harnesses or not contest:
        return None

    dim_labels = _dimension_labels(reports)
    candidate: DimensionBlindSpot | None = None
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
        harness_averages = tuple(
            DimensionHarnessAverage(harness, per_harness[harness])
            for harness in sorted(per_harness)
        )
        candidate = DimensionBlindSpot(
            index=i,
            label=label,
            max_score=_max_for_dimension(reports, i),
            all_avg=all_avg,
            harness_averages=harness_averages,
        )
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


def calculate_executive_summary_expectations(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> ExecutiveSummaryExpectations:
    """Return typed verdict data for meta-analysis section 1.

    Example:
        expected = calculate_executive_summary_expectations(reports)
        best = expected.top_model.model_slug if expected.top_model else None
    """
    return ExecutiveSummaryExpectations(
        harness_rankings=calculate_harness_rankings(reports),
        top_model=_top_model_expectation(reports, display_slug_map),
        best_ollama=_best_ollama_expectation(reports, display_slug_map),
        cursor_runs=_cursor_run_expectation(reports),
        mixed_version_harnesses=tuple(
            _mixed_version_contest_harnesses(reports, source_dirs=source_dirs)
        ),
        blind_spot=_lowest_dimension_candidate(reports),
    )


def _top_model_expectation(
    reports: list[ParsedReport], display_slug_map: dict[str, str] | None
) -> TopModelExpectation | None:
    top_run = _top_contest_run(reports)
    if top_run is None or top_run.total is None:
        return None
    model_slug = top_run.model_slug or "-"
    return TopModelExpectation(
        harness=top_run.harness,
        model_slug=_display_slug(model_slug, display_slug_map),
        total=float(top_run.total),
        note=_single_harness_run_note(reports, model_slug),
    )


def _best_ollama_expectation(
    reports: list[ParsedReport], display_slug_map: dict[str, str] | None
) -> BestOllamaExpectation | None:
    rows = calculate_ollama_model_ranking(reports)
    if not rows:
        return None
    best = rows[0]
    return BestOllamaExpectation(
        model_slug=_display_slug(best.model_slug, display_slug_map),
        avg_total=best.avg_total,
        n_harnesses=best.n_harnesses,
        std_dev=best.std_dev,
    )


def _cursor_run_expectation(
    reports: list[ParsedReport],
) -> CursorRunExpectation | None:
    cursor_reports = _cursor_agent_reports(reports)
    if not cursor_reports:
        return None
    totals = [float(r.total) for r in cursor_reports if r.total is not None]
    return CursorRunExpectation(
        runs=len(cursor_reports),
        avg_total=mean(totals) if totals else None,
    )


def executive_summary_expectations(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> dict[str, object]:
    """Key verdict fields the executive summary must contain."""
    typed = calculate_executive_summary_expectations(
        reports,
        source_dirs=source_dirs,
        display_slug_map=display_slug_map,
    )
    expectations: dict[str, object] = {}

    if typed.harness_rankings:
        best_harness = typed.harness_rankings[0]
        expectations["best_harness"] = best_harness.harness
        expectations["best_harness_avg"] = best_harness.avg_total
    if typed.top_model is not None:
        expectations["top_model_slug"] = typed.top_model.model_slug
        expectations["top_model_total"] = typed.top_model.total
        expectations["top_model_harness"] = typed.top_model.harness
    if typed.best_ollama is not None:
        expectations["best_ollama_slug"] = typed.best_ollama.model_slug
        expectations["best_ollama_avg"] = typed.best_ollama.avg_total
        expectations["best_ollama_n_harnesses"] = typed.best_ollama.n_harnesses
    expectations["mixed_version_harnesses"] = list(typed.mixed_version_harnesses)
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
        harness_parts = " / ".join(
            f"{item.harness} {_fmt(item.avg_score) if item.avg_score is not None else 'n/a'}"
            for item in blind_spot.harness_averages
        )
        max_display = blind_spot.max_score if blind_spot.max_score is not None else "?"
        lines.append(
            f"- **Universal blind spot candidate**: D{blind_spot.index} {blind_spot.label} — "
            f"all avg {_fmt(blind_spot.all_avg)}/{max_display}; {harness_parts}."
        )

    return "\n".join(lines) + "\n"


def build_precomputed_rollup(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
    benchmark_projects_root: Path | None = None,
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
        "bullets, section 2, 2a, 3, 4, 6, appendix dimension matrix, and the "
        "harness CLI versions table in meta-analysis.md MUST match these values.** "
        "Use individual reports only for citations and narrative.",
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
        build_aggregated_runs_ranking_table(
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
        "",
        build_dimension_signal_section(reports).rstrip(),
        "",
        build_aggregated_performance_cost_table(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_performance_cost_detail_table(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_aggregated_dimension_matrix_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_dimension_matrix_detail_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
    ]
    from benchmark.d9_preflight import build_d9_subcheck_cohort_section  # noqa: PLC0415

    d9_section = build_d9_subcheck_cohort_section(
        benchmark_projects_root=benchmark_projects_root,
        source_dirs=source_dirs,
    ).rstrip()
    if d9_section:
        parts.extend(["", d9_section])
    return "\n".join(parts) + "\n"


def _meta_table_float_equal(expected: float | None, reported: float | None) -> bool:
    """True when two rollup/meta table floats match at one decimal place."""
    if expected is None or reported is None:
        return expected is reported
    return round(expected, 1) == round(reported, 1)


def validate_meta_analysis_coverage(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> list[str]:
    """Compare section-2 aggregated rows in meta-analysis.md to the rollup."""
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
            or not _meta_table_float_equal(exp_total, got_total)
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
            or not _meta_table_float_equal(exp_avg, got_avg)
            or not _meta_table_float_equal(exp_std, got_std)
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


def validate_meta_analysis_dimension_signals(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
) -> list[str]:
    """Compare section-5 dimension classifications in meta-analysis.md to rollup."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    expected = calculate_dimension_signals(reports)
    if not expected or not meta_path.is_file():
        return []

    text = meta_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"#{2,3}\s*5\.\s*Dimension-level signal(.*?)(?=\n#{2,3}\s+\d+\.|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return ["section 5 (Dimension-level signal) not found in meta-analysis.md"]

    section = section_match.group(1)
    line_re = re.compile(
        r"^\s*-\s*\*\*D(\d+)\b.*?\bClassify:\s*\*\*([^*]+)\*\*",
        re.MULTILINE | re.IGNORECASE,
    )
    reported = {
        int(match.group(1)): match.group(2).strip().lower()
        for match in line_re.finditer(section)
    }

    errors: list[str] = []
    if len(reported) != len(expected):
        errors.append(
            f"section 5 has {len(reported)} dimension lines but rollup has {len(expected)}"
        )

    for row in expected:
        got = reported.get(row.index)
        exp = row.classification.lower()
        if got is None:
            errors.append(f"D{row.index}: missing classification line in section 5")
            continue
        if got != exp:
            errors.append(
                f"D{row.index}: expected classification {exp!r} but meta-analysis has {got!r}"
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
