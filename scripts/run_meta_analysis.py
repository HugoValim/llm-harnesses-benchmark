#!/usr/bin/env python3
"""Role 2: AI meta-analysis dispatch.

Reads every ``audit-reports/<auditor>/<target>/report.md`` produced by
``scripts/run_audit.py`` and dispatches an LLM meta-analyst (Claude Code
variant) against the full grid. The meta-analyst follows
``prompts/audit_meta_analysis_prompt.txt`` and writes
``audit-reports/meta-analysis.md`` (best-harness verdict, best-model verdict,
cross-harness model pairings, dimension-level signal, performance & cost,
critical-failure inventory, calibration check, recommendations).

Before dispatch, ``audit-reports/comparison.md`` is rebuilt from the existing
reports so the regex rollup is always in sync. The AI meta-analyst itself
reads the raw ``report.md`` files, not the rollup.

Auth:
  - Anthropic meta-analysts use Claude subscription auth (``claude login``).
  - Non-Anthropic meta-analysts are routed via
    ``ollama launch claude --model <tag>`` through the variant's
    ``command_prefix`` field in audit_models.json.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    build_comparison_table,
    build_statistical_summary,
    discover_auditor_subdirs,
    resolve_meta_variant,
    run_ai_meta_analysis,
)
from benchmark.util import load_json, print_line  # noqa: E402


AUDIT_CONFIG_PATH = REPO_ROOT / "config" / "audit_models.json"
META_PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_meta_analysis_prompt.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Role 2: dispatch an LLM meta-analyst over the per-target audit "
            "reports written by scripts/run_audit.py. Always rebuilds "
            "comparison.md first; writes meta-analysis.md to the results dir."
        )
    )
    parser.add_argument(
        "--audit-config",
        default=str(AUDIT_CONFIG_PATH),
        help="Path to audit_models.json (auditor registry; also used for meta variants).",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory containing the per-auditor subdirs with report.md files.",
    )
    parser.add_argument(
        "--meta-harness",
        default="claude",
        choices=("claude", "codex", "ollama"),
        help=(
            "Harness used to dispatch the AI meta-analysis (default: claude). "
            "'codex' runs the meta-analyst via the Codex CLI; 'ollama' wraps "
            "codex with `ollama launch codex` for Ollama Cloud models. "
            "Non-Anthropic Claude variants can still be routed via a "
            "command_prefix (e.g. ['ollama','launch','claude'])."
        ),
    )
    parser.add_argument(
        "--meta-model",
        default=None,
        help=(
            "Variant slug from --audit-config to use for the meta-analysis. "
            "Default: first non-skipped variant whose harness matches "
            "--meta-harness."
        ),
    )
    parser.add_argument(
        "--meta-prompt",
        default=str(META_PROMPT_TEMPLATE_PATH),
        help=(
            "Path to meta-analysis prompt template (placeholders: "
            "{audit_input_dirs}, {output_path})."
        ),
    )
    parser.add_argument(
        "--meta-input-dir",
        action="append",
        default=None,
        help=(
            "Auditor subdir(s) whose report.md files the meta-analyst reads. "
            "Repeatable. Accepts an absolute path or a name relative to the "
            "results dir (e.g. 'kimi_k2_6_ollama_codex'). Default: every auditor-"
            "shaped subdir auto-discovered under --results-dir."
        ),
    )
    parser.add_argument(
        "--meta-timeout-minutes",
        type=int,
        default=30,
        help="Timeout for the meta-analysis run (default: 30).",
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=6,
        help="Stall detection threshold (default: 6).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run the meta-analysis even if a cached payload exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_config_path = Path(args.audit_config)
    results_dir = Path(args.results_dir)
    meta_prompt_path = Path(args.meta_prompt)

    required_binary = {
        "claude": "claude",
        "codex": "codex",
        "ollama": "ollama",
    }[args.meta_harness]
    if shutil.which(required_binary) is None:
        print(
            f"{required_binary} is not available on PATH "
            f"(required for --meta-harness {args.meta_harness})",
            file=sys.stderr,
        )
        return 1

    if not meta_prompt_path.exists():
        print(
            f"Meta-analysis prompt template not found: {meta_prompt_path}",
            file=sys.stderr,
        )
        return 1

    if not results_dir.is_dir():
        print(
            f"Results dir does not exist: {results_dir}. Run scripts/run_audit.py first.",
            file=sys.stderr,
        )
        return 1

    audit_config = load_json(audit_config_path)

    # Rebuild the regex rollup first so comparison.md is in sync. The AI
    # meta-analyst reads the raw report.md files; this artifact is for humans.
    results_dir.mkdir(parents=True, exist_ok=True)
    comparison_md = build_comparison_table(results_dir)
    statistical_md = build_statistical_summary(results_dir)
    comparison_path = results_dir / "comparison.md"
    comparison_path.write_text(comparison_md.rstrip() + "\n\n" + statistical_md)
    print_line(f"Comparison table + statistical summary written: {comparison_path}")

    try:
        meta_variant = resolve_meta_variant(
            audit_config, args.meta_harness, args.meta_model
        )
    except ValueError as exc:
        print(f"Meta-analysis variant resolution failed: {exc}", file=sys.stderr)
        return 1

    meta_runner = audit_config.get("runner") or {}
    meta_command_prefix = meta_runner.get("command_prefix")
    meta_isolate_home = bool(meta_runner.get("isolate_home", False))

    if args.meta_input_dir:
        meta_input_dirs: list[Path] = []
        for raw in args.meta_input_dir:
            candidate = Path(raw)
            resolved = (
                candidate if candidate.is_absolute() else results_dir / candidate
            ).resolve()
            if not resolved.is_dir():
                print(
                    f"Meta-analysis input dir does not exist: {resolved}",
                    file=sys.stderr,
                )
                return 1
            meta_input_dirs.append(resolved)
    else:
        meta_input_dirs = discover_auditor_subdirs(results_dir)
        if not meta_input_dirs:
            print(
                f"No auditor subdirs found under {results_dir}. "
                "Pass --meta-input-dir explicitly or run scripts/run_audit.py first.",
                file=sys.stderr,
            )
            return 1

    print_line(
        f"Dispatching AI meta-analysis: harness={args.meta_harness} "
        f"variant={meta_variant['slug']} model={meta_variant.get('main_model', '?')} "
        f"input_dirs=[{', '.join(p.name for p in meta_input_dirs)}]"
    )

    try:
        run_ai_meta_analysis(
            reports_dir=results_dir,
            audit_input_dirs=meta_input_dirs,
            prompt_template=meta_prompt_path.read_text(),
            variant=meta_variant,
            harness=args.meta_harness,
            runner_command_prefix=meta_command_prefix,
            isolate_home=meta_isolate_home,
            timeout_seconds=args.meta_timeout_minutes * 60,
            no_progress_timeout_seconds=args.no_progress_minutes * 60,
            force=args.force,
        )
    except NotImplementedError as exc:
        print(f"Meta-analysis dispatch failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print_line("Meta-analysis dispatch raised:")
        traceback.print_exc()
        return 1

    meta_output = results_dir / "meta-analysis.md"
    if meta_output.exists():
        print_line(f"AI meta-analysis written: {meta_output}")
    else:
        print_line(
            f"WARNING: meta-analysis run finished but {meta_output} was not written. "
            f"Check {results_dir / '_meta-analysis-runs' / meta_variant['slug']}."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
