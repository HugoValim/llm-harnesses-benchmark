"""Parse audit ``report.md`` outputs and aggregate them.

The auditor (Claude Code variant) writes a markdown report per (auditor,
target) pair under ``audit-reports/<auditor>/<target>/report.md``. The
report follows the rubric layout in ``prompts/audit_prompt_template.txt``
(sections A-I). This module produces three artifacts from those reports:

- ``build_comparison_table``: side-by-side ``Auditor | Target | D1..D8 |
  Total | Tier`` table. Replaces the broken inline parser previously baked
  into ``run_audit_benchmark.py``.
- ``build_statistical_summary``: regex-derived harness / model / dimension
  rollups. **Not the final analysis** — this is structured input that the
  AI meta-analyst consumes.
- ``run_ai_meta_analysis``: dispatch a configured LLM (harness + model)
  through ``benchmark.claude_code_runner.run_variant`` to read every audit
  report and write the actual meta-analysis to ``meta-analysis.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Iterable

NUM_DIMENSIONS = 8
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
    "Frontend",
    "Architecture",
    "Production readiness",
)


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


def _iter_reports(reports_dir: Path) -> Iterable[ParsedReport]:
    """Yield one parsed report per ``<auditor>/<target>/report.md`` on disk."""
    if not reports_dir.is_dir():
        return
    for auditor_dir in sorted(reports_dir.iterdir()):
        if not auditor_dir.is_dir():
            continue
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
                text, auditor=auditor_dir.name, target=target_dir.name
            )


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


def build_comparison_table(reports_dir: Path) -> str:
    """Build the side-by-side ``Auditor | Target | D1..D8 | Total | Tier`` table.

    Replaces the broken inline parser in ``run_audit_benchmark.py``. Returns
    a complete markdown document (with H1 heading) so callers can write it
    straight to ``comparison.md``.
    """
    reports = list(_iter_reports(reports_dir))
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


def build_statistical_summary(reports_dir: Path) -> str:
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
    """
    reports = list(_iter_reports(reports_dir))
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


def resolve_meta_variant(
    meta_config: dict, harness: str, model_slug: str | None
) -> dict:
    """Look up a meta-analysis variant from a meta-models config.

    The config schema mirrors ``config/audit_models.json``:
    ``{"variants": [{"slug": ..., "main_model": ..., "runner_type": ...,
                     "command_prefix": [...]}]}``.

    Selection rules:
    1. If ``model_slug`` is given, must match a variant's slug exactly.
    2. Variant's ``runner_type`` field (default ``"claude"``) must equal
       ``harness``.
    3. Otherwise the first non-skipped variant with matching runner_type wins.

    Raises ``ValueError`` with a descriptive message on mismatch.
    """
    variants = [
        v for v in meta_config.get("variants", []) if not v.get("skip_by_default")
    ]
    matches_harness = [
        v for v in variants if v.get("runner_type", "claude") == harness
    ]
    if not matches_harness:
        available = ", ".join(
            sorted({v.get("runner_type", "claude") for v in variants})
        ) or "(none)"
        raise ValueError(
            f"No meta-analysis variant with runner_type={harness!r}. "
            f"Available runner_types in config: {available}."
        )
    if model_slug is None:
        return matches_harness[0]
    for v in matches_harness:
        if v["slug"] == model_slug:
            return v
    slugs = ", ".join(v["slug"] for v in matches_harness)
    raise ValueError(
        f"No meta-analysis variant with slug={model_slug!r} under "
        f"runner_type={harness!r}. Available slugs: {slugs}."
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
