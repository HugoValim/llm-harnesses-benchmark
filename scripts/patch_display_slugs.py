#!/usr/bin/env python3
"""Patch published markdown to show Codex reasoning effort in model slugs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    build_comparison_table,
    build_statistical_summary,
)
from benchmark.config import build_display_slug_map  # noqa: E402
from benchmark.result_layout import layout_from_repo  # noqa: E402
from benchmark.util import print_line  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run directory under results/ (e.g. run_01).",
    )
    parser.add_argument(
        "--models-config",
        type=Path,
        default=REPO_ROOT / "config" / "models.json",
        help="Model registry for display slug map.",
    )
    parser.add_argument(
        "--auditor",
        default="codex_gpt_5_5",
        help="Auditor slug directory under audit-reports/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    return parser.parse_args()


def _annotated_slugs(display_slug_map: dict[str, str]) -> dict[str, str]:
    """Return only slugs whose display form differs from the canonical slug."""
    return {
        canonical: display
        for canonical, display in display_slug_map.items()
        if display != canonical
    }


def _patch_slug_in_text(text: str, canonical: str, display: str) -> str:
    """Replace bare ``canonical`` slug with ``display`` outside path segments."""
    if canonical not in text:
        return text
    pattern = re.compile(
        rf"(?<![-/]){re.escape(canonical)}(?![-/])"
    )

    def _replace(match: re.Match[str]) -> str:
        start = match.start()
        if start >= len(display) - len(canonical) and text[
            start - (len(display) - len(canonical)) : start
        ].endswith("("):
            return match.group(0)
        return display

    return pattern.sub(_replace, text)


def patch_meta_analysis_text(text: str, display_slug_map: dict[str, str]) -> str:
    """Annotate model slugs in meta-analysis prose and tables."""
    patched = text
    for canonical, display in sorted(
        _annotated_slugs(display_slug_map).items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        patched = _patch_slug_in_text(patched, canonical, display)
    return patched


def rebuild_auditor_comparison(
    auditor_dir: Path,
    *,
    display_slug_map: dict[str, str],
    dry_run: bool,
) -> bool:
    """Rebuild comparison.md for one auditor tree."""
    if not auditor_dir.is_dir():
        print(f"Auditor dir missing: {auditor_dir}", file=sys.stderr)
        return False
    comparison_md = build_comparison_table(
        auditor_dir, display_slug_map=display_slug_map
    )
    statistical_md = build_statistical_summary(
        auditor_dir, display_slug_map=display_slug_map
    )
    output = comparison_md.rstrip() + "\n\n" + statistical_md
    comparison_path = auditor_dir / "comparison.md"
    if dry_run:
        print_line(f"[dry-run] would write {comparison_path}")
        return True
    comparison_path.write_text(output)
    print_line(f"Rebuilt {comparison_path}")
    return True


def patch_meta_analysis_file(
    meta_path: Path,
    *,
    display_slug_map: dict[str, str],
    dry_run: bool,
) -> bool:
    """Patch meta-analysis.md display slugs while preserving path segments."""
    if not meta_path.is_file():
        print(f"Meta-analysis file missing: {meta_path}", file=sys.stderr)
        return False
    original = meta_path.read_text(encoding="utf-8")
    patched = patch_meta_analysis_text(original, display_slug_map)
    if patched == original:
        print_line(f"No display slug changes needed: {meta_path}")
        return True
    if dry_run:
        print_line(f"[dry-run] would patch {meta_path}")
        return True
    meta_path.write_text(patched, encoding="utf-8")
    print_line(f"Patched {meta_path}")
    return True


def main() -> int:
    args = parse_args()
    layout = layout_from_repo(args.run_id, REPO_ROOT)
    display_slug_map = build_display_slug_map(args.models_config)
    auditor_dir = layout.audit_root / args.auditor
    meta_path = layout.run_root / "meta-analysis.md"

    ok = rebuild_auditor_comparison(
        auditor_dir,
        display_slug_map=display_slug_map,
        dry_run=args.dry_run,
    )
    ok = patch_meta_analysis_file(
        meta_path,
        display_slug_map=display_slug_map,
        dry_run=args.dry_run,
    ) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
