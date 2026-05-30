"""Side-by-side audit comparison table builder.

Consumes typed :class:`~benchmark.audit_report.ParsedReport` values from
:mod:`benchmark.audit_report` — never re-parses markdown.
"""

from __future__ import annotations

from pathlib import Path

from benchmark.audit_report import NUM_DIMENSIONS, _collect_reports, _fmt


def build_comparison_table(
    reports_dir: Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
    display_slug_map: dict[str, str] | None = None,
) -> str:
    """Build the side-by-side ``Auditor | Target | D1..D9 | Total | Tier`` table.

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
        auditor = r.auditor
        if display_slug_map is not None:
            auditor = display_slug_map.get(auditor, auditor)
        row = [auditor, r.target]
        for i in range(1, NUM_DIMENSIONS + 1):
            row.append(_fmt(r.dim_score(i)))
        row.append(_fmt(r.total))
        row.append(r.tier or "-")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
