#!/usr/bin/env python3
"""Dispatch an LLM auditor to score benchmark-generated code against a rubric.

Reuses benchmark.claude_code_runner for subprocess lifecycle, NDJSON streaming,
and result serialization. The only differences from the benchmark runner are:
- The prompt is the audit rubric (with {project_dir} and {model_slug} interpolated).
- The output goes to audit-reports/<auditor_slug>/<target_slug>/.
- After all runs, a comparison.md aggregates side-by-side scores.

Auth:
  - Anthropic models use Claude subscription auth (claude login).
  - Non-Anthropic models use ollama launch claude --model <tag>.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.claude_code_runner import run_variant  # noqa: E402
from benchmark.util import load_json, print_line, save_json  # noqa: E402


# Config paths ----------------------------------------------------------------
AUDIT_CONFIG_PATH = REPO_ROOT / "config" / "audit_models.json"
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "claude_code_models.json"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_prompt_template.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"
DEFAULT_BENCHMARK_RESULTS_DIR = REPO_ROOT / "results"


def benchmark_variant_project_dir(benchmark_results_dir: Path, slug: str) -> Path:
    """Resolve generated project dir: prefer ``claude-<slug>/project``, else legacy ``<slug>/project``."""
    prefixed = benchmark_results_dir / f"claude-{slug}" / "project"
    if prefixed.is_dir():
        return prefixed
    return benchmark_results_dir / slug / "project"


def benchmark_variant_has_project(benchmark_results_dir: Path, slug: str) -> bool:
    """True if a benchmark project exists for this variant slug."""
    return benchmark_variant_project_dir(benchmark_results_dir, slug).is_dir()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LLM-powered code audit on benchmark results."
    )
    parser.add_argument(
        "--audit-config",
        default=str(AUDIT_CONFIG_PATH),
        help="Path to audit_models.json (auditor registry).",
    )
    parser.add_argument(
        "--benchmark-config",
        default=str(BENCHMARK_CONFIG_PATH),
        help="Path to claude_code_models.json (target variant registry).",
    )
    parser.add_argument(
        "--prompt",
        default=str(PROMPT_TEMPLATE_PATH),
        help="Path to audit prompt template (must contain {project_dir} and {model_slug} placeholders).",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory where audit reports are written.",
    )
    parser.add_argument(
        "--benchmark-results-dir",
        default=str(DEFAULT_BENCHMARK_RESULTS_DIR),
        help=(
            "Directory where benchmark results live (to locate target project dirs). "
            "Defaults to results/; prefers results/claude-<slug>/project, falls back to results/<slug>/project."
        ),
    )
    parser.add_argument(
        "--auditor",
        action="append",
        default=None,
        help="Select auditor(s) by slug from audit_models.json. Repeatable. Default: all non-skipped.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Select target(s) by slug from claude_code_models.json. Repeatable. "
            "Use 'all' to select every target with an existing project/ dir. "
            "Default: all non-skipped targets that have results."
        ),
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=None,
        help=(
            "(Deprecated — use --auditor and --target instead.) "
            "Select auditor or target variant by slug. Repeatable. "
            "If the slug exists in audit_models.json, it is treated as an AUDITOR. "
            "If it exists in claude_code_models.json, it is treated as a TARGET. "
        ),
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=30,
        help="Per-audit timeout (default: 30). Audits are shorter than builds.",
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=6,
        help="Stall detection threshold (default: 6).",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if cached.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Rebuild comparison.md from existing reports without running.",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Number of concurrent audits (default: 1 = sequential). Use 0 for one worker per job.",
    )
    return parser.parse_args()


def resolve_variant_sets(
    wanted_auditors: set[str] | None,
    wanted_targets: set[str] | None,
    wanted_variants: set[str] | None,
    audit_config: dict,
    benchmark_config: dict,
    benchmark_results_dir: Path,
) -> tuple[list[dict], list[dict]]:
    """Resolve auditor and target lists from CLI flags.

    Precedence:
      1. --auditor / --target (explicit)
      2. --variant (legacy: auto-partition by config membership)
      3. Default: all non-skipped auditors × all targets with existing project/ dirs.
    """
    all_auditors = [
        v for v in audit_config.get("variants", []) if not v.get("skip_by_default")
    ]
    all_targets = [
        v for v in benchmark_config.get("variants", []) if not v.get("skip_by_default")
    ]
    audit_slugs = {v["slug"] for v in all_auditors}
    target_slugs = {v["slug"] for v in all_targets}

    # Mode 1: explicit --auditor / --target
    if wanted_auditors is not None or wanted_targets is not None:
        auditors = [v for v in all_auditors if v["slug"] in (wanted_auditors or set())]
        targets = [v for v in all_targets if v["slug"] in (wanted_targets or set())]

        # Special sentinel: "all" in --target means every target with a project dir
        if wanted_targets and "all" in wanted_targets:
            targets = [
                v
                for v in all_targets
                if benchmark_variant_has_project(benchmark_results_dir, v["slug"])
            ]

        missing_auditors = (wanted_auditors or set()) - audit_slugs - {"all"}
        missing_targets = (wanted_targets or set()) - target_slugs - {"all"}
        if missing_auditors:
            print(
                f"Unknown auditor slug(s): {', '.join(sorted(missing_auditors))}",
                file=sys.stderr,
            )
            print(
                "Available auditors:  " + ", ".join(sorted(audit_slugs)),
                file=sys.stderr,
            )
            sys.exit(1)
        if missing_targets:
            print(
                f"Unknown target slug(s): {', '.join(sorted(missing_targets))}",
                file=sys.stderr,
            )
            print(
                "Available targets:   " + ", ".join(sorted(target_slugs)),
                file=sys.stderr,
            )
            sys.exit(1)
        return auditors, targets

    # Mode 2: legacy --variant (auto-partition by config membership)
    if wanted_variants is not None:
        auditors = [v for v in all_auditors if v["slug"] in wanted_variants]
        targets = [v for v in all_targets if v["slug"] in wanted_variants]
        missing = wanted_variants - audit_slugs - target_slugs
        if missing:
            print(f"Unknown slug(s): {', '.join(sorted(missing))}", file=sys.stderr)
            print(
                "Available auditors:  " + ", ".join(sorted(audit_slugs)),
                file=sys.stderr,
            )
            print(
                "Available targets:   " + ", ".join(sorted(target_slugs)),
                file=sys.stderr,
            )
            sys.exit(1)
        return auditors, targets

    # Mode 3: default — all auditors, all targets with project dirs
    targets = [
        v
        for v in all_targets
        if benchmark_variant_has_project(benchmark_results_dir, v["slug"])
    ]
    return all_auditors, targets


def build_audit_prompt(template: str, project_dir: Path, model_slug: str) -> str:
    """Interpolate placeholders into the audit prompt template."""
    prompt = template.replace("{project_dir}", str(project_dir.resolve()))
    prompt = prompt.replace("{model_slug}", model_slug)
    return prompt


def _build_comparison_table(reports_dir: Path) -> str:
    """Scan audit-reports/*/*/report.md and build a markdown comparison table."""
    lines = [
        "# Audit Comparison Report",
        "",
        "| Auditor | Target | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | Total | Tier |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]

    for auditor_dir in sorted(reports_dir.iterdir()):
        if not auditor_dir.is_dir():
            continue
        auditor_slug = auditor_dir.name
        for target_dir in sorted(auditor_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            target_slug = target_dir.name
            report_path = target_dir / "report.md"
            if not report_path.exists():
                continue
            report_text = report_path.read_text()

            # Extract total score and tier with simple regex
            import re

            total_match = re.search(
                r"Total\s*[:=]\s*(\d+)(?:\s*/\s*100)?", report_text, re.IGNORECASE
            )
            tier_match = re.search(
                r"Tier\s*[:=]\s*([ABCD])", report_text, re.IGNORECASE
            )

            total = total_match.group(1) if total_match else "?"
            tier = tier_match.group(1) if tier_match else "?"

            # Extract dimension scores (look for "1. **Deliverable** (0-25)" → "Score: X/25" or similar)
            dim_scores = []
            for i in range(1, 9):
                # Try multiple patterns
                patterns = [
                    rf"{i}\.\s*\*\*.*?\*\*\s*\((\d+)\).*?\n.*?Score[:=]\s*(\d+)",
                    rf"{i}\.\s*\*\*.*?\*\*.*?\n.*?\((\d+)/\d+\)",
                ]
                score = "?"
                for pat in patterns:
                    m = re.search(pat, report_text, re.DOTALL | re.IGNORECASE)
                    if m:
                        score = (
                            m.group(2)
                            if m.lastindex and m.lastindex >= 2
                            else m.group(1)
                        )
                        break
                dim_scores.append(score)

            lines.append(
                f"| {auditor_slug} | {target_slug} | "
                f"{' | '.join(dim_scores)} | {total} | {tier} |"
            )

    if len(lines) <= 3:
        lines.append("| *(no reports found)* | | | | | | | | | | | |")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    audit_config_path = Path(args.audit_config)
    benchmark_config_path = Path(args.benchmark_config)
    prompt_template_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    benchmark_results_dir = Path(args.benchmark_results_dir)

    if shutil.which("claude") is None:
        print("claude (Claude Code CLI) is not available on PATH", file=sys.stderr)
        return 1

    audit_config = load_json(audit_config_path)
    benchmark_config = load_json(benchmark_config_path)
    prompt_template = prompt_template_path.read_text()

    # Resolve auditor / target sets
    wanted_auditors = set(args.auditor) if args.auditor else None
    wanted_targets = set(args.target) if args.target else None
    wanted_variants = set(args.variant) if args.variant else None
    auditors, targets = resolve_variant_sets(
        wanted_auditors,
        wanted_targets,
        wanted_variants,
        audit_config,
        benchmark_config,
        benchmark_results_dir,
    )

    if not auditors:
        print("No auditors selected.", file=sys.stderr)
        return 1
    if not targets:
        print("No targets selected.", file=sys.stderr)
        return 1

    # Build the cartesian product of jobs
    jobs: list[tuple[dict, dict]] = []
    for auditor in auditors:
        for target in targets:
            jobs.append((auditor, target))

    # Compute effective concurrency
    jobs_count = args.jobs if args.jobs > 0 else len(jobs)
    jobs_count = max(1, min(jobs_count, len(jobs))) if jobs else 1

    print_line(
        f"Audit benchmark: {len(auditors)} auditors × {len(targets)} targets = {len(jobs)} runs, jobs={jobs_count}"
    )

    if not args.report_only:
        timeout_seconds = args.timeout_minutes * 60
        no_progress_timeout_seconds = args.no_progress_minutes * 60
        runner = audit_config.get("runner") or {}
        runner_command_prefix = runner.get("command_prefix")
        isolate_home = bool(runner.get("isolate_home", False))

        def _run(auditor: dict, target: dict) -> tuple[str, str, str | None]:
            auditor_slug = auditor["slug"]
            target_slug = target["slug"]
            job_slug = f"{auditor_slug}__auditing__{target_slug}"

            # Each (auditor, target) pair gets its own result dir
            result_dir = results_dir / auditor_slug / target_slug
            result_dir.mkdir(parents=True, exist_ok=True)

            project_dir = benchmark_variant_project_dir(
                benchmark_results_dir, target_slug
            )
            audit_prompt = build_audit_prompt(prompt_template, project_dir, target_slug)

            # Write the interpolated prompt for debugging
            (result_dir / "prompt.txt").write_text(audit_prompt)

            try:
                payload = run_variant(
                    variant=auditor,
                    prompt=audit_prompt,
                    results_dir=results_dir / auditor_slug,
                    timeout_seconds=timeout_seconds,
                    no_progress_timeout_seconds=no_progress_timeout_seconds,
                    force=args.force,
                    runner_command_prefix=runner_command_prefix,
                    isolate_home=isolate_home,
                    explicit_result_dir=result_dir,
                )
                # The LLM's report is expected in result_dir / "report.md" (it should write it via the Write tool)
                # If the LLM didn't write report.md, we note it.
                report_path = result_dir / "report.md"
                if not report_path.exists():
                    # Fall back: extract the final assistant text from stream.ndjson and save as report
                    stream_path = result_dir / "stream.ndjson"
                    if stream_path.exists():
                        _extract_final_report(stream_path, report_path)

                return job_slug, "ok", None
            except Exception:
                return job_slug, "error", traceback.format_exc()

        def _extract_final_report(stream_path: Path, report_path: Path) -> None:
            """Best-effort: extract the last assistant text block from NDJSON as report."""
            chunks: list[str] = []
            try:
                with stream_path.open() as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "assistant":
                            msg = event.get("message", {})
                            for part in msg.get("content", []):
                                if part.get("type") == "text":
                                    text = part.get("text", "")
                                    if text.strip():
                                        chunks.append(text)
                if chunks:
                    report_path.write_text("\n\n".join(chunks))
            except OSError:
                pass

        if jobs_count == 1 or len(jobs) <= 1:
            for auditor, target in jobs:
                job_slug, status, err = _run(auditor, target)
                if err:
                    print_line(f"[{job_slug}] ERROR:\n{err}")
                else:
                    print_line(f"[{job_slug}] {status}")
        else:
            with ThreadPoolExecutor(max_workers=jobs_count) as pool:
                futures = {
                    pool.submit(_run, a, t): f"{a['slug']}__auditing__{t['slug']}"
                    for a, t in jobs
                }
                for fut in as_completed(futures):
                    job_slug = futures[fut]
                    _, status, err = fut.result()
                    if err:
                        print_line(f"[{job_slug}] ERROR:\n{err}")
                    else:
                        print_line(f"[{job_slug}] {status}")

    # Build comparison report from all existing reports on disk
    comparison_md = _build_comparison_table(results_dir)
    comparison_path = results_dir / "comparison.md"
    comparison_path.write_text(comparison_md)
    print_line(f"Comparison report updated: {comparison_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
