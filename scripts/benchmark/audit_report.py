"""Parse audit ``report.md`` outputs and aggregate them.

The auditor writes a markdown report per (auditor,
target) pair under ``audit-reports/<auditor>/<target>/report.md``. The
report follows the rubric layout in ``prompts/audit_prompt_template.txt``
(sections A-I). This module produces three artifacts from those reports:

- ``build_comparison_table``: side-by-side ``Auditor | Target | D1..D9 |
  Total | Tier`` table. Replaces the broken inline parser previously baked
  into ``run_audit_benchmark.py``.
- ``build_statistical_summary``: regex-derived harness / model / dimension
  rollups plus **leader-relative normalized scores** (ceiling = mean of
  configured benchmark-leader model slugs). **Not the final analysis** —
  this is structured input that the AI meta-analyst consumes.
- ``run_ai_meta_analysis``: dispatch a configured LLM (harness + model)
  through the selected harness runner to read every audit
  report and write the actual meta-analysis to ``meta-analysis.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable

NUM_DIMENSIONS = 9
HARNESS_PREFIXES: tuple[str, ...] = ("claude", "codex", "ollama", "opencode")
TIERS: tuple[str, ...] = ("A", "B", "C", "D")

# Default dimension labels, used as fallback when a report's B-section is
# unparseable. Order matches the rubric (audit_prompt_template.txt).
DEFAULT_DIMENSION_LABELS: tuple[str, ...] = (
    "Deliverable completeness",
    "LLM integration",
    "Test quality",
    "Error handling",
    "Persistence / multi-turn",
    "Streaming & frontend",
    "Architecture",
    "Secrets & config hygiene",
    "Production hardening",
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

    Keys: ``\"total\"`` and ``\"1\"``..``\"9\"`` for D1..D9. When no leader
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
        lines.append("| *(no non-leader reports with a parseable total)* | " + " | ".join([""] * (len(nh_header) - 1)) + " |")
    else:
        for _, cells in rows:
            lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("Dimension legend (for D% columns):")
    lines.append("")
    for i, label in enumerate(dim_labels, 1):
        lines.append(f"- **D{i}**: {label}")
    return lines


@dataclass
class DimensionScore:
    index: int
    label: str
    score: int
    max_score: int


@dataclass
class ParsedReport:
    auditor: str
    target: str
    harness: str
    model_slug: str
    total: int | None = None
    tier: str | None = None
    dimensions: list[DimensionScore] = field(default_factory=list)

    def dim_score(self, index: int) -> int | None:
        """Return the score for 1-indexed dimension ``index`` or None."""
        for d in self.dimensions:
            if d.index == index:
                return d.score
        return None


# Regex patterns ---------------------------------------------------------------

# Total score:
#  - "Total score: **89 / 100**"
#  - "Total score\n\n**85 / 100** — Tier A"
#  - "Total: 89/100"
_TOTAL_PATTERN = re.compile(
    r"Total(?:\s+score)?\s*[:\n]+\s*\*{0,2}\s*(\d+)\s*/\s*100",
    re.IGNORECASE,
)

# Tier line:
#  - "Practical tier: **A (81-100)**"
#  - "Practical tier\n\n**A** — ship ..."
#  - "Tier: A"
#  - "Tier A (81-100)"
_TIER_PATTERN = re.compile(
    r"(?:Practical\s+)?tier\s*[:\n]+\s*\*{0,2}\s*([A-D])\b",
    re.IGNORECASE,
)
_TIER_INLINE_PATTERN = re.compile(r"Tier\s+([A-D])\b", re.IGNORECASE)

# Dimension table row:
#   | 1 | Deliverable completeness | 25/25 | ...
#   | D1 | Deliverable completeness | **25 / 25** | ...
_DIM_ROW_PATTERN = re.compile(
    r"^\|\s*\**\s*D?(\d+)\s*\**\s*"
    r"\|\s*\**\s*(.+?)\s*\**\s*"
    r"\|\s*\**\s*(\d+)\s*/\s*(\d+)\s*\**\s*\|",
    re.MULTILINE,
)


def parse_report_scores(
    report_text: str,
    *,
    auditor: str = "",
    target: str = "",
) -> ParsedReport:
    """Extract total, tier, and per-dimension scores from a rubric report.

    Tolerant of formatting drift: bold markers, inline vs newline-separated
    headings, ``D1`` vs ``1`` dimension prefixes. Returns a ``ParsedReport``
    with ``None`` fields when patterns don't match — callers should treat
    missing fields as "unscored", not as zeros.
    """
    harness, model_slug = _split_harness(target)
    report = ParsedReport(
        auditor=auditor,
        target=target,
        harness=harness,
        model_slug=model_slug,
    )

    total_match = _TOTAL_PATTERN.search(report_text)
    if total_match:
        report.total = int(total_match.group(1))

    tier_match = _TIER_PATTERN.search(report_text)
    if tier_match:
        report.tier = tier_match.group(1).upper()
    else:
        inline = _TIER_INLINE_PATTERN.search(report_text)
        if inline:
            report.tier = inline.group(1).upper()

    seen_indices: set[int] = set()
    for m in _DIM_ROW_PATTERN.finditer(report_text):
        idx = int(m.group(1))
        if idx in seen_indices or not (1 <= idx <= NUM_DIMENSIONS):
            continue
        label = m.group(2).strip().strip("*").strip()
        score = int(m.group(3))
        max_score = int(m.group(4))
        report.dimensions.append(DimensionScore(idx, label, score, max_score))
        seen_indices.add(idx)

    report.dimensions.sort(key=lambda d: d.index)
    return report


def _split_harness(target: str) -> tuple[str, str]:
    """Split ``claude-foo_bar`` into ``("claude", "foo_bar")``."""
    for prefix in HARNESS_PREFIXES:
        if target.startswith(f"{prefix}-"):
            return prefix, target[len(prefix) + 1 :]
    return "unknown", target


def _iter_target_reports(
    auditor_dir: Path, *, auditor_name: str
) -> Iterable[ParsedReport]:
    """Yield reports under ``<auditor_dir>/<target>/report.md``."""
    if not auditor_dir.is_dir():
        return
    for target_dir in sorted(auditor_dir.iterdir()):
        if not target_dir.is_dir():
            continue
        report_path = target_dir / "report.md"
        if not report_path.exists():
            continue
        try:
            text = report_path.read_text()
        except OSError:
            continue
        yield parse_report_scores(
            text, auditor=auditor_name, target=target_dir.name
        )


def _iter_reports(reports_dir: Path) -> Iterable[ParsedReport]:
    """Yield parsed reports from an audit output tree.

    Supports two layouts:

    - **Auditor-scoped** (``audit-reports/<auditor>/<target>/report.md``):
      direct children of ``reports_dir`` are targets.
    - **Root** (``audit-reports/<auditor>/<target>/report.md`` with an extra
      auditor level): each direct child of ``reports_dir`` is an auditor dir.
    """
    if not reports_dir.is_dir():
        return
    child_dirs = [c for c in sorted(reports_dir.iterdir()) if c.is_dir()]
    if not child_dirs:
        return
    if any((c / "report.md").exists() for c in child_dirs):
        yield from _iter_target_reports(reports_dir, auditor_name=reports_dir.name)
        return
    for auditor_dir in child_dirs:
        yield from _iter_target_reports(auditor_dir, auditor_name=auditor_dir.name)


def _collect_reports(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
) -> list[ParsedReport]:
    """Gather parsed reports from one tree root or an explicit dir list."""
    if source_dirs is not None:
        reports: list[ParsedReport] = []
        for d in source_dirs:
            reports.extend(_iter_reports(d))
        return reports
    if reports_dir is None:
        return []
    return list(_iter_reports(reports_dir))


def _dimension_labels(reports: list[ParsedReport]) -> list[str]:
    """Derive dimension labels from the first report that has them.

    Falls back to ``DEFAULT_DIMENSION_LABELS`` so the table header is always
    populated even when every report is malformed.
    """
    labels = list(DEFAULT_DIMENSION_LABELS)
    for r in reports:
        if len(r.dimensions) == NUM_DIMENSIONS:
            labels = [d.label for d in r.dimensions]
            break
    return labels


def _fmt(value: float | int | None, *, decimals: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def build_comparison_table(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
) -> str:
    """Build the side-by-side ``Auditor | Target | D1..D9 | Total | Tier`` table.

    Replaces the broken inline parser in ``run_audit_benchmark.py``. Returns
    a complete markdown document (with H1 heading) so callers can write it
    straight to ``comparison.md``.

    Pass ``source_dirs`` to aggregate across multiple auditor-scoped trees
  (e.g. meta-analysis inputs). Otherwise pass ``reports_dir``.
    """
    reports = _collect_reports(reports_dir, source_dirs=source_dirs)
    header_cells = ["Auditor", "Target"]
    header_cells.extend(f"D{i}" for i in range(1, NUM_DIMENSIONS + 1))
    header_cells.extend(["Total", "Tier"])

    lines = [
        "# Audit Comparison Report",
        "",
        "| " + " | ".join(header_cells) + " |",
        "|" + "|".join(["---"] * len(header_cells)) + "|",
    ]

    if not reports:
        lines.append(
            "| *(no reports found)* | "
            + " | ".join([""] * (len(header_cells) - 1))
            + " |"
        )
        return "\n".join(lines)

    for r in reports:
        row = [r.auditor, r.target]
        for i in range(1, NUM_DIMENSIONS + 1):
            row.append(_fmt(r.dim_score(i)))
        row.append(_fmt(r.total))
        row.append(r.tier or "-")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


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

    # Identify best harness by avg total (ties tolerated).
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

    # Reference for which dimension is which.
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

    The sections answer (in order):
    1. Which harness produces better Phase-1 code on average?
    2. For models audited under multiple harnesses, where does harness choice
       move the needle the most?
    3. Which dimensions are universally weak vs harness-specific?

    Pass ``source_dirs`` to aggregate across multiple auditor-scoped trees.
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


# AI-backed meta-analysis dispatch --------------------------------------------

# Type-only import to avoid pulling claude_code_runner at import time (it
# imports a lot of runner machinery we don't need until dispatch time).
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    pass


def audit_model_harness(
    config: dict, slug: str, models_config: dict | None = None
) -> str:
    """Return the first registry harness containing model slug.

    Falls back to auto-derived routing for ollama_cloud models: those are
    auto-included in the claude harness without an explicit harnesses.json entry.

    Example:
        >>> audit_model_harness({"claude": {"models": {"x": {}}}}, "x")
        'claude'
    """
    preferred = ["claude", "codex", "opencode", "cursor"]
    harnesses = preferred + [h for h in config if h not in preferred]
    for harness in harnesses:
        entry = config.get(harness)
        if not isinstance(entry, dict):
            continue
        models = entry.get("models")
        if isinstance(models, dict) and slug in models:
            return str(harness)
    # Derive harness from provider when no explicit harnesses.json entry exists.
    if models_config is not None:
        from benchmark.config import _PROVIDER_HARNESS_MAP  # avoid circular at module level

        registry = models_config.get("models") or []
        _preferred = ["claude", "codex", "opencode", "cursor"]
        for model in registry:
            if not isinstance(model, dict) or model.get("slug") != slug:
                continue
            provider = model.get("provider", "")
            harnesses = _PROVIDER_HARNESS_MAP.get(provider, frozenset())
            if harnesses:
                return min(harnesses, key=lambda h: _preferred.index(h) if h in _preferred else 99)
            if model.get("opencode_id"):
                return "opencode"
    raise ValueError(f"No harness model with slug={slug!r}")


def _meta_row_to_variant(model: dict) -> dict:
    variant = dict(model)
    main_model = variant.get("main_model") or variant.get("id")
    if not isinstance(main_model, str) or not main_model:
        raise ValueError(
            f"meta model row {variant.get('slug')!r} needs string id or main_model"
        )
    variant["main_model"] = main_model
    variant.setdefault("runner_type", variant.get("harness", "claude"))
    return variant


def _meta_config_variants(meta_config: dict) -> list[dict]:
    return [
        _meta_row_to_variant(model)
        for model in meta_config.get("models", [])
        if not model.get("skip_by_default")
    ]


def _meta_variant_harness(variant: dict) -> str:
    value = variant.get("harness") or variant.get("runner_type", "claude")
    return str(value)


def resolve_meta_variant(
    meta_config: dict, harness: str, model_slug: str | None
) -> dict:
    """Look up a meta-analysis model from models config.

    The config is a resolved harness-scoped model list:
    ``{"models": [{"slug": ..., "id": ..., "harness": ...}]}``.

    Selection rules:
    1. If ``model_slug`` is given, must match a model's slug exactly.
    2. Registry row ``harness`` must equal ``harness``.
    3. Otherwise the first non-skipped model with matching harness wins.

    Raises ``ValueError`` with a descriptive message on mismatch.
    """
    variants = _meta_config_variants(meta_config)
    matches_harness = [v for v in variants if _meta_variant_harness(v) == harness]
    if not matches_harness:
        if model_slug is not None and any(v["slug"] == model_slug for v in variants):
            raise ValueError(f"Slug `{model_slug}` is not a {harness} meta model.")
        available = ", ".join(
            sorted({_meta_variant_harness(v) for v in variants})
        ) or "(none)"
        raise ValueError(
            f"No meta-analysis model with harness={harness!r}. "
            f"Available harnesses in config: {available}."
        )
    if model_slug is None:
        return matches_harness[0]
    matches_slug = [v for v in matches_harness if v["slug"] == model_slug]
    if len(matches_slug) == 1:
        return matches_slug[0]
    if len(matches_slug) > 1:
        raise ValueError(
            f"Expected exactly one meta-analysis model with slug={model_slug!r} "
            f"under harness={harness!r}; found {len(matches_slug)}."
        )
    if any(v["slug"] == model_slug for v in variants):
        raise ValueError(f"Slug `{model_slug}` is not a {harness} meta model.")
    slugs = ", ".join(v["slug"] for v in matches_harness)
    raise ValueError(
        f"No meta-analysis model with slug={model_slug!r} under "
        f"harness={harness!r}. Available slugs: {slugs}."
    )


def discover_auditor_subdirs(reports_dir: Path) -> list[Path]:
    """Return the auditor subdirs under ``reports_dir`` that contain reports.

    An auditor subdir is a direct child directory of ``reports_dir`` that:
    - does not start with ``_`` (skips ``_meta-analysis-runs/``),
    - does not start with one of the harness prefixes (``claude-``,
      ``codex-``, ``opencode-``) — those are stray target outputs that
      ended up at the wrong nesting level and should not be globbed,
    - contains at least one ``*/report.md`` file (one report per audited target).

    Returns paths sorted by name. Empty list when ``reports_dir`` does
    not exist or contains no auditor-shaped subdirs.
    """
    if not reports_dir.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(reports_dir.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("_"):
            continue
        if any(name.startswith(f"{p}-") for p in HARNESS_PREFIXES):
            continue
        if not any(child.glob("*/report.md")):
            continue
        found.append(child)
    return found


def _render_audit_input_dirs(dirs: list[Path]) -> str:
    """Render a list of auditor subdirs as a markdown bullet list of absolute paths."""
    return "\n".join(f"- {p.resolve()}" for p in dirs)


def build_meta_prompt(
    template: str,
    *,
    audit_input_dirs: list[Path],
    output_path: Path,
) -> str:
    """Interpolate the meta-analysis prompt template's placeholders.

    The template exposes ``{audit_input_dirs}`` (rendered as a markdown
    bullet list of auditor-scoped directories the meta-analyst must glob
    ``report.md`` files under) and ``{output_path}`` (where it must
    write ``meta-analysis.md``). Pre-aggregated inputs (comparison
    table, statistical summary) are not passed — the LLM is expected
    to inspect the raw reports itself.
    """
    if not audit_input_dirs:
        raise ValueError("audit_input_dirs must be non-empty")
    return (
        template.replace("{audit_input_dirs}", _render_audit_input_dirs(audit_input_dirs))
        .replace("{output_path}", str(output_path.resolve()))
    )


def run_ai_meta_analysis(
    *,
    reports_dir: Path,
    audit_input_dirs: list[Path],
    prompt_template: str,
    variant: dict,
    harness: str,
    runner_command_prefix: list[str] | None = None,
    isolate_home: bool = False,
    timeout_seconds: int = 30 * 60,
    no_progress_timeout_seconds: int = 6 * 60,
    force: bool = False,
) -> dict:
    """Dispatch an LLM to write the meta-analysis markdown file.

    The LLM (selected by ``variant`` + ``harness``) is invoked via the
    Claude Code runner. It receives:
    - ``audit_input_dirs``: one or more auditor subdirs the LLM must
      glob ``*/report.md`` under. When multiple are given, each report
      is an independent sample for its (harness, model) cell; the
      auditor name (parent dir) is an extra axis the LLM can use to
      surface auditor disagreement.
    - The output path it must write to.

    Returns the ``run_variant`` payload. Side effect: the LLM writes
    ``meta-analysis.md`` to ``reports_dir``. No pre-aggregated input file
    is written — the LLM reads the raw audit reports directly.

    Supported harnesses:

    - ``"claude"``: routes to ``claude_code_runner.run_variant``. Natively
      handles ``ollama launch claude`` shims via the variant's
      ``command_prefix``.
    - ``"codex"``: routes to ``benchmark.runner.run_codex_variant`` with the
      Codex CLI.
    - ``"ollama"``: routes to ``run_codex_variant`` and auto-injects
      ``["ollama","launch","codex"]`` as the command prefix.
    """
    if harness not in {"claude", "codex", "ollama"}:
        raise NotImplementedError(
            f"meta-analysis harness={harness!r} not supported; "
            "expected one of 'claude', 'codex', 'ollama'."
        )

    reports_dir = reports_dir.resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs: list[Path] = []
    for d in audit_input_dirs:
        rd = d.resolve()
        if not rd.is_dir():
            raise FileNotFoundError(
                f"audit input dir does not exist or is not a directory: {rd}"
            )
        resolved_inputs.append(rd)
    if not resolved_inputs:
        raise ValueError("audit_input_dirs must be non-empty")
    output_path = reports_dir / "meta-analysis.md"

    prompt = build_meta_prompt(
        prompt_template,
        audit_input_dirs=resolved_inputs,
        output_path=output_path,
    )

    meta_run_dir = reports_dir / "_meta-analysis-runs" / variant["slug"]
    meta_run_dir.mkdir(parents=True, exist_ok=True)
    (meta_run_dir / "prompt.txt").write_text(prompt)

    if harness in {"codex", "ollama"}:
        from benchmark.runner import run_codex_variant  # noqa: PLC0415

        return run_codex_variant(
            variant=variant,
            prompt=prompt,
            results_dir=meta_run_dir.parent,
            timeout_seconds=timeout_seconds,
            no_progress_timeout_seconds=no_progress_timeout_seconds,
            force=force,
            harness=harness,
            explicit_result_dir=meta_run_dir,
        )

    from benchmark.claude_code_runner import run_variant  # noqa: PLC0415

    return run_variant(
        variant=variant,
        prompt=prompt,
        results_dir=meta_run_dir.parent,
        timeout_seconds=timeout_seconds,
        no_progress_timeout_seconds=no_progress_timeout_seconds,
        force=force,
        runner_command_prefix=runner_command_prefix,
        isolate_home=isolate_home,
        explicit_result_dir=meta_run_dir,
    )
