"""Statistical normalization for audit reports.

Consumes typed :class:`~benchmark.audit_report.ParsedReport` values. Produces
harness comparison, cross-harness model comparison, dimension breakdown, and
leader-relative normalized scores. These are auto-computed inputs for the AI
meta-analyst — not the final analysis.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import comb
from pathlib import Path
from statistics import mean, median, stdev

from benchmark.audit_report import (
    DEFAULT_DIMENSION_LABELS,
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
LEADER_MODEL_SLUG_SUBSTRINGS: tuple[str, ...] = (
    "gpt_5_5",
    "claude_opus_4_7",
    "claude_opus_4_8",
)

_NORMALIZED_PCT_CAP = 150.0
_SATURATION_FULL_MARKS_RATIO = 0.80
_BLIND_SPOT_MAX_AVG_RATIO = 0.70
_BLIND_SPOT_MAX_HARNESS_SPREAD = 1.0
_HARNESS_ATTRIBUTABLE_MIN_SPREAD = 2.0
_CLEAN_NEAR_MAX_RATIO = 0.75
_HARNESS_VERDICT_MARGIN_PTS = 1.0
_BOOTSTRAP_ITERATIONS = 2000
_BOOTSTRAP_SEED = 42
_QUALITY_PER_DOLLAR_MIN_COST_USD = 0.10


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
    total: float
    leaders: tuple[tuple[str, str, int, float | None, str], ...]
    """``(harness, model_slug, sample_n, std_dev, note)`` per tied rank-1 cell."""

    @property
    def is_tie(self) -> bool:
        return len(self.leaders) > 1

    @property
    def harness(self) -> str:
        return self.leaders[0][0]

    @property
    def model_slug(self) -> str:
        return self.leaders[0][1]

    @property
    def note(self) -> str:
        return self.leaders[0][4]


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
class PerformanceCostCell:
    harness: str
    model_slug: str
    mean_total: float
    mean_gen_minutes: float | None
    quality_per_minute: float | None
    tier: str


@dataclass(frozen=True)
class QualityTimeTradeoffExpectation:
    overall_harness: str
    overall_model_slug: str
    overall_mean_total: float
    overall_gen_minutes: float
    overall_quality_per_minute: float
    contest_harness: str | None
    contest_model_slug: str | None
    contest_mean_total: float | None
    contest_gen_minutes: float | None
    contest_quality_per_minute: float | None


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
    quality_time: QualityTimeTradeoffExpectation | None


@dataclass(frozen=True)
class OllamaModelRankingRow:
    rank: int
    model_slug: str
    n_harnesses: int
    avg_total: float
    std_dev: float | None
    tier: str
    harness_averages: tuple[HarnessAverage, ...]


@dataclass(frozen=True)
class CellMeanRow:
    model_slug: str
    harness: str
    mean_total: float
    sample_n: int
    std_dev: float | None


@dataclass(frozen=True)
class PairwiseHarnessComparison:
    harness_a: str
    harness_b: str
    mean_delta: float
    ci_low: float
    ci_high: float
    p_value: float
    n_models: int
    positive_deltas: int


@dataclass(frozen=True)
class HarnessInferenceResult:
    label: str
    n_models: int
    harness_means: tuple[tuple[str, float, float, float], ...]
    leader: str | None
    runner_up: str | None
    gap: float | None
    verdict: str
    top_pairwise: PairwiseHarnessComparison | None
    win_counts: tuple[tuple[str, int], ...]
    largest_spread_dimension: tuple[int, str] | None


@dataclass(frozen=True)
class PractitionerDecisionRow:
    goal: str
    target: str
    mean_total: float
    gen_minutes: float | None
    cost_usd: float | None
    caveat: str


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


def calculate_cell_means(reports: list[ParsedReport]) -> tuple[CellMeanRow, ...]:
    """Mean audit total per ``(harness, model_slug)`` cell on the cross-harness grid."""
    cohort = _cross_harness_cohort_slugs(reports)
    contest_harnesses = [
        h for h in _CONTEST_HARNESS_COLUMN_ORDER if h in _contest_harnesses_in_data(reports)
    ]
    rows: list[CellMeanRow] = []
    for base in sorted(cohort):
        for harness in contest_harnesses:
            cell_avg = _contest_cell_avg_total(reports, harness, base)
            if cell_avg is None:
                continue
            subset = [
                r
                for r in reports
                if r.harness == harness
                and cohort_slug(r.model_slug) == base
                and r.total is not None
            ]
            totals = [float(r.total) for r in subset]
            rows.append(
                CellMeanRow(
                    model_slug=base,
                    harness=harness,
                    mean_total=cell_avg,
                    sample_n=len(totals),
                    std_dev=stdev(totals) if len(totals) >= 2 else None,
                )
            )
    return tuple(rows)


def _cell_mean_matrix(
    cell_means: tuple[CellMeanRow, ...],
) -> dict[str, dict[str, float]]:
    matrix: dict[str, dict[str, float]] = {}
    for row in cell_means:
        matrix.setdefault(row.model_slug, {})[row.harness] = row.mean_total
    return matrix


def bootstrap_ci(
    values: list[float],
    *,
    n_iter: int = _BOOTSTRAP_ITERATIONS,
    seed: int = _BOOTSTRAP_SEED,
) -> tuple[float, float, float]:
    """Return ``(mean, ci_low, ci_high)`` at 95% for the sample mean."""
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0], values[0]
    rng = random.Random(seed)
    n = len(values)
    boot_means = sorted(
        sum(rng.choice(values) for _ in range(n)) / n for _ in range(n_iter)
    )
    mean_val = mean(values)
    lo = boot_means[int(0.025 * n_iter)]
    hi = boot_means[int(0.975 * n_iter)]
    return mean_val, lo, hi


def paired_sign_test(deltas: list[float]) -> float | None:
    """Two-sided exact sign test p-value for paired deltas (zeros excluded)."""
    non_zero = [delta for delta in deltas if delta != 0.0]
    n = len(non_zero)
    if n == 0:
        return 1.0
    positives = sum(1 for delta in non_zero if delta > 0.0)
    tail_low = sum(comb(n, i) * (0.5**n) for i in range(positives + 1))
    tail_high = sum(comb(n, i) * (0.5**n) for i in range(positives, n + 1))
    return min(1.0, 2 * min(tail_low, tail_high))


def _compute_harness_verdict(
    gap: float | None,
    pairwise: PairwiseHarnessComparison | None,
    *,
    margin_pts: float = _HARNESS_VERDICT_MARGIN_PTS,
) -> str:
    if gap is None or gap <= 0:
        return "tie"
    if gap < margin_pts:
        if pairwise is not None and pairwise.ci_low <= 0.0 <= pairwise.ci_high:
            return "tie"
        return "marginal"
    if pairwise is not None:
        if pairwise.ci_low <= 0.0 <= pairwise.ci_high:
            return "marginal"
        if pairwise.p_value > 0.05:
            return "marginal"
    return "decisive"


def calculate_harness_inference(
    reports: list[ParsedReport],
    *,
    label: str = "primary",
    margin_pts: float = _HARNESS_VERDICT_MARGIN_PTS,
) -> HarnessInferenceResult | None:
    """Paired harness inference on cross-harness cell means (one row per model)."""
    cell_means = calculate_cell_means(reports)
    if not cell_means:
        return None

    matrix = _cell_mean_matrix(cell_means)
    n_models = len(matrix)
    harnesses = [
        h for h in _CONTEST_HARNESS_COLUMN_ORDER if h in _contest_harnesses_in_data(reports)
    ]
    if n_models < 2 or len(harnesses) < 2:
        return HarnessInferenceResult(
            label=label,
            n_models=n_models,
            harness_means=(),
            leader=None,
            runner_up=None,
            gap=None,
            verdict="insufficient-data",
            top_pairwise=None,
            win_counts=(),
            largest_spread_dimension=_largest_harness_dimension_spread(reports),
        )

    harness_means: list[tuple[str, float, float, float]] = []
    for harness in harnesses:
        vals = [matrix[model][harness] for model in matrix if harness in matrix[model]]
        if not vals:
            continue
        avg, lo, hi = bootstrap_ci(vals)
        harness_means.append((harness, avg, lo, hi))
    harness_means.sort(key=lambda item: item[1], reverse=True)

    leader = harness_means[0][0] if harness_means else None
    runner_up = harness_means[1][0] if len(harness_means) >= 2 else None
    gap = (
        harness_means[0][1] - harness_means[1][1]
        if len(harness_means) >= 2
        else None
    )

    top_pairwise: PairwiseHarnessComparison | None = None
    if leader and runner_up:
        deltas = [
            matrix[model][leader] - matrix[model][runner_up]
            for model in matrix
            if leader in matrix[model] and runner_up in matrix[model]
        ]
        mean_delta, ci_low, ci_high = bootstrap_ci(deltas)
        p_value = paired_sign_test(deltas) or 1.0
        top_pairwise = PairwiseHarnessComparison(
            harness_a=leader,
            harness_b=runner_up,
            mean_delta=mean_delta,
            ci_low=ci_low,
            ci_high=ci_high,
            p_value=p_value,
            n_models=len(deltas),
            positive_deltas=sum(1 for delta in deltas if delta > 0.0),
        )

    win_counts: dict[str, int] = {harness: 0 for harness in harnesses}
    for model_scores in matrix.values():
        if not model_scores:
            continue
        best_harness = max(model_scores.items(), key=lambda item: item[1])[0]
        win_counts[best_harness] = win_counts.get(best_harness, 0) + 1

    verdict = _compute_harness_verdict(gap, top_pairwise, margin_pts=margin_pts)
    return HarnessInferenceResult(
        label=label,
        n_models=n_models,
        harness_means=tuple(harness_means),
        leader=leader,
        runner_up=runner_up,
        gap=gap,
        verdict=verdict,
        top_pairwise=top_pairwise,
        win_counts=tuple(sorted(win_counts.items())),
        largest_spread_dimension=_largest_harness_dimension_spread(reports),
    )


def filter_version_homogeneous_reports(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> list[ParsedReport]:
    """Keep reports whose harness CLI version matches the mode version per harness."""
    coverage = collect_harness_cli_versions(reports, source_dirs=source_dirs)
    mode_version: dict[str, str] = {}
    for harness, version_map in coverage.items():
        if not _is_benchmark_harness(harness) or not version_map:
            continue
        mode_version[harness] = max(version_map, key=lambda version: len(version_map[version]))

    if not mode_version:
        return list(reports)

    kept: list[ParsedReport] = []
    for report in reports:
        if report.harness not in mode_version:
            kept.append(report)
            continue
        label = _load_cli_version_for_report(report, source_dirs=source_dirs)
        if label == mode_version[report.harness]:
            kept.append(report)
    return kept


def _largest_harness_dimension_spread(
    reports: list[ParsedReport],
) -> tuple[int, str] | None:
    """Dimension index + label with largest per-harness avg spread in contest cohort."""
    dim_labels = _dimension_labels(reports)
    contest = _benchmark_reports(reports)
    harnesses = _contest_harnesses_in_data(reports)
    if not contest or not harnesses:
        return None

    best_index = 0
    best_spread = -1.0
    for index in range(1, NUM_DIMENSIONS + 1):
        harness_avgs: list[float] = []
        for harness in harnesses:
            subset = [
                float(r.dim_score(index))
                for r in contest
                if r.harness == harness and r.dim_score(index) is not None
            ]
            avg = _avg(subset)
            if avg is not None:
                harness_avgs.append(avg)
        if len(harness_avgs) < 2:
            continue
        spread = max(harness_avgs) - min(harness_avgs)
        if spread > best_spread:
            best_spread = spread
            best_index = index
    if best_spread < 0:
        return None
    label = (
        dim_labels[best_index - 1]
        if best_index - 1 < len(dim_labels)
        else f"D{best_index}"
    )
    return best_index, label


def _needle_dimension_for_model(
    reports: list[ParsedReport],
    model_slug: str,
) -> str:
    """Dimension with largest harness spread for one model slug."""
    harnesses = _contest_harnesses_in_data(reports)
    best_index = 0
    best_spread = -1.0
    for index in range(1, NUM_DIMENSIONS + 1):
        harness_avgs: list[float] = []
        for harness in harnesses:
            subset = [
                float(r.dim_score(index))
                for r in reports
                if r.harness == harness
                and cohort_slug(r.model_slug) == model_slug
                and r.dim_score(index) is not None
            ]
            avg = _avg(subset)
            if avg is not None:
                harness_avgs.append(avg)
        if len(harness_avgs) < 2:
            continue
        spread = max(harness_avgs) - min(harness_avgs)
        if spread > best_spread:
            best_spread = spread
            best_index = index
    if best_index == 0:
        return "—"
    return f"D{best_index}"


def _harness_verdict_bullet(inference: HarnessInferenceResult) -> str:
    if inference.verdict == "insufficient-data":
        return (
            "- **Harness verdict (insufficient-data)**: fewer than two paired "
            "models on the cross-harness grid — harness verdict suppressed."
        )

    leader = inference.leader or "n/a"
    leader_mean = next(
        (item[1] for item in inference.harness_means if item[0] == inference.leader),
        None,
    )
    runner = inference.runner_up or "n/a"
    runner_mean = next(
        (item[1] for item in inference.harness_means if item[0] == inference.runner_up),
        None,
    )
    verdict_label = inference.verdict
    if inference.verdict in {"tie", "marginal"}:
        opener = (
            f"No decisive winner among contest harnesses — cell-mean leader `{leader}`"
        )
        if (
            leader_mean is not None
            and runner_mean is not None
            and inference.gap is not None
        ):
            opener += (
                f" {_fmt(leader_mean)}/100 (+{_fmt(inference.gap)} vs `{runner}` "
                f"{_fmt(runner_mean)})"
            )
        opener += f"; paired n={inference.n_models} models"
        if inference.top_pairwise is not None:
            pw = inference.top_pairwise
            opener += (
                f"; {pw.harness_a}−{pw.harness_b} Δ={_fmt(pw.mean_delta)} "
                f"(95% CI {_fmt(pw.ci_low)}–{_fmt(pw.ci_high)}; sign-test p={pw.p_value:.2f})"
            )
        if inference.win_counts:
            wins = ", ".join(
                f"{harness} {count}/{inference.n_models}"
                for harness, count in inference.win_counts
            )
            opener += f". Tie-breaker win counts: {wins}"
        return f"- **Harness verdict ({verdict_label})**: {opener}."

    mean_clause = f"{_fmt(leader_mean)}/100" if leader_mean is not None else "n/a"
    gap_clause = f"+{_fmt(inference.gap)}" if inference.gap is not None else "n/a"
    runner_clause = (
        f" vs `{runner}` {_fmt(runner_mean)}" if runner_mean is not None else ""
    )
    pairwise_clause = ""
    if inference.top_pairwise is not None:
        pw = inference.top_pairwise
        pairwise_clause = (
            f"; {pw.harness_a}−{pw.harness_b} Δ={_fmt(pw.mean_delta)} "
            f"(95% CI {_fmt(pw.ci_low)}–{_fmt(pw.ci_high)}; sign-test p={pw.p_value:.2f})"
        )
    return (
        f"- **Harness verdict ({verdict_label})**: `{leader}` — {mean_clause} "
        f"({gap_clause}{runner_clause}; paired n={inference.n_models} models"
        f"{pairwise_clause})."
    )


def build_inference_summary_markdown(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Deterministic harness inference block for meta-analysis sections 0.1 and 3."""
    primary = calculate_harness_inference(reports, label="primary")
    if primary is None:
        return "## Harness inference summary\n\n*(no cross-harness cell means)*\n"

    lines = [
        "## Harness inference summary",
        "",
        "Copy this block into **section 3** below the harness ranking table. "
        "The **Harness verdict** bullet in section 1 must match the verdict here.",
        "",
        f"**Primary cohort:** cross-harness grid; effective paired n={primary.n_models} models "
        "(cell means, not replicate rows).",
        "",
        "| Harness | Cell-mean avg | 95% CI | Model wins |",
        "|---|---:|---|---:|",
    ]
    win_map = dict(primary.win_counts)
    for harness, avg, lo, hi in primary.harness_means:
        lines.append(
            f"| {harness} | {_fmt(avg)} | {_fmt(lo)}–{_fmt(hi)} | "
            f"{win_map.get(harness, 0)}/{primary.n_models} |"
        )
    lines.append("")
    lines.append(f"**Verdict:** `{primary.verdict}` — leader `{primary.leader}`.")
    if primary.top_pairwise is not None:
        pw = primary.top_pairwise
        lines.append(
            f"Pairwise `{pw.harness_a}`−`{pw.harness_b}`: Δ={_fmt(pw.mean_delta)} "
            f"(95% CI {_fmt(pw.ci_low)}–{_fmt(pw.ci_high)}; sign-test p={pw.p_value:.2f}; "
            f"n={pw.n_models} models)."
        )
    if primary.largest_spread_dimension is not None:
        idx, label = primary.largest_spread_dimension
        lines.append(
            f"Largest harness dimension spread: D{idx} {label} (contest cohort)."
        )

    return "\n".join(lines) + "\n"


def build_research_questions_skeleton(
    reports: list[ParsedReport],
) -> str:
    """Section 0.1 research questions filled from primary inference."""
    inference = calculate_harness_inference(reports)
    verdict = inference.verdict if inference else "insufficient-data"
    n_models = inference.n_models if inference else 0
    lines = [
        "## Research questions skeleton",
        "",
        "Copy into **section 0.1** immediately after methodology.",
        "",
        "### 0.1 Research questions & endpoints",
        "",
        "| Item | Definition |",
        "|---|---|",
        "| **Primary endpoint** | Cell-mean audit total per `(harness, model_slug)` "
        "on the cross-harness open-weight grid |",
        "| **Primary estimand** | Harness effect = mean of per-model cell-mean deltas "
        f"(paired on model slug; n={n_models} models in this run) |",
        f"| **Decision rule** | Harness verdict `{verdict}` from **Harness inference "
        "summary** (copy verbatim; do not override with replicate-level averages) |",
    ]
    return "\n".join(lines) + "\n"


def build_limitations_skeleton(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Section 0.2 limitations template."""
    auditors = sorted({r.auditor for r in reports if r.auditor})
    lines = [
        "## Limitations skeleton",
        "",
        "Copy into **section 0.2** immediately after research questions.",
        "",
        "### 0.2 Limitations",
        "",
        "| Limitation | Detail |",
        "|---|---|",
        f"| **Single auditor** | {', '.join(auditors) or 'unknown'} — no inter-rater reliability |",
        "| **LLM rubric scores** | Audit totals are not runtime verification; treat causal "
        "claims as observational |",
    ]
    return "\n".join(lines) + "\n"


def build_cross_harness_summary_table(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Section 4 summary: one row per model with cell means per harness."""
    cohort = _cross_harness_cohort_slugs(reports)
    if not cohort:
        return "## Cross-harness summary (section 4)\n\n*(no paired models)*\n"

    contest_harnesses = [
        h for h in _CONTEST_HARNESS_COLUMN_ORDER if h in _contest_harnesses_in_data(reports)
    ]
    lines = [
        "## Cross-harness summary (section 4)",
        "",
        "Authoritative section 4 table (cell means). Move replicate-level detail to appendix.",
        "",
        "| Model | "
        + " | ".join(h.capitalize() for h in contest_harnesses)
        + " | Best harness | Spread | Needle dim |",
        "|---|" + "|".join(["---:"] * (len(contest_harnesses) + 3)) + "|",
    ]
    rows: list[tuple[float, list[str]]] = []
    for model in sorted(cohort):
        harness_scores: dict[str, float] = {}
        for harness in contest_harnesses:
            avg = _contest_cell_avg_total(reports, harness, model)
            if avg is not None:
                harness_scores[harness] = avg
        if len(harness_scores) < 2:
            continue
        spread = max(harness_scores.values()) - min(harness_scores.values())
        best_harness = max(harness_scores.items(), key=lambda item: item[1])[0]
        cells = [_display_slug(model, display_slug_map)]
        for harness in contest_harnesses:
            score = harness_scores.get(harness)
            cells.append(_fmt(score) if score is not None else "n/a")
        cells.extend(
            [
                best_harness,
                _fmt(spread),
                _needle_dimension_for_model(reports, model),
            ]
        )
        rows.append((spread, cells))
    rows.sort(key=lambda item: item[0], reverse=True)
    for _, cells in rows:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build_harness_effect_summary(
    reports: list[ParsedReport],
) -> str:
    """Section 4b: per-model paired deltas and win counts."""
    inference = calculate_harness_inference(reports)
    cell_means = calculate_cell_means(reports)
    if inference is None or not cell_means:
        return "## Harness effect summary (section 4b)\n\n*(no paired data)*\n"

    matrix = _cell_mean_matrix(cell_means)
    leader = inference.leader
    runner = inference.runner_up
    delta_header = (
        f"Δ({leader}−{runner})"
        if leader and runner
        else "Δ"
    )
    lines = [
        "## Harness effect summary (section 4b)",
        "",
        "Copy into **section 4b**.",
        "",
        f"| Model | {delta_header} | Best harness |",
        "|---|---:|---|",
    ]
    for model in sorted(matrix):
        best_harness = max(matrix[model].items(), key=lambda item: item[1])[0]
        delta = "n/a"
        if leader and runner and leader in matrix[model] and runner in matrix[model]:
            delta = _fmt(matrix[model][leader] - matrix[model][runner])
        lines.append(f"| {model} | {delta} | {best_harness} |")
    if inference.win_counts:
        wins = ", ".join(
            f"`{harness}` {count}/{inference.n_models}"
            for harness, count in inference.win_counts
        )
        lines.extend(["", f"**Model win counts:** {wins}."])
    if inference.largest_spread_dimension is not None:
        idx, label = inference.largest_spread_dimension
        lines.append(
            f"**Largest harness dimension spread:** D{idx} {label}."
        )
    return "\n".join(lines) + "\n"


def _performance_cost_row_data(
    reports: list[ParsedReport],
    harness: str,
    slug: str,
    *,
    source_dirs: list[Path] | None,
) -> tuple[float | None, float | None, float | None]:
    subset = [
        r
        for r in reports
        if r.harness == harness
        and (r.model_slug == slug or cohort_slug(r.model_slug) == slug)
        and r.total is not None
    ]
    totals = [float(r.total) for r in subset]
    if not totals:
        return None, None, None
    mean_total = mean(totals)
    mean_gen = _mean_optional(
        [_report_gen_minutes(r, source_dirs=source_dirs) for r in subset]
    )
    mean_cost = _mean_optional(
        [_report_cost_usd(r, source_dirs=source_dirs) for r in subset]
    )
    return mean_total, mean_gen, mean_cost


def build_practitioner_decisions_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Section 1.5 practitioner picks from deterministic rollup rules."""
    rows: list[PractitionerDecisionRow] = []

    top_cells = _top_contest_cells(reports)
    if top_cells:
        if len(top_cells) == 1:
            cell = top_cells[0]
            _, mean_gen, mean_cost = _performance_cost_row_data(
                reports,
                cell.harness,
                cell.model_slug,
                source_dirs=source_dirs,
            )
            rows.append(
                PractitionerDecisionRow(
                    goal="Max quality (contest)",
                    target=f"{cell.harness}-{_display_slug(cell.model_slug, display_slug_map)}",
                    mean_total=cell.mean_total,
                    gen_minutes=mean_gen,
                    cost_usd=mean_cost,
                    caveat=_single_harness_run_note(reports, cell.model_slug)
                    or "contest-harness cell mean",
                )
            )
        else:
            tied_targets = " / ".join(
                f"{item.harness}-{_display_slug(item.model_slug, display_slug_map)}"
                for item in top_cells
            )
            cell = top_cells[0]
            rows.append(
                PractitionerDecisionRow(
                    goal="Max quality (contest, tie)",
                    target=tied_targets,
                    mean_total=cell.mean_total,
                    gen_minutes=None,
                    cost_usd=None,
                    caveat="tied rank-1 contest cells — see section 2",
                )
            )

    ollama_rows = _ollama_ranking_rows(reports)
    if ollama_rows:
        best = ollama_rows[0]
        cell_avgs: dict[str, float] = best["cell_avgs"]  # type: ignore[assignment]
        best_harness = max(cell_avgs.items(), key=lambda item: item[1])[0]
        best_slug = str(best["slug"])
        mean_total, mean_gen, mean_cost = _performance_cost_row_data(
            reports, best_harness, best_slug, source_dirs=source_dirs
        )
        if mean_total is None:
            mean_total = float(best["avg_total"])  # type: ignore[arg-type]
        rows.append(
            PractitionerDecisionRow(
                goal="Best OSS grid",
                target=f"{best_harness}-{_display_slug(best_slug, display_slug_map)}",
                mean_total=mean_total,
                gen_minutes=mean_gen,
                cost_usd=mean_cost,
                caveat=f"cross-harness OSS leader `{best_slug}`",
            )
        )

    perf_cells = calculate_performance_cost_cells(
        reports, source_dirs=source_dirs, display_slug_map=display_slug_map
    )
    tier_a = [cell for cell in perf_cells if cell.tier == "A"]
    if tier_a:
        cheapest = min(
            tier_a,
            key=lambda cell: _report_cost_usd_for_cell(reports, cell, source_dirs)
            or float("inf"),
        )
        cost = _report_cost_usd_for_cell(reports, cheapest, source_dirs)
        rows.append(
            PractitionerDecisionRow(
                goal="Cheapest Tier-A",
                target=f"{cheapest.harness}-{_display_slug(cheapest.model_slug, display_slug_map)}",
                mean_total=cheapest.mean_total,
                gen_minutes=cheapest.mean_gen_minutes,
                cost_usd=cost,
                caveat="lowest mean cost among Tier-A cells",
            )
        )
        fastest = min(
            (cell for cell in tier_a if _is_benchmark_harness(cell.harness)),
            key=lambda cell: cell.mean_gen_minutes or float("inf"),
            default=None,
        )
        if fastest is not None:
            rows.append(
                PractitionerDecisionRow(
                    goal="Fastest Tier-A (contest)",
                    target=f"{fastest.harness}-{_display_slug(fastest.model_slug, display_slug_map)}",
                    mean_total=fastest.mean_total,
                    gen_minutes=fastest.mean_gen_minutes,
                    cost_usd=_report_cost_usd_for_cell(reports, fastest, source_dirs),
                    caveat="fastest Tier-A contest-harness cell",
                )
            )

    lines = [
        "## Practitioner decisions (section 1.5)",
        "",
        "Copy table into **section 1.5**. Add one narrative sentence per row in prose.",
        "",
        "| Goal | Pick | Score | Time (min) | Cost (USD) | Caveat |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.goal,
                    f"`{row.target}`",
                    _fmt(row.mean_total),
                    _fmt(row.gen_minutes) if row.gen_minutes is not None else "n/a",
                    f"{row.cost_usd:.2f}" if row.cost_usd is not None else "n/a",
                    row.caveat,
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _report_cost_usd_for_cell(
    reports: list[ParsedReport],
    cell: PerformanceCostCell,
    source_dirs: list[Path] | None,
) -> float | None:
    subset = [
        r
        for r in reports
        if r.harness == cell.harness
        and r.model_slug == cell.model_slug
        and r.total is not None
    ]
    return _mean_optional([_report_cost_usd(r, source_dirs=source_dirs) for r in subset])


def build_pareto_efficient_cells_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Tier-A cells not dominated on both time and cost."""
    cells: list[tuple[str, float, float | None, float | None]] = []
    for cell in calculate_performance_cost_cells(
        reports, source_dirs=source_dirs, display_slug_map=display_slug_map
    ):
        if cell.tier != "A":
            continue
        cost = _report_cost_usd_for_cell(reports, cell, source_dirs)
        label = f"{cell.harness}-{_display_slug(cell.model_slug, display_slug_map)}"
        cells.append((label, cell.mean_total, cell.mean_gen_minutes, cost))

    if not cells:
        return "## Pareto-efficient Tier-A cells\n\n*(no Tier-A cells)*\n"

    efficient: list[tuple[str, float, float | None, float | None]] = []
    for idx, candidate in enumerate(cells):
        dominated = False
        for jdx, other in enumerate(cells):
            if idx == jdx:
                continue
            cand_time = candidate[2] if candidate[2] is not None else float("inf")
            cand_cost = candidate[3] if candidate[3] is not None else float("inf")
            other_time = other[2] if other[2] is not None else float("inf")
            other_cost = other[3] if other[3] is not None else float("inf")
            if (
                other[1] >= candidate[1]
                and other_time <= cand_time
                and other_cost <= cand_cost
                and (
                    other[1] > candidate[1]
                    or other_time < cand_time
                    or other_cost < cand_cost
                )
            ):
                dominated = True
                break
        if not dominated:
            efficient.append(candidate)

    lines = [
        "## Pareto-efficient Tier-A cells",
        "",
        "Copy into **section 6** below the performance table. Non-dominated on score, "
        "time, and cost among Tier-A cells.",
        "",
        "| Target | Mean total | Gen-time (min) | Cost (USD) |",
        "|---|---:|---:|---:|",
    ]
    efficient.sort(key=lambda item: (-item[1], item[2] or float("inf")))
    for label, mean_total, gen_min, cost in efficient:
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _fmt(mean_total),
                    _fmt(gen_min) if gen_min is not None else "n/a",
                    f"{cost:.2f}" if cost is not None else "n/a",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


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
    if mean_cost < _QUALITY_PER_DOLLAR_MIN_COST_USD:
        return "n/a"
    return f"{mean_total / mean_cost:.2f}"


def _quality_per_minute(mean_total: float, mean_gen_minutes: float | None) -> str:
    if mean_gen_minutes is None or mean_gen_minutes == 0:
        return "n/a"
    return f"{mean_total / mean_gen_minutes:.2f}"


def calculate_performance_cost_cells(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> tuple[PerformanceCostCell, ...]:
    """Mean performance/cost metrics per ``(harness, model_slug)`` cell."""
    groups = _group_reports_by_harness_model(reports)
    cells: list[PerformanceCostCell] = []
    for (harness, slug), subset in sorted(groups.items()):
        totals = [float(r.total) for r in subset if r.total is not None]
        if not totals:
            continue
        mean_total = mean(totals)
        mean_gen = _mean_optional(
            [_report_gen_minutes(r, source_dirs=source_dirs) for r in subset]
        )
        qpm = (
            mean_total / mean_gen
            if mean_gen is not None and mean_gen > 0
            else None
        )
        cells.append(
            PerformanceCostCell(
                harness=harness,
                model_slug=slug,
                mean_total=mean_total,
                mean_gen_minutes=mean_gen,
                quality_per_minute=qpm,
                tier=_tier_from_total(mean_total),
            )
        )
    return tuple(cells)


def rank_contest_tier_a_by_quality_per_minute(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
    top_n: int = 5,
) -> tuple[PerformanceCostCell, ...]:
    """Tier-A contest-harness cells ranked by quality per minute (descending)."""
    tier_a = [
        cell
        for cell in calculate_performance_cost_cells(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        )
        if cell.tier == "A"
        and cell.quality_per_minute is not None
        and _is_benchmark_harness(cell.harness)
    ]
    tier_a.sort(key=lambda cell: cell.quality_per_minute or 0.0, reverse=True)
    return tuple(tier_a[:top_n])


def calculate_quality_time_tradeoff(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> QualityTimeTradeoffExpectation | None:
    """Best Tier-A quality-per-minute overall and on contest harnesses only."""
    tier_a = [
        cell
        for cell in calculate_performance_cost_cells(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        )
        if cell.tier == "A" and cell.quality_per_minute is not None
    ]
    if not tier_a:
        return None

    best_overall = max(tier_a, key=lambda cell: cell.quality_per_minute or 0.0)
    contest = [
        cell
        for cell in tier_a
        if _is_benchmark_harness(cell.harness)
    ]
    best_contest = (
        max(contest, key=lambda cell: cell.quality_per_minute or 0.0)
        if contest
        else None
    )
    return QualityTimeTradeoffExpectation(
        overall_harness=best_overall.harness,
        overall_model_slug=_display_slug(
            best_overall.model_slug, display_slug_map
        ),
        overall_mean_total=best_overall.mean_total,
        overall_gen_minutes=float(best_overall.mean_gen_minutes or 0.0),
        overall_quality_per_minute=float(best_overall.quality_per_minute or 0.0),
        contest_harness=best_contest.harness if best_contest else None,
        contest_model_slug=(
            _display_slug(best_contest.model_slug, display_slug_map)
            if best_contest
            else None
        ),
        contest_mean_total=best_contest.mean_total if best_contest else None,
        contest_gen_minutes=(
            float(best_contest.mean_gen_minutes or 0.0) if best_contest else None
        ),
        contest_quality_per_minute=(
            float(best_contest.quality_per_minute or 0.0)
            if best_contest
            else None
        ),
    )


_METHODOLOGY_RUBRIC_MAX: tuple[int, ...] = (15, 10, 10, 10, 5, 10, 15, 5, 10, 10)


def _methodology_rubric_table() -> str:
    lines = [
        "| Dim | Dimension | Max pts |",
        "|---|---|---:|",
    ]
    for index, (label, max_pts) in enumerate(
        zip(DEFAULT_DIMENSION_LABELS, _METHODOLOGY_RUBRIC_MAX),
        start=1,
    ):
        lines.append(f"| D{index} | {label} | {max_pts} |")
    lines.append("| **Total** | | **100** |")
    return "\n".join(lines)


def _methodology_harness_comparison_table(
    reports: list[ParsedReport],
    *,
    n_replicates: int,
) -> str:
    """Paired harness-inference steps for methodology."""
    contest = _contest_harnesses_label(reports)
    n_models = len(_cross_harness_cohort_slugs(reports))
    return "\n".join(
        [
            "| Step | Operation |",
            "|---|---|",
            f"| 1 — **Grid execution** | Each Ollama Cloud model in the grid "
            f"runs under every contest harness (`{contest}`) — same brief, same "
            "backend model, different agent CLI per column |",
            f"| 2 — **Cell aggregation** | Mean audit total per `(harness, model)` "
            f"cell across {n_replicates} independent replicates |",
            "| 3 — **Per-model pairing** | For each model **row**, compute "
            "Δ(leader−runner) between harness column means — model held constant, "
            "harness varies |",
            f"| 4 — **Harness effect** | Average Δ across all {n_models} paired "
            "model rows; bootstrap 95% CI on the n paired deltas |",
            "| 5 — **Verdict** | Two-sided exact sign test on paired Δ → "
            "`decisive` / `marginal` / `tie` / `insufficient-data` (section 3) |",
        ]
    )


def _methodology_cohort_stats(
    reports: list[ParsedReport],
) -> dict[str, int]:
    """Counts for the cross-harness contest cohort used in harness ranking."""
    cohort_slugs = _cross_harness_cohort_slugs(reports)
    contest_harnesses = _contest_harnesses_in_data(reports)
    cohort_audits = [
        r
        for r in reports
        if _is_benchmark_harness(r.harness)
        and cohort_slug(r.model_slug) in cohort_slugs
        and r.total is not None
    ]
    replicate_counts: list[int] = []
    for harness in contest_harnesses:
        for slug in cohort_slugs:
            cell_n = sum(
                1
                for r in cohort_audits
                if r.harness == harness and cohort_slug(r.model_slug) == slug
            )
            if cell_n:
                replicate_counts.append(cell_n)
    return {
        "n_cohort_models": len(cohort_slugs),
        "n_contest_harnesses": len(contest_harnesses),
        "n_cohort_audits": len(cohort_audits),
        "n_replicates_per_cell": max(replicate_counts) if replicate_counts else 0,
    }


def build_methodology_skeleton(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Deterministic methodology intro for meta-analysis section 0."""
    parsed = sum(1 for report in reports if report.total is not None)
    contest = _contest_harnesses_label(reports)
    with_time = sum(
        1
        for report in reports
        if report.total is not None
        and _report_gen_minutes(report, source_dirs=source_dirs) is not None
    )
    cohort = _methodology_cohort_stats(reports)
    n_models = cohort["n_cohort_models"]
    n_harnesses = cohort["n_contest_harnesses"]
    n_replicates = cohort["n_replicates_per_cell"]
    n_cohort_audits = cohort["n_cohort_audits"]
    lines = [
        "## Methodology skeleton",
        "",
        "Copy this block into **Methodology** immediately after the document title.",
        "",
        "### Benchmark task",
        "",
        "Every agent receives the same fixed implementation brief: build a "
        "**ChatGPT-style single-page chat web app** from an empty workspace — "
        "autonomously, with no human confirmation.",
        "",
        "The user types a message in the browser; the app forwards it over a "
        "WebSocket to a Django Channels consumer, which calls **LangChain "
        "`ChatOllama`** against a **local Ollama** server and streams tokens "
        "back to the UI in real time. HTMX (with the WebSocket extension) patches "
        "the chat transcript as chunks arrive; Tailwind CSS styles the page.",
        "",
        "The brief is deliberately demanding: agents must deliver a runnable "
        "**ASGI** stack (not API-only), real streaming (no stubbed responses), "
        "env-driven Ollama configuration, pytest coverage, static-analysis "
        "tooling, Docker + compose with production hardening, and a documented "
        "README — while avoiding forbidden shortcuts (no DRF, no auth, no Celery).",
        "",
        "| Layer | What agents build |",
        "|---|---|",
        "| Backend | Django + Django Channels (`AsyncWebsocketConsumer`) |",
        "| LLM integration | `langchain-ollama` `ChatOllama` → "
        "`OLLAMA_HOST` / `OLLAMA_MODEL` from env |",
        "| Streaming path | Ollama → LangChain `.astream()` → WebSocket → browser |",
        "| Frontend | Single-page chat UI — HTMX + Tailwind CSS (built static assets) |",
        "| Quality & ops | Docker/compose, pytest, ruff/mypy/bandit/coverage, "
        "healthchecks, non-root container |",
        "",
        "### Experimental design",
        "",
        "The campaign answers **two independent questions**. Every benchmark run "
        "is one `(harness, model, replicate)` execution: two sequential phases "
        "(implementation, then cold validation) with **no session continuity** "
        "between them.",
        "",
        "| Question | Section | How it is tested |",
        "|---|---|---|",
        "| **Which harness is best?** | 3 | Run the **same** Ollama Cloud models "
        f"under every contest harness (`{contest}`) — {n_replicates} independent "
        "runs per `(harness, model)` cell — then compare harnesses **across rows** "
        "(same backend model, different agent CLI) |",
        "| **Which model is best?** | 2 | For **every** `(harness, model)` "
        f"combination, run {n_replicates} independent implementations; rank cells "
        "by the **mean audit score** across those replicates (no cross-harness "
        "pairing required) |",
        "",
        "**Harness ranking (section 3).** "
        f"{n_models} open-weight Ollama models form the cross-harness grid: each "
        "model is executed under Claude Code, Codex, and OpenCode, "
        f"{n_replicates} times per harness. Cell mean = average of those "
        f"{n_replicates} audit scores. Harnesses are compared **row by row** — "
        "for `glm_5_2`, compare claude vs codex vs opencode on the same model; "
        "repeat for every grid model; aggregate paired deltas for the harness "
        "verdict.",
        "",
        "**Model ranking (section 2).** Each `(harness, model)` pair — whether "
        "proprietary (`claude_opus_4_8` under claude) or open-weight (`glm_5_2` "
        "under codex) — gets its own cell mean from "
        f"{n_replicates} independent runs. Cells are ranked by that mean. "
        "Open-source models on the shared grid also get a cross-harness average "
        "(section 2a).",
        "",
        "| Phase | Goal | Continuity |",
        "|---|---|---|",
        "| 1 — Implementation | Greenfield build from the fixed brief | — |",
        "| 2 — Validation | Install deps, run tests/static checks, boot ASGI, "
        "build Docker images | Cold start (no phase-1 session) |",
        "",
        "### Assessment protocol",
        "",
        "A separate LLM auditor reads each generated codebase and assigns a "
        "**100-point rubric score**. The auditor verifies API claims against "
        "installed package source, records per-dimension evidence, and flags "
        "auto-critical failures. This meta-analysis aggregates those audit "
        "scores; it does not re-grade projects.",
        "",
        _methodology_rubric_table(),
        "",
        "### Cohort and comparability",
        "",
        "Harness rankings compare agent CLIs **only on the cross-harness Ollama "
        "grid** — models that appear under every contest harness. Proprietary "
        "single-harness models and Cursor Agent runs are reported separately "
        "and excluded from paired harness inference.",
        "",
        "| Comparison | Scope | What varies | What is held constant |",
        "|---|---|---|---|",
        f"| **Contest harness ranking** | {{{contest}}} × Ollama grid | Agent CLI "
        "(harness column) | Backend Ollama model (grid row) |",
        "| **Cross-harness model ranking** | Same slug across harnesses | Backend "
        "model (row) | Harness mix averaged across columns |",
        "| **Cell aggregation** | One `(harness, model)` intersection | — | Mean "
        "of replicate scores; spread = σ across replicates |",
        "",
        "### Cross-harness Ollama grid",
        "",
        "Each **row** is one open-weight Ollama Cloud model; each **column** is "
        "one contest harness. Every intersection is an independent "
        f"`(harness, model)` cell ({n_replicates} replicates × 2 phases each). "
        "Read across a row to compare harnesses on the **same** model; read down "
        "a column to compare models under one harness.",
        "",
        "### How contest harnesses are compared",
        "",
        "Harness inference is **paired on model slug**: each Ollama row supplies "
        "one matched observation per harness, so backend-model capability "
        "differences cancel when averaging row-wise deltas.",
        "",
        _methodology_harness_comparison_table(
            reports,
            n_replicates=n_replicates,
        ),
        "",
        "**Excluded from pairing:** proprietary anchors (`claude_opus_*`, "
        "`codex_gpt_*`, `claude_sonnet_*`, etc.) and `cursor` runs — they do not "
        "fill every harness column and cannot isolate harness effects.",
        "",
        "**This run:**",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Scored audit reports | {parsed} |",
        f"| With recorded generation time | {with_time} |",
        f"| Harness-ranking cohort audits | {n_cohort_audits} |",
        f"| Open-weight models (cross-harness grid) | {n_models} |",
        f"| Contest harnesses | {n_harnesses} |",
        f"| Replicates per cell | {n_replicates} |",
        "",
        "Grid layout: "
        + (
            f"{n_models} models × {n_replicates} replicates × {n_harnesses} "
            f"harnesses = {n_cohort_audits} cohort audits."
            if n_cohort_audits
            else "No cross-harness model grid is available for harness ranking."
        ),
        "",
        "### Derived metrics",
        "",
        "| Metric | Definition |",
        "|---|---|",
        "| **Generation time** | Wall-clock elapsed for phase 1 + phase 2 |",
        "| **Estimated cost (USD)** | Counterfactual per-token estimate from "
        "``docs/PRICING.md`` (OpenRouter list rates where published; "
        "proxy/estimated rates when not available outside subscription). All runs "
        "used provider subscription access; costs are not actual invoices. |",
        "| **Quality–time tradeoff** | Tier-A cells (mean ≥ 81/100) ranked by "
        "mean total ÷ mean generation time (min); higher = better speed-adjusted "
        "output (section 6) |",
        "| **Performance tier** | A: 81–100 · B: 61–80 · C: 41–60 · D: 0–40 "
        "(applied to mean cell totals) |",
    ]
    return "\n".join(lines) + "\n"


def build_quality_time_tradeoff_table(
    reports: list[ParsedReport],
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
    top_n: int = 5,
) -> str:
    """Contest-harness Tier-A quality–time leaderboard for section 1 / section 6."""
    ranked = rank_contest_tier_a_by_quality_per_minute(
        reports,
        source_dirs=source_dirs,
        display_slug_map=display_slug_map,
        top_n=top_n,
    )
    if not ranked:
        return ""

    lines = [
        "**Best quality–time (contest harnesses, Tier-A only):**",
        "",
        "| Rank | Target | Score | Gen-time (min) | Pts/min |",
        "|---:|---|---:|---:|---:|",
    ]
    for rank, cell in enumerate(ranked, start=1):
        target = f"{cell.harness}-{_display_slug(cell.model_slug, display_slug_map)}"
        lines.append(
            f"| {rank} | `{target}` | {_fmt(cell.mean_total)} | "
            f"{_fmt(cell.mean_gen_minutes)} | {_fmt(cell.quality_per_minute)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _quality_time_tradeoff_bullet(
    tradeoff: QualityTimeTradeoffExpectation,
) -> str:
    overall_target = f"{tradeoff.overall_harness}-{tradeoff.overall_model_slug}"
    overall_clause = (
        f"`{overall_target}` — {_fmt(tradeoff.overall_mean_total)}/100 in "
        f"{_fmt(tradeoff.overall_gen_minutes)} min "
        f"({_fmt(tradeoff.overall_quality_per_minute)} pts/min)"
    )
    if (
        tradeoff.contest_harness is not None
        and tradeoff.contest_model_slug is not None
        and tradeoff.contest_mean_total is not None
        and tradeoff.contest_gen_minutes is not None
        and tradeoff.contest_quality_per_minute is not None
    ):
        contest_target = (
            f"{tradeoff.contest_harness}-{tradeoff.contest_model_slug}"
        )
        same_cell = (
            tradeoff.contest_harness == tradeoff.overall_harness
            and tradeoff.contest_model_slug == tradeoff.overall_model_slug
        )
        if same_cell:
            contest_clause = "also best on contest harnesses"
        else:
            contest_clause = (
                f"best on contest harnesses: `{contest_target}` — "
                f"{_fmt(tradeoff.contest_mean_total)}/100 in "
                f"{_fmt(tradeoff.contest_gen_minutes)} min "
                f"({_fmt(tradeoff.contest_quality_per_minute)} pts/min)"
            )
        return (
            f"- **Best quality–time tradeoff**: {overall_clause}; "
            f"{contest_clause} (Tier-A quality per minute; section 6)."
        )
    return (
        f"- **Best quality–time tradeoff**: {overall_clause} "
        f"(Tier-A quality per minute; section 6)."
    )


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



def _dimension_signal_harness_avg_map(
    harness_averages: tuple[DimensionHarnessAverage, ...],
) -> dict[str, float | None]:
    return {item.harness: item.avg_score for item in harness_averages}


def build_dimension_signal_section(reports: list[ParsedReport]) -> str:
    """Precomputed section-5 dimension table for the meta-analysis prompt."""
    signals = calculate_dimension_signals(reports)
    if not signals:
        return "## Dimension-level signal (precomputed)\n\n*(no contest reports parsed)*\n"

    harnesses = [
        h
        for h in _CONTEST_HARNESS_COLUMN_ORDER
        if h in _contest_harnesses_in_data(reports)
    ]
    header = ["Dim", "Dimension", "Max", "Universal avg"]
    header.extend(h.capitalize() for h in harnesses)
    header.append("Classify")

    lines = [
        "## Dimension-level signal (precomputed)",
        "",
        "Copy this table into section 5 verbatim (averages and Classify labels).",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(
            ["---", "---"] + ["---:"] * (2 + len(harnesses)) + ["---"]
        ) + "|",
    ]
    for row in signals:
        avg_by_harness = _dimension_signal_harness_avg_map(row.harness_averages)
        cells = [
            f"D{row.index}",
            row.label,
            str(row.max_score) if row.max_score is not None else "?",
            _fmt(row.all_avg),
        ]
        cells.extend(_fmt(avg_by_harness.get(harness)) for harness in harnesses)
        cells.append(f"**{row.classification}**")
        lines.append("| " + " | ".join(cells) + " |")
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
        "All generation runs used provider subscription access; **Cost (USD)** is a",
        "counterfactual estimate from ``docs/PRICING.md`` (OpenRouter list rates",
        "where published, or proxy/estimated rates when not available outside",
        "subscription billing) — not actual subscription invoices.",
        "``Quality per $`` is ``n/a`` when mean cost < "
        f"${_QUALITY_PER_DOLLAR_MIN_COST_USD:.2f} (misleading ratios).",
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


def _top_contest_cells(
    reports: list[ParsedReport],
) -> tuple[AggregatedRunRankingRow, ...]:
    """All contest-harness cells tied at rank 1 by mean total."""
    ranked = [
        row
        for row in calculate_aggregated_runs_ranking(reports)
        if _is_benchmark_harness(row.harness)
    ]
    if not ranked:
        return ()
    best_total = ranked[0].mean_total
    return tuple(row for row in ranked if row.mean_total == best_total)


def _top_contest_cell(
    reports: list[ParsedReport],
) -> AggregatedRunRankingRow | None:
    """Rank-1 contest ``(harness, model_slug)`` by mean total across replicates."""
    cells = _top_contest_cells(reports)
    return cells[0] if cells else None


def _best_model_overall_bullet(
    reports: list[ParsedReport],
    *,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    cells = _top_contest_cells(reports)
    if not cells:
        return "- **Best model overall**: no contest-harness runs with parseable totals."

    cell = cells[0]
    std_clause = (
        f", std dev {_fmt(cell.std_dev)}" if cell.std_dev is not None else ""
    )
    note = _single_harness_run_note(reports, cell.model_slug)
    note_clause = f"; {note}" if note else ""

    if len(cells) == 1:
        display_slug = _display_slug(cell.model_slug, display_slug_map)
        return (
            f"- **Best model overall**: `{display_slug}` — "
            f"{_fmt(cell.mean_total)}/100 mean under `{cell.harness}` "
            f"(N={cell.sample_n}{std_clause}{note_clause})."
        )

    leader_parts = [
        f"`{_display_slug(item.model_slug, display_slug_map)}` under `{item.harness}`"
        for item in cells
    ]
    leaders = " and ".join(leader_parts)
    tie_note = _single_harness_run_note(reports, cell.model_slug)
    if tie_note:
        tie_note = tie_note.replace("anchor", "anchors")
    tie_note_clause = f"; {tie_note}" if tie_note else ""
    return (
        f"- **Best model overall (tie)**: {leaders} — "
        f"{_fmt(cell.mean_total)}/100 mean each "
        f"(N={cell.sample_n}{std_clause}{tie_note_clause})."
    )


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


def _contest_harness_median_rankings(
    reports: list[ParsedReport],
) -> list[tuple[str, dict[str, float | int | None]]]:
    """Contest harnesses sorted by cross-harness-cohort median total descending."""
    rows: list[tuple[str, dict[str, float | int | None]]] = []
    for harness in _contest_harnesses_in_data(reports):
        stats = _harness_contest_stats(reports, harness)
        if stats["median"] is not None:
            rows.append((harness, stats))
    rows.sort(key=lambda item: float(item[1]["median"]), reverse=True)  # type: ignore[arg-type]
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
        quality_time=calculate_quality_time_tradeoff(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ),
    )


def _top_model_expectation(
    reports: list[ParsedReport], display_slug_map: dict[str, str] | None
) -> TopModelExpectation | None:
    cells = _top_contest_cells(reports)
    if not cells:
        return None
    leaders = tuple(
        (
            cell.harness,
            _display_slug(cell.model_slug, display_slug_map),
            cell.sample_n,
            cell.std_dev,
            _single_harness_run_note(reports, cell.model_slug),
        )
        for cell in cells
    )
    return TopModelExpectation(total=cells[0].mean_total, leaders=leaders)


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
    inference = calculate_harness_inference(reports)
    if inference is not None:
        expectations["harness_verdict"] = inference.verdict
        expectations["harness_verdict_leader"] = inference.leader
        if inference.gap is not None:
            expectations["harness_verdict_gap"] = inference.gap
    if typed.top_model is not None:
        expectations["top_model_total"] = typed.top_model.total
        if typed.top_model.is_tie:
            expectations["top_model_tie"] = True
            expectations["top_model_slugs"] = [
                slug for _, slug, _, _, _ in typed.top_model.leaders
            ]
        else:
            expectations["top_model_slug"] = typed.top_model.model_slug
            expectations["top_model_harness"] = typed.top_model.harness
    if typed.best_ollama is not None:
        expectations["best_ollama_slug"] = typed.best_ollama.model_slug
        expectations["best_ollama_avg"] = typed.best_ollama.avg_total
        expectations["best_ollama_n_harnesses"] = typed.best_ollama.n_harnesses
    if typed.quality_time is not None:
        expectations["quality_time_overall_target"] = (
            f"{typed.quality_time.overall_harness}-"
            f"{typed.quality_time.overall_model_slug}"
        )
        expectations["quality_time_overall_qpm"] = (
            typed.quality_time.overall_quality_per_minute
        )
        if typed.quality_time.contest_harness is not None:
            expectations["quality_time_contest_target"] = (
                f"{typed.quality_time.contest_harness}-"
                f"{typed.quality_time.contest_model_slug}"
            )
            expectations["quality_time_contest_qpm"] = (
                typed.quality_time.contest_quality_per_minute
            )
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

    inference = calculate_harness_inference(reports)
    if inference is not None:
        lines.append(_harness_verdict_bullet(inference))
    else:
        lines.append(
            "- **Harness verdict (insufficient-data)**: no cross-harness cell means — "
            "harness verdict suppressed."
        )

    top_cell = _top_contest_cell(reports)
    if top_cell is not None:
        lines.append(
            _best_model_overall_bullet(reports, display_slug_map=display_slug_map)
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

    quality_time = calculate_quality_time_tradeoff(
        reports,
        source_dirs=source_dirs,
        display_slug_map=display_slug_map,
    )
    if quality_time is not None:
        lines.append(_quality_time_tradeoff_bullet(quality_time))

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
        "Harness-computed from parsed ``report.md`` files. **Section 0 methodology, "
        "sections 0.1–0.2, section 1 verdict bullets, section 1.5, section 2, 2a, "
        "3, 4, 4b, 6, and appendix dimension matrix MUST match these values.** "
        "Use individual reports only for citations and narrative.",
        "",
        build_methodology_skeleton(
            reports, source_dirs=source_dirs
        ).rstrip(),
        "",
        build_research_questions_skeleton(reports).rstrip(),
        "",
        build_limitations_skeleton(
            reports, source_dirs=source_dirs
        ).rstrip(),
        "",
        build_executive_summary_skeleton(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_practitioner_decisions_table(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_inference_summary_markdown(
            reports, source_dirs=source_dirs
        ).rstrip(),
        "",
        build_cross_harness_summary_table(
            reports, display_slug_map=display_slug_map
        ).rstrip(),
        "",
        build_harness_effect_summary(reports).rstrip(),
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
        build_pareto_efficient_cells_table(
            reports,
            source_dirs=source_dirs,
            display_slug_map=display_slug_map,
        ).rstrip(),
        "",
        build_quality_time_tradeoff_table(
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


def _slice_meta_section(text: str, header_pattern: str, *, until: str) -> str | None:
    """Return body text after a legacy or IMRaD Results subsection header."""
    import re

    match = re.search(
        rf"(?:{header_pattern})(.*?)(?={until}|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else None


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
    section = _slice_meta_section(
        text,
        r"#{2,3}\s*2\.\s*Best model overall|###\s*3\.3\s+Model ranking",
        until=r"\n(?:###\s*3\.4|#{2,3}\s+2a\.)",
    )
    if section is None:
        return ["section 2 (Best model overall) not found in meta-analysis.md"]
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
    section = _slice_meta_section(
        text,
        r"#{2,3}\s*2a\.\s*Open-source \(Ollama\) model ranking"
        r"|###\s*3\.4\s+Open-source model ranking",
        until=r"\n(?:###\s*3\.5|#{2,3}\s+3\.)",
    )
    if section is None:
        return [
            "section 2a (Open-source Ollama model ranking) not found in meta-analysis.md"
        ]
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
    section = _slice_meta_section(
        text,
        r"#{2,3}\s*1\.\s*Executive summary|###\s*3\.1\s+Summary of primary findings",
        until=r"\n(?:###\s*3\.2|#{2,3}\s+1\.5\s)",
    )
    if section is None:
        return ["section 1 (Executive summary) not found in meta-analysis.md"]

    section = section.strip()
    errors: list[str] = []

    if not re.search(r"^\s*-\s+\*\*", section, re.MULTILINE):
        errors.append(
            "section 1 is not a bullet list (expected markdown `- **Label**: …` bullets)"
        )

    if "report.md:" in section:
        errors.append("section 1 contains report.md citations (move to later sections)")

    harness_verdict = expectations.get("harness_verdict")
    if isinstance(harness_verdict, str):
        if "Harness verdict" not in section:
            errors.append("section 1 missing **Harness verdict** bullet")
        if f"({harness_verdict})" not in section and f"`{harness_verdict}`" not in section:
            errors.append(
                f"section 1 missing harness verdict label {harness_verdict!r}"
            )

    harness_verdict_leader = expectations.get("harness_verdict_leader")
    if isinstance(harness_verdict_leader, str) and harness_verdict_leader not in section:
        errors.append(
            f"section 1 missing harness verdict leader {harness_verdict_leader!r}"
        )

    best_harness = expectations.get("best_harness")
    best_harness_avg = expectations.get("best_harness_avg")
    if isinstance(best_harness, str) and isinstance(best_harness_avg, float):
        avg_token = _fmt(best_harness_avg)
        if avg_token not in section and harness_verdict not in {"tie", "marginal"}:
            errors.append(
                f"section 1 missing replicate-level harness avg {avg_token} "
                f"for {best_harness!r}"
            )

    top_total = expectations.get("top_model_total")
    top_tie = expectations.get("top_model_tie")
    top_slugs = expectations.get("top_model_slugs")
    top_slug = expectations.get("top_model_slug")
    if top_tie and isinstance(top_slugs, list) and isinstance(top_total, float):
        if "Best model overall (tie)" not in section:
            errors.append("section 1 missing **Best model overall (tie)** bullet")
        total_token = _fmt(top_total)
        if total_token not in section:
            errors.append(
                f"section 1 missing best model overall total {total_token}"
            )
        for slug in top_slugs:
            if not isinstance(slug, str):
                continue
            if slug not in section:
                errors.append(
                    f"section 1 missing tied best model slug {slug!r}"
                )
    elif isinstance(top_slug, str) and isinstance(top_total, float):
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

    quality_target = expectations.get("quality_time_overall_target")
    quality_qpm = expectations.get("quality_time_overall_qpm")
    if isinstance(quality_target, str) and isinstance(quality_qpm, float):
        if "Best quality–time tradeoff" not in section:
            errors.append("section 1 missing **Best quality–time tradeoff** bullet")
        if quality_target not in section:
            errors.append(
                f"section 1 missing quality–time target {quality_target!r}"
            )
        qpm_token = _fmt(quality_qpm)
        if qpm_token not in section:
            errors.append(
                f"section 1 missing quality–time pts/min {qpm_token} "
                f"for {quality_target!r}"
            )
    contest_target = expectations.get("quality_time_contest_target")
    if isinstance(contest_target, str) and contest_target not in section:
        errors.append(
            f"section 1 missing contest quality–time target {contest_target!r}"
        )

    return errors


def validate_meta_analysis_harness_inference(
    meta_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    reports_dir: Path | None = None,
) -> list[str]:
    """Compare section 3 inference block in meta-analysis.md to the rollup."""
    import re

    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    inference = calculate_harness_inference(reports)
    if inference is None or not meta_path.is_file():
        return []

    text = meta_path.read_text(encoding="utf-8")
    section = _slice_meta_section(
        text,
        r"#{2,3}\s*3\.\s*Harness ranking|###\s*3\.5\s+Harness ranking",
        until=r"\n(?:###\s*3\.6|#{2,3}\s+4\.)",
    )
    if section is None:
        return ["section 3 (Harness ranking) not found in meta-analysis.md"]
    errors: list[str] = []
    if f"`{inference.verdict}`" not in section:
        errors.append(
            f"section 3 missing harness inference verdict {inference.verdict!r}"
        )
    if inference.leader and inference.leader not in section:
        errors.append(
            f"section 3 missing inference leader harness {inference.leader!r}"
        )
    if inference.n_models > 0 and f"n={inference.n_models}" not in section.replace(
        " ", ""
    ):
        paired_token = f"paired n={inference.n_models}"
        if paired_token not in section and f"effective paired n={inference.n_models}" not in section:
            errors.append(
                f"section 3 missing paired n={inference.n_models} models note"
            )
    if inference.top_pairwise is not None:
        delta_token = _fmt(inference.top_pairwise.mean_delta)
        if delta_token not in section:
            errors.append(
                f"section 3 missing pairwise delta {delta_token} "
                f"for {inference.top_pairwise.harness_a}−{inference.top_pairwise.harness_b}"
            )
    return errors


def _parse_dimension_signal_classifications(section: str) -> dict[int, str]:
    """Parse section-5 dimension classifications from bullet or table markup."""
    import re

    reported: dict[int, str] = {}
    bullet_re = re.compile(
        r"^\s*-\s*\*\*D(\d+)\b.*?\bClassify:\s*\*\*([^*]+)\*\*",
        re.MULTILINE | re.IGNORECASE,
    )
    for match in bullet_re.finditer(section):
        reported[int(match.group(1))] = match.group(2).strip().lower()

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| D"):
            continue
        parts = [part.strip() for part in stripped.split("|") if part.strip()]
        if len(parts) < 3:
            continue
        dim_match = re.match(r"D(\d+)\b", parts[0], re.IGNORECASE)
        if dim_match is None:
            continue
        classify_match = re.search(r"\*\*([^*]+)\*\*", parts[-1])
        if classify_match is None:
            continue
        reported[int(dim_match.group(1))] = classify_match.group(1).strip().lower()

    return reported


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
    section = _slice_meta_section(
        text,
        r"#{2,3}\s*5\.\s*Dimension-level signal|###\s*3\.9\s+Dimension-level signal",
        until=r"\n(?:###\s*3\.10|#{2,3}\s+[67]\.)",
    )
    if section is None:
        return ["section 5 (Dimension-level signal) not found in meta-analysis.md"]
    reported = _parse_dimension_signal_classifications(section)

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
