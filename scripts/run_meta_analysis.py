#!/usr/bin/env python3
"""Role 2: AI meta-analysis dispatch.

Reads every ``audit-reports/<auditor>/<target>/report.md`` produced by
``scripts/run_audit.py`` and dispatches an LLM meta-analyst (Claude Code
model) against the full grid. The meta-analyst follows
``prompts/audit_meta_analysis_prompt.txt`` and writes
``audit-reports/<meta_model_slug>/meta-analysis.md`` (best-harness verdict,
best-model verdict, cross-harness model pairings, dimension-level signal,
performance & cost, critical-failure inventory, calibration check,
recommendations). Run artifacts live under the same
``audit-reports/<meta_model_slug>/`` directory.

Before dispatch, ``audit-reports/<meta_model_slug>/comparison.md`` is
rebuilt from the configured input auditor tree(s) so the regex rollup is
always in sync. The AI meta-analyst itself reads the raw ``report.md`` files,
not the rollup.

Auth:
  - Anthropic meta-analysts use Claude subscription auth (``claude login``).
  - Non-Anthropic meta-analysts are routed via
    ``ollama launch claude --model <tag>`` through the model row's
    ``command_prefix`` field in config/models.json.
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
from benchmark.audit_rollup import (  # noqa: E402
    validate_meta_analysis_coverage,
    validate_meta_analysis_ollama_ranking,
)
from benchmark.config import resolve_meta_harness_config  # noqa: E402
from benchmark.defaults import DEFAULT_AUDITOR_SLUG, DEFAULT_AUDIT_HARNESS  # noqa: E402
from benchmark.rate_limit import add_rate_limit_cli_args, rate_limit_policy_from_args  # noqa: E402
from benchmark.timeouts import (  # noqa: E402
    DEFAULT_NO_PROGRESS_MINUTES,
    DEFAULT_TIMEOUT_MINUTES,
)
from benchmark.util import load_json, normalize_path_fields, print_line  # noqa: E402


MODELS_CONFIG_PATH = REPO_ROOT / "config" / "models.json"
META_PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_meta_analysis_prompt.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"


def _required_meta_binary(harness: str, meta_model: dict) -> str:
    command_prefix = meta_model.get("command_prefix") or []
    if harness == "ollama":
        return "ollama"
    if (
        isinstance(command_prefix, list)
        and len(command_prefix) >= 2
        and command_prefix[0] == "ollama"
        and command_prefix[1] == "launch"
    ):
        return "ollama"
    if harness == "codex":
        return "codex"
    return "claude"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Role 2: dispatch an LLM meta-analyst over the per-target audit "
            "reports written by scripts/run_audit.py. Always rebuilds "
            "comparison.md first; writes meta-analysis.md under the meta "
            "output directory."
        )
    )
    parser.add_argument(
        "--models-config",
        default=str(MODELS_CONFIG_PATH),
        help="Path to models.json (shared model registry).",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help=(
            "Root audit-reports directory. Used to resolve relative "
            "--meta-input-dir paths and as the parent of the default "
            "--meta-output-dir."
        ),
    )
    parser.add_argument(
        "--meta-output-dir",
        default=None,
        help=(
            "Directory for meta-analysis outputs (meta-analysis.md, "
            "comparison.md, _meta-analysis-runs/). Default: "
            "<results-dir>/<meta-model slug>."
        ),
    )
    parser.add_argument(
        "--harness",
        default=DEFAULT_AUDIT_HARNESS,
        help=(
            "Meta-analysis dispatch harness slug from harnesses.json "
            f"(default: {DEFAULT_AUDIT_HARNESS})."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_AUDITOR_SLUG,
        help=(
            f"Select one meta-analysis model slug from models.json "
            f"(default: {DEFAULT_AUDITOR_SLUG})."
        ),
    )
    parser.add_argument(
        "--meta-prompt",
        default=str(META_PROMPT_TEMPLATE_PATH),
        help=(
            "Path to meta-analysis prompt template (placeholders: "
            "{audit_input_dirs}, {precomputed_rollup}, {output_path})."
        ),
    )
    parser.add_argument(
        "--meta-input-dir",
        action="append",
        default=None,
        help=(
            "Auditor subdir(s) whose report.md files the meta-analyst reads. "
            "Repeatable. Accepts an absolute path or a name relative to the "
            "results dir (e.g. 'kimi_k2_6_ollama_cloud'). Default: every auditor-"
            "shaped subdir auto-discovered under --results-dir."
        ),
    )
    parser.add_argument(
        "--meta-timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help=f"Timeout for the meta-analysis run (default: {DEFAULT_TIMEOUT_MINUTES}).",
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=DEFAULT_NO_PROGRESS_MINUTES,
        help=f"Stall detection threshold (default: {DEFAULT_NO_PROGRESS_MINUTES}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run the meta-analysis even if a cached payload exists.",
    )
    parser.add_argument(
        "--strict-meta-validation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "After meta-analysis, compare section-2 harness counts against "
            "the deterministic rollup and exit non-zero on mismatch "
            "(default: enabled)."
        ),
    )
    add_rate_limit_cli_args(parser)
    return parser.parse_args()


_META_PATH_FIELDS = (
    "meta_prompt",
    "models_config",
    "results_dir",
)


def normalize_meta_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve relative CLI filesystem paths against the harness checkout."""
    return normalize_path_fields(args, REPO_ROOT, _META_PATH_FIELDS)


def main() -> int:
    args = normalize_meta_paths(parse_args())
    models_config_path = Path(args.models_config)
    results_dir = Path(args.results_dir)
    meta_prompt_path = Path(args.meta_prompt)

    if not meta_prompt_path.exists():
        print(
            f"Meta-analysis prompt template not found: {meta_prompt_path}",
            file=sys.stderr,
        )
        return 1

    models_config = load_json(models_config_path)
    try:
        meta_config = resolve_meta_harness_config(
            models_config, models_config_path, args.harness
        )
    except ValueError as exc:
        print(f"Meta-analysis harness resolution failed: {exc}", file=sys.stderr)
        return 1

    try:
        meta_variant = resolve_meta_variant(
            meta_config, args.harness, args.model
        )
    except ValueError as exc:
        print(f"Meta-analysis model resolution failed: {exc}", file=sys.stderr)
        return 1

    meta_dispatch_harness = str(meta_variant.get("runner_type", args.harness))
    required_binary = _required_meta_binary(meta_dispatch_harness, meta_variant)
    if shutil.which(required_binary) is None:
        print(
            f"{required_binary} is not available on PATH "
            f"(required for --harness {args.harness})",
            file=sys.stderr,
        )
        return 1

    if args.meta_output_dir:
        meta_output_dir = Path(args.meta_output_dir)
        if not meta_output_dir.is_absolute():
            meta_output_dir = (results_dir / meta_output_dir).resolve()
    else:
        meta_output_dir = (results_dir / meta_variant["slug"]).resolve()

    meta_runner = meta_config.get("runner") or {}
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
        if not results_dir.is_dir():
            print(
                f"Results dir does not exist: {results_dir}. "
                "Run scripts/run_audit.py first.",
                file=sys.stderr,
            )
            return 1
        meta_input_dirs = discover_auditor_subdirs(results_dir)
        if not meta_input_dirs:
            print(
                f"No auditor subdirs found under {results_dir}. "
                "Pass --meta-input-dir explicitly or run scripts/run_audit.py first.",
                file=sys.stderr,
            )
            return 1

    # Rebuild the regex rollup under the meta output dir. The AI meta-analyst
    # reads the raw report.md files; this artifact is for humans.
    meta_output_dir.mkdir(parents=True, exist_ok=True)
    comparison_md = build_comparison_table(source_dirs=meta_input_dirs)
    statistical_md = build_statistical_summary(source_dirs=meta_input_dirs)
    comparison_path = meta_output_dir / "comparison.md"
    comparison_path.write_text(comparison_md.rstrip() + "\n\n" + statistical_md)
    print_line(f"Comparison table + statistical summary written: {comparison_path}")

    print_line(
        f"Dispatching AI meta-analysis: harness={args.harness} "
        f"model={meta_variant['slug']} id={meta_variant.get('main_model', '?')} "
        f"input_dirs=[{', '.join(p.name for p in meta_input_dirs)}]"
    )

    try:
        run_ai_meta_analysis(
            reports_dir=meta_output_dir,
            audit_input_dirs=meta_input_dirs,
            prompt_template=meta_prompt_path.read_text(),
            variant=meta_variant,
            harness=meta_dispatch_harness,
            runner_command_prefix=meta_command_prefix,
            isolate_home=meta_isolate_home,
            timeout_seconds=args.meta_timeout_minutes * 60,
            no_progress_timeout_seconds=args.no_progress_minutes * 60,
            force=args.force,
            rate_limit_policy=rate_limit_policy_from_args(args),
        )
    except NotImplementedError as exc:
        print(f"Meta-analysis dispatch failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print_line("Meta-analysis dispatch raised:")
        traceback.print_exc()
        return 1

    meta_output = meta_output_dir / "meta-analysis.md"
    if meta_output.exists():
        print_line(f"AI meta-analysis written: {meta_output}")
    else:
        print_line(
            f"WARNING: meta-analysis run finished but {meta_output} was not written. "
            f"Check {meta_output_dir / '_meta-analysis-runs' / meta_variant['slug']}."
        )
        return 1

    if args.strict_meta_validation:
        coverage_errors = validate_meta_analysis_coverage(
            meta_output,
            source_dirs=meta_input_dirs,
        )
        ollama_errors = validate_meta_analysis_ollama_ranking(
            meta_output,
            source_dirs=meta_input_dirs,
        )
        all_errors = coverage_errors + ollama_errors
        if all_errors:
            print_line("Meta-analysis strict validation failed:")
            for err in all_errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
