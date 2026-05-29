"""Parse audit ``report.md`` outputs and aggregate them.

The auditor writes a markdown report per (auditor,
target) pair under ``audit-reports/<auditor>/<target>/report.md``. The
report follows the rubric layout in ``prompts/audit_prompt_template.txt``
(sections A-I). This module parses individual reports into typed
:class:`ParsedReport` values.

Downstream consumers (comparison tables, statistical rollups, meta-analysis)
live in separate modules — see :mod:`benchmark.audit_comparison`,
:mod:`benchmark.audit_rollup`, and :mod:`benchmark.audit_meta`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from benchmark.result_layout import split_target_slug

NUM_DIMENSIONS = 10
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
    "Code quality (tool-backed)",
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


# Public alias — the parsed representation of one rubric report.md.
RubricResult = ParsedReport


def audit_report_is_complete(report_path: Path) -> bool:
    """True when ``report_path`` exists and contains a parseable total /100."""
    if not report_path.is_file():
        return False
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return parse_report_scores(text).total is not None


def load_rubric_result(report_md_path: Path) -> RubricResult:
    """Parse a single ``report.md`` and return a typed :class:`RubricResult`."""
    return parse_report_scores(
        report_md_path.read_text(),
        auditor=report_md_path.parent.parent.name,
        target=report_md_path.parent.name,
    )


def iter_rubric_results(audit_root: Path) -> Iterable[RubricResult]:
    """Yield :class:`RubricResult` for every ``report.md`` under *audit_root*."""
    yield from _iter_reports(audit_root)


# Regex patterns ---------------------------------------------------------------

# Total score patterns (v3.3+ formatting drift):
#  - "Total score: **89 / 100**"
#  - "## C. Total score / 100\n\n**95 / 100**"
#  - "C. **Total score / 100** — **91 / 100**"
_TOTAL_INLINE_PATTERN = re.compile(
    r"Total(?:\s+score)?\s*[:\n/—-]+\s*\*{0,2}\s*(\d+)\s*/\s*100",
    re.IGNORECASE,
)
_SCORE_OUT_OF_100 = re.compile(r"\*{0,2}\s*(\d+)\s*/\s*100\s*\*{0,2}")
_SECTION_C_INLINE_TOTAL = re.compile(
    r"C\.\s+\*{0,2}Total[^\n]*?[—-]\s*\*{0,2}\s*(\d+)\s*/\s*100",
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
_SECTION_C_HEADING = re.compile(
    r"(?:^|\n)(?:##\s+)?C\.\s+\*{0,2}Total[^\n]*",
    re.IGNORECASE,
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

    total_match = _extract_total(report_text)
    if total_match is not None:
        report.total = total_match

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


def _extract_total(report_text: str) -> int | None:
    """Parse section C total with fallbacks for common markdown drift."""
    inline = _TOTAL_INLINE_PATTERN.search(report_text)
    if inline:
        return int(inline.group(1))

    section_inline = _SECTION_C_INLINE_TOTAL.search(report_text)
    if section_inline:
        return int(section_inline.group(1))

    heading = _SECTION_C_HEADING.search(report_text)
    if heading:
        tail = report_text[heading.end() : heading.end() + 400]
        for match in _SCORE_OUT_OF_100.finditer(tail):
            return int(match.group(1))

    return None


def _split_harness(target: str) -> tuple[str, str]:
    """Split ``claude-foo_bar`` into ``("claude", "foo_bar")``."""
    harness, slug = split_target_slug(target)
    return harness or "unknown", slug


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


# ── re-exports for backward compatibility ────────────────────────────────────
# These symbols moved to domain-specific modules; re-export so existing callers
# don't need import path changes.

from benchmark.audit_comparison import build_comparison_table  # noqa: E402, F401
from benchmark.audit_rollup import (  # noqa: E402, F401
    LEADER_MODEL_SLUG_SUBSTRINGS,
    _avg,
    _cross_harness_model_section,
    _dimension_breakdown_section,
    _harness_section,
    _is_leader_slug,
    _leader_ceiling,
    _max_for_dimension,
    _normalized_scores_section,
    _pct_of_ceiling,
    build_statistical_summary,
    build_model_coverage_table,
    build_precomputed_rollup,
    model_harness_coverage,
    validate_meta_analysis_coverage,
)
from benchmark.audit_meta import (  # noqa: E402, F401
    audit_model_harness,
    build_meta_prompt,
    discover_auditor_subdirs,
    resolve_meta_variant,
    run_ai_meta_analysis,
)
