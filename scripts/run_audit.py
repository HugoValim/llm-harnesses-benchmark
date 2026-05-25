#!/usr/bin/env python3
"""Role 1: per-project AI audit dispatch.

Reads benchmark outputs under ``results/<harness>-<slug>/project`` and
dispatches an LLM auditor registry row against each, using the
rubric template at ``prompts/audit_prompt_template.txt``. Audit outputs land
in ``audit-reports/<auditor_slug>/<target_slug>/`` (one ``report.md`` per
(auditor, target) pair).

After dispatch, rebuilds ``audit-reports/<auditor_slug>/comparison.md`` per
auditor from that auditor's ``report.md`` files via
:func:`benchmark.audit_report.build_comparison_table` and
:func:`build_statistical_summary`.

This script is the per-project leg of the audit pipeline. The cross-auditor
meta-analysis is its own entry point: ``scripts/run_meta_analysis.py``.

Auth:
  - Anthropic auditors use Claude subscription auth (``claude login``).
  - Non-Anthropic auditors are routed via ``ollama launch claude --model <tag>``
    using the row's ``command_prefix`` field in config/models.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import (  # noqa: E402
    build_comparison_table,
    build_statistical_summary,
    load_rubric_result,
)
from benchmark.harnesses import get_harness  # noqa: E402
from benchmark.audit_coverage import (  # noqa: E402
    audit_dispatch_needed,
    find_audit_coverage_gaps,
    format_coverage_gaps,
)
from benchmark.audit_meta import discover_auditor_subdirs  # noqa: E402
from benchmark.timeouts import (  # noqa: E402
    DEFAULT_NO_PROGRESS_MINUTES,
    DEFAULT_TIMEOUT_MINUTES,
)
from benchmark.config import resolve_audit_harness_config  # noqa: E402

# Runner imports go through the Harness registry; no direct imports needed.
from benchmark.util import (  # noqa: E402
    USAGE_LIMIT_REACHED,
    load_json,
    normalize_path_fields,
    print_line,
    save_json,
)


_CODEX_RUNNER_TYPES: frozenset[str] = frozenset({"codex", "ollama"})


def _verify_auditor_binaries(auditors: list[dict]) -> tuple[bool, str]:
    """Check the PATH binaries required by the selected auditors.

    Each auditor's ``runner_type`` (default ``"claude"``) selects which CLI
    must be available. ``"ollama"`` auditors need ``ollama`` on PATH (codex
    is launched via ``ollama launch codex``); ``"codex"`` needs ``codex``;
    ``"claude"`` needs ``claude``.
    """
    needs_claude = False
    needs_codex = False
    needs_ollama = False
    for a in auditors:
        runner_type = a.get("runner_type", "claude")
        cp = a.get("command_prefix") or []
        if runner_type == "ollama" or (
            len(cp) >= 2 and cp[0] == "ollama" and cp[1] == "launch"
        ):
            needs_ollama = True
        elif runner_type == "codex":
            needs_codex = True
        else:
            needs_claude = True
    if needs_claude and shutil.which("claude") is None:
        return False, "claude (Claude Code CLI) is not available on PATH"
    if needs_codex and shutil.which("codex") is None:
        return False, "codex is not available on PATH"
    if needs_ollama and shutil.which("ollama") is None:
        return False, "ollama is not available on PATH (needed for ollama launch codex)"
    return True, ""


# Config paths ----------------------------------------------------------------
AUDIT_CONFIG_PATH = REPO_ROOT / "config" / "models.json"
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "models.json"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_prompt_template.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"
DEFAULT_BENCHMARK_RESULTS_DIR = REPO_ROOT / "results"


from benchmark.quality_probe import probe as run_quality_probe  # noqa: E402
from benchmark.audit_d10 import (  # noqa: E402
    compute_d10_from_probe,
    format_d10_precomputed_block,
    load_static_analysis,
    reconcile_report_d10,
)
from benchmark.pricing import (  # noqa: E402
    build_generation_metrics,
    format_generation_metrics_block,
    pricing_path,
    validate_section_h_cost,
)
from benchmark.result_layout import (  # noqa: E402
    audit_generation_metrics_json,
    audit_report_md,
    audit_result_json,
    audit_static_analysis_json,
    audit_stream_ndjson,
    audit_target_dir,
    split_target_slug,
)


def discover_project_dirs(
    benchmark_results_dir: Path,
    config_targets_by_slug: dict[str, dict] | None = None,
) -> list[dict]:
    """Scan ``benchmark_results_dir`` for every ``<name>/project`` subdir.

    This is the authoritative audit target set: ``run_audit.py`` audits every
    discovered row by default and exits non-zero when any lack a scored
    ``report.md`` (see ``--no-enforce-coverage``).

    Returns one target dict per discovered project, sorted by dir name:

    - ``slug``: the directory name (e.g. ``claude-kimi_k2_6_ollama_cloud``).
      Used as the audit output dir name; unique by construction.
    - ``model_slug``: the slug with the harness prefix stripped, or the dir
      name itself when no harness prefix is recognised.
    - ``harness``: ``"claude" | "cursor" | "codex" | "ollama" | "opencode" | "unknown"``.
    - ``project_dir``: absolute Path to ``<name>/project``.
    - ``label`` / ``main_model`` / ``selection_reason`` from
      ``config_targets_by_slug[model_slug]`` when available (optional metadata).
    """
    config_targets_by_slug = config_targets_by_slug or {}
    out: list[dict] = []
    if not benchmark_results_dir.is_dir():
        return out
    for entry in sorted(benchmark_results_dir.iterdir()):
        if not entry.is_dir():
            continue
        project_dir = entry / "project"
        if not project_dir.is_dir():
            continue
        name = entry.name
        prefix, model_slug = split_target_slug(name)
        harness = prefix or "unknown"
        target: dict = {
            "slug": name,
            "model_slug": model_slug,
            "harness": harness,
            "project_dir": project_dir,
        }
        extra = config_targets_by_slug.get(model_slug)
        if extra:
            for k in ("label", "main_model", "selection_reason", "provider"):
                if k in extra:
                    target[k] = extra[k]
        out.append(target)
    return out


def _filter_discovered(discovered: list[dict], wanted: set[str]) -> list[dict]:
    """Filter discovered targets by full dirname OR by model_slug.

    ``"all"`` selects every discovered project. A bare model_slug that matches
    multiple harness prefixes (e.g. ``kimi_k2_6_ollama_cloud`` exists under
    ``claude-``, ``codex-``, and ``opencode-``) selects ALL matching dirs —
    callers wanting a single harness must pass the full dirname.
    """
    if "all" in wanted:
        return list(discovered)
    out: list[dict] = []
    for t in discovered:
        if t["slug"] in wanted or t["model_slug"] in wanted:
            out.append(t)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Role 1: dispatch an LLM auditor against every benchmark-generated "
            "project and write a per-target rubric report. Cross-model "
            "meta-analysis is a separate script: scripts/run_meta_analysis.py."
        )
    )
    parser.add_argument(
        "--models-config",
        default=str(AUDIT_CONFIG_PATH),
        help="Path to models.json (shared model registry).",
    )
    parser.add_argument(
        "--harness",
        default="claude",
        help="Audit dispatch harness slug from harnesses.json (default: claude).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Select one audit model slug from models.json.",
    )
    parser.add_argument(
        "--benchmark-config",
        default=str(BENCHMARK_CONFIG_PATH),
        help=(
            "Optional metadata source for discovered targets (label, main_model, "
            "selection_reason matched by model_slug). Targets themselves come "
            "from disk discovery; this flag is no longer used to filter the set."
        ),
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
            "Directory where benchmark results live. Every subdir that contains "
            "a project/ child is treated as a target. Recognised harness "
            "prefixes (claude-, codex-, opencode-) are stripped to derive the "
            "model slug; other dir names are used as-is."
        ),
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Select target(s) by full dirname (e.g. claude-kimi_k2_6_ollama_cloud) "
            "or by bare model slug (matches every harness that has that slug). "
            "Repeatable. Use 'all' to select every discovered project. "
            "Default: every discovered project."
        ),
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help=f"Per-audit timeout (default: {DEFAULT_TIMEOUT_MINUTES}).",
    )
    parser.add_argument(
        "--no-progress-minutes",
        type=int,
        default=DEFAULT_NO_PROGRESS_MINUTES,
        help=f"Stall detection threshold (default: {DEFAULT_NO_PROGRESS_MINUTES}).",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if cached.")
    parser.add_argument(
        "--skip-quality-probe",
        action="store_true",
        help=(
            "Skip the ruff/mypy/bandit/radon static-analysis probe that "
            "produces static-analysis.json for the D10 rubric dimension. "
            "When skipped, D10 is graded as 'unverified' (5/10 default)."
        ),
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Rebuild each auditor's comparison.md from existing reports "
            "without running audits."
        ),
    )
    parser.add_argument(
        "--no-enforce-coverage",
        action="store_true",
        help=(
            "Do not require a scored report.md for every results/ target after "
            "dispatch. Default: exit 1 when any benchmark project lacks a "
            "complete audit for the selected auditor(s)."
        ),
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Number of concurrent audits (default: 1 = sequential). Use 0 for one worker per job.",
    )
    return parser.parse_args()


def _audit_row_to_variant(model: dict[str, Any]) -> dict[str, Any]:
    auditor = dict(model)
    main_model = auditor.get("main_model") or auditor.get("id")
    if not isinstance(main_model, str) or not main_model:
        raise ValueError(
            f"audit model row {auditor.get('slug')!r} needs string id or main_model"
        )
    auditor["main_model"] = main_model
    auditor.setdefault("runner_type", auditor.get("harness", "claude"))
    return auditor


def _audit_config_auditors(
    audit_config: dict[str, Any], harness: str | None
) -> list[dict[str, Any]]:
    return [
        _audit_row_to_variant(model)
        for model in audit_config.get("models", [])
        if not model.get("skip_by_default")
        and (harness is None or model.get("harness", harness) == harness)
    ]


def _all_audit_slugs(audit_config: dict[str, Any]) -> set[str]:
    registry_models = audit_config.get("_registry_models", audit_config.get("models"))
    if registry_models is not None:
        return {str(model["slug"]) for model in registry_models if "slug" in model}
    return set()


def _target_metadata_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("models", []))


def _auditor_dir_has_reports(auditor_dir: Path) -> bool:
    """True when ``auditor_dir`` contains at least one ``<target>/report.md``."""
    return auditor_dir.is_dir() and any(auditor_dir.glob("*/report.md"))


def _write_auditor_comparison(auditor_dir: Path) -> Path:
    """Rebuild ``comparison.md`` for one auditor tree; returns the output path."""
    comparison_md = build_comparison_table(auditor_dir)
    statistical_md = build_statistical_summary(auditor_dir)
    comparison_path = auditor_dir / "comparison.md"
    comparison_path.write_text(comparison_md.rstrip() + "\n\n" + statistical_md)
    return comparison_path


def _auditor_dirs_for_comparison_rollup(
    results_dir: Path,
    auditors: list[dict[str, Any]],
    *,
    report_only: bool,
    wanted_model: str | None,
) -> list[Path]:
    """Return auditor dirs that should get a comparison.md rebuild.

    ``--report-only`` without ``--model`` rolls up every on-disk auditor tree
    that already has reports. Otherwise only the selected auditor slug(s) are
    considered, and trees without any ``report.md`` are skipped.
    """
    if report_only and wanted_model is None:
        return discover_auditor_subdirs(results_dir)
    dirs: list[Path] = []
    for auditor in auditors:
        auditor_dir = results_dir / auditor["slug"]
        if _auditor_dir_has_reports(auditor_dir):
            dirs.append(auditor_dir)
    return dirs


def resolve_auditors_and_targets(
    wanted_model: str | None,
    wanted_targets: set[str] | None,
    audit_config: dict[str, Any],
    benchmark_config: dict[str, Any],
    benchmark_results_dir: Path,
    harness: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Resolve auditor and target lists from CLI flags.

    Auditors come from ``audit_config``. Targets are discovered on disk via
    :func:`discover_project_dirs` and optionally enriched with metadata from
    ``benchmark_config`` when a model_slug matches.

    Default (both wanted sets are None): all non-skipped auditors × every
    discovered project.
    """
    all_auditors = _audit_config_auditors(audit_config, harness)
    audit_slugs = {v["slug"] for v in all_auditors}
    all_audit_slugs = _all_audit_slugs(audit_config)

    config_target_rows = _target_metadata_rows(benchmark_config)
    config_targets_by_slug = {v["slug"]: v for v in config_target_rows}
    discovered = discover_project_dirs(benchmark_results_dir, config_targets_by_slug)
    discovered_dirnames = {t["slug"] for t in discovered}
    discovered_model_slugs = {t["model_slug"] for t in discovered}
    known_target_keys = discovered_dirnames | discovered_model_slugs

    def _emit_unknown_targets(missing: set[str]) -> None:
        print(
            f"Unknown target(s): {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        print(
            "Available dirnames:    " + ", ".join(sorted(discovered_dirnames)),
            file=sys.stderr,
        )
        print(
            "Available model slugs: " + ", ".join(sorted(discovered_model_slugs)),
            file=sys.stderr,
        )

    if wanted_model is not None or wanted_targets is not None:
        auditors = [v for v in all_auditors if v["slug"] == wanted_model]
        targets = _filter_discovered(discovered, wanted_targets or set())

        missing_auditors = {wanted_model} - audit_slugs if wanted_model else set()
        missing_targets = (wanted_targets or set()) - known_target_keys - {"all"}
        if missing_auditors:
            incompatible = missing_auditors & all_audit_slugs
            if incompatible and harness is not None:
                print(
                    f"Slug `{sorted(incompatible)[0]}` is not a {harness} audit model.",
                    file=sys.stderr,
                )
                sys.exit(1)
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
            _emit_unknown_targets(missing_targets)
            sys.exit(1)
        if wanted_model is None:
            auditors = all_auditors
        if wanted_targets is None:
            targets = discovered
        if wanted_model is not None and len(auditors) != 1:
            print(
                f"Expected exactly one audit model for slug={wanted_model!r}; "
                f"found {len(auditors)}.",
                file=sys.stderr,
            )
            sys.exit(1)
        return auditors, targets

    return all_auditors, discovered


def build_audit_prompt(
    template: str,
    project_dir: Path,
    model_slug: str,
    output_path: Path | None = None,
    static_analysis_path: Path | None = None,
    *,
    benchmark_result_path: Path | None = None,
    generation_metrics_path: Path | None = None,
    generation_metrics_block: str | None = None,
    pricing_doc_path: Path | None = None,
    d10_precomputed_block: str | None = None,
) -> str:
    """Interpolate placeholders into the audit prompt template.

    ``{static_analysis_path}`` resolves to the path the probe wrote (or the
    expected path when the probe was skipped) — the auditor opens it as
    evidence for D10 per the audit-v3.4 rubric.

    ``{d10_precomputed_block}`` carries harness-computed D10 the auditor must
    not exceed.

    ``{generation_metrics_block}`` carries precomputed cost/tokens for section H.
    """
    prompt = template.replace("{project_dir}", str(project_dir.resolve()))
    prompt = prompt.replace("{model_slug}", model_slug)
    if output_path is not None:
        prompt = prompt.replace("{output_path}", str(output_path.resolve()))
    if static_analysis_path is not None:
        prompt = prompt.replace(
            "{static_analysis_path}", str(static_analysis_path.resolve())
        )
    if d10_precomputed_block is not None:
        prompt = prompt.replace("{d10_precomputed_block}", d10_precomputed_block)
    else:
        prompt = prompt.replace(
            "{d10_precomputed_block}",
            "n/a — probe skipped; award D10 5/10 unverified.",
        )
    if benchmark_result_path is not None:
        prompt = prompt.replace(
            "{benchmark_result_path}", str(benchmark_result_path.resolve())
        )
    else:
        prompt = prompt.replace("{benchmark_result_path}", "n/a")
    if generation_metrics_path is not None:
        prompt = prompt.replace(
            "{generation_metrics_path}", str(generation_metrics_path.resolve())
        )
    else:
        prompt = prompt.replace("{generation_metrics_path}", "n/a")
    if generation_metrics_block is not None:
        prompt = prompt.replace("{generation_metrics_block}", generation_metrics_block)
    else:
        prompt = prompt.replace("{generation_metrics_block}", "n/a")
    if pricing_doc_path is not None:
        prompt = prompt.replace("{pricing_doc_path}", str(pricing_doc_path.resolve()))
    else:
        prompt = prompt.replace("{pricing_doc_path}", str(pricing_path().resolve()))
    return prompt


def _extract_final_report(stream_path: Path, report_path: Path) -> None:
    """Best-effort: extract assistant text from NDJSON as report.

    Supports Claude Code ``type == "assistant"`` events and Codex
    ``type == "item.completed"`` with ``item.type == "agent_message"``.
    """
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
                elif event.get("type") == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        text = item.get("text", "")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text)
        if chunks:
            report_path.write_text("\n\n".join(chunks))
    except OSError:
        pass


_AUDIT_PATH_FIELDS = (
    "benchmark_config",
    "benchmark_results_dir",
    "models_config",
    "prompt",
    "results_dir",
)


def normalize_audit_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve relative CLI filesystem paths against the harness checkout."""
    return normalize_path_fields(args, REPO_ROOT, _AUDIT_PATH_FIELDS)


def _maybe_run_quality_probe(
    *,
    project_dir: Path,
    out_path: Path,
    skip: bool,
    force: bool,
    job_slug: str,
) -> None:
    """Run the static-analysis probe; failures land in the JSON, never raise.

    Cached: if ``out_path`` already exists and ``force`` is False, reuse it.
    ``skip=True`` short-circuits — the audit prompt will see a missing file
    and grade D10 as unverified (5/10 default).
    """
    if skip:
        print_line(f"[{job_slug}] quality probe skipped (--skip-quality-probe)")
        return
    if out_path.exists() and not force:
        print_line(f"[{job_slug}] quality probe cached -> {out_path}")
        return
    try:
        payload = run_quality_probe(project_dir, out_path, repo_root=REPO_ROOT)
    except Exception as exc:  # noqa: BLE001 — never abort audit on probe issues
        print_line(f"[{job_slug}] quality probe crashed: {exc!r}")
        return
    status = payload.get("status", "unknown")
    print_line(f"[{job_slug}] quality probe status={status} -> {out_path}")


def _maybe_write_generation_metrics(
    *,
    target: dict,
    audit_results_dir: Path,
    auditor_slug: str,
    target_slug: str,
    force: bool,
    job_slug: str,
) -> dict:
    """Compute and write generation-metrics.json from the benchmark result."""
    metrics_path = audit_generation_metrics_json(
        audit_results_dir, auditor_slug, target_slug
    )
    if metrics_path.exists() and not force:
        print_line(f"[{job_slug}] generation metrics cached -> {metrics_path}")
        return load_json(metrics_path)

    benchmark_result_path = target["project_dir"].parent / "result.json"
    metrics = build_generation_metrics(
        target_slug=target_slug,
        model_slug=target.get("model_slug", target_slug),
        harness=target.get("harness", "unknown"),
        benchmark_result_path=benchmark_result_path,
        provider=target.get("provider"),
    )
    save_json(metrics_path, metrics)
    print_line(
        f"[{job_slug}] generation metrics status={metrics.get('status')} "
        f"cost={metrics.get('estimated_cost_usd')} -> {metrics_path}"
    )
    return metrics


def _print_calibration_warnings(auditor_dir: Path) -> None:
    """Warn when parsed cohort scores suggest rubric saturation."""
    reports = [
        load_rubric_result(p)
        for p in sorted(auditor_dir.glob("*/report.md"))
        if p.is_file()
    ]
    totals = [r.total for r in reports if r.total is not None]
    if not totals:
        return
    totals.sort()
    median = totals[len(totals) // 2]
    if median > 85:
        print_line(
            f"WARN calibration: median total={median} > 85 for {auditor_dir.name} "
            "(rubric may be too lenient — see meta-analysis Check 1)"
        )
    d2_scores = [r.dim_score(2) for r in reports if r.dim_score(2) is not None]
    if d2_scores:
        d2_full = sum(1 for s in d2_scores if s >= 20)
        if d2_full / len(d2_scores) >= 0.8:
            print_line(
                f"WARN calibration: D2 saturated ({d2_full}/{len(d2_scores)} at 20/20) "
                f"for {auditor_dir.name}"
            )


def main() -> int:
    args = normalize_audit_paths(parse_args())
    audit_config_path = Path(args.models_config)
    benchmark_config_path = Path(args.benchmark_config)
    prompt_template_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    benchmark_results_dir = Path(args.benchmark_results_dir)

    audit_config = load_json(audit_config_path)
    audit_config = resolve_audit_harness_config(
        audit_config, audit_config_path, args.harness
    )
    benchmark_config = load_json(benchmark_config_path)
    prompt_template = prompt_template_path.read_text()

    wanted_model = args.model
    wanted_targets = set(args.target) if args.target else None

    if args.report_only and wanted_model is None:
        results_dir.mkdir(parents=True, exist_ok=True)
        rollup_dirs = discover_auditor_subdirs(results_dir)
        if not rollup_dirs:
            print(
                f"No auditor trees with reports under {results_dir}.",
                file=sys.stderr,
            )
            return 1
        for auditor_dir in rollup_dirs:
            comparison_path = _write_auditor_comparison(auditor_dir)
            print_line(
                f"Comparison table + statistical summary written: {comparison_path}"
            )
        print_line(
            "Next: run scripts/run_meta_analysis.py to dispatch the cross-auditor "
            "AI meta-analysis."
        )
        return 0

    auditors, targets = resolve_auditors_and_targets(
        wanted_model,
        wanted_targets,
        audit_config,
        benchmark_config,
        benchmark_results_dir,
        args.harness,
    )

    if not auditors:
        print("No auditors selected.", file=sys.stderr)
        return 1
    if not targets and not args.report_only:
        print("No targets selected.", file=sys.stderr)
        return 1

    if not args.report_only:
        ok, err = _verify_auditor_binaries(auditors)
        if not ok:
            print(err, file=sys.stderr)
            return 1

    config_targets_by_slug = {
        v["slug"]: v for v in _target_metadata_rows(benchmark_config)
    }
    all_benchmark_targets = discover_project_dirs(
        benchmark_results_dir, config_targets_by_slug
    )
    if wanted_targets is None:
        targets = all_benchmark_targets

    jobs: list[tuple[dict, dict]] = [
        (auditor, target) for auditor in auditors for target in targets
    ]
    jobs_count = args.jobs if args.jobs > 0 else len(jobs)
    jobs_count = max(1, min(jobs_count, len(jobs))) if jobs else 1

    print_line(
        f"Audit benchmark: {len(auditors)} auditors × {len(targets)} targets = "
        f"{len(jobs)} runs, jobs={jobs_count}"
    )
    print_line(
        f"Benchmark results: {len(all_benchmark_targets)} project(s) under "
        f"{benchmark_results_dir}"
    )
    enforce_coverage = not args.no_enforce_coverage

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

            result_dir = audit_target_dir(results_dir, auditor_slug, target_slug)
            result_dir.mkdir(parents=True, exist_ok=True)

            report_path = audit_report_md(results_dir, auditor_slug, target_slug)
            audit_result_path = audit_result_json(
                results_dir, auditor_slug, target_slug
            )
            dispatch_force = audit_dispatch_needed(
                report_path=report_path,
                audit_result_path=audit_result_path,
                force=args.force,
            )
            if not dispatch_force:
                print_line(f"[{job_slug}] complete report cached; skipping dispatch")
                return job_slug, "cached", None

            project_dir = target["project_dir"]
            model_slug_for_prompt = target.get("model_slug", target_slug)
            static_analysis_path = audit_static_analysis_json(
                results_dir, auditor_slug, target_slug
            )
            _maybe_run_quality_probe(
                project_dir=project_dir,
                out_path=static_analysis_path,
                skip=args.skip_quality_probe,
                force=args.force,
                job_slug=job_slug,
            )

            static_payload = (
                None
                if args.skip_quality_probe
                else load_static_analysis(static_analysis_path)
            )
            d10_result = compute_d10_from_probe(static_payload, project_dir=project_dir)
            d10_block = format_d10_precomputed_block(d10_result)

            gen_metrics = _maybe_write_generation_metrics(
                target=target,
                audit_results_dir=results_dir,
                auditor_slug=auditor_slug,
                target_slug=target_slug,
                force=args.force,
                job_slug=job_slug,
            )
            benchmark_result_path = project_dir.parent / "result.json"
            generation_metrics_path = audit_generation_metrics_json(
                results_dir, auditor_slug, target_slug
            )

            audit_prompt = build_audit_prompt(
                prompt_template,
                project_dir,
                model_slug_for_prompt,
                output_path=audit_report_md(results_dir, auditor_slug, target_slug),
                static_analysis_path=static_analysis_path,
                benchmark_result_path=benchmark_result_path,
                generation_metrics_path=generation_metrics_path,
                generation_metrics_block=format_generation_metrics_block(gen_metrics),
                pricing_doc_path=pricing_path(),
                d10_precomputed_block=d10_block,
            )

            (result_dir / "prompt.txt").write_text(audit_prompt)

            try:
                runner_type = auditor.get("runner_type", "claude")
                # "ollama" is a legacy alias routed through the codex harness.
                harness_name = (
                    "codex" if runner_type in _CODEX_RUNNER_TYPES else runner_type
                )
                harness = get_harness(harness_name)
                run_kwargs: dict[str, Any] = dict(
                    variant=auditor,
                    prompt=audit_prompt,
                    results_dir=results_dir / auditor_slug,
                    timeout_seconds=timeout_seconds,
                    no_progress_timeout_seconds=no_progress_timeout_seconds,
                    force=True,
                    harness=runner_type,  # preserve original (incl. "ollama") for callee
                    explicit_result_dir=result_dir,
                )
                if harness.name not in _CODEX_RUNNER_TYPES:
                    run_kwargs["runner_command_prefix"] = runner_command_prefix
                if harness.accepts_isolate_home:
                    run_kwargs["isolate_home"] = isolate_home
                run_result = harness.run_variant(**run_kwargs)

                if run_result.get("status") == USAGE_LIMIT_REACHED:
                    return job_slug, USAGE_LIMIT_REACHED, None

                # The LLM should have written report.md via the Write tool. If
                # not, fall back to extracting the last assistant text from
                # stream.ndjson so the comparison table still has something.
                if not report_path.exists():
                    stream_path = audit_stream_ndjson(
                        results_dir, auditor_slug, target_slug
                    )
                    if stream_path.exists():
                        _extract_final_report(stream_path, report_path)

                if report_path.exists():
                    issues = validate_section_h_cost(
                        report_path.read_text(encoding="utf-8"),
                        gen_metrics,
                    )
                    for issue in issues:
                        print_line(f"[{job_slug}] WARN section H: {issue}")

                    reconciliation_path = result_dir / "d10-reconciliation.json"
                    recon = reconcile_report_d10(
                        report_path,
                        d10_result,
                        reconciliation_path=reconciliation_path,
                    )
                    if recon.get("patched"):
                        print_line(
                            f"[{job_slug}] D10 reconciled: auditor={recon.get('auditor_d10')} "
                            f"-> harness={recon.get('computed_d10')} "
                            f"(delta={recon.get('delta')})"
                        )
                    elif recon.get("action") == "match":
                        print_line(
                            f"[{job_slug}] D10 match harness={recon.get('computed_d10')}"
                        )

                return job_slug, "ok", None
            except Exception:
                return job_slug, "error", traceback.format_exc()

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

    if enforce_coverage and not args.report_only:
        gaps = find_audit_coverage_gaps(
            benchmark_results_dir=benchmark_results_dir,
            audit_results_dir=results_dir,
            auditor_slugs=[a["slug"] for a in auditors],
            required_targets=all_benchmark_targets,
        )
        if gaps:
            print(format_coverage_gaps(gaps), file=sys.stderr)
            return 1

    # Per-auditor comparison + regex rollup (including --report-only). Only
    # auditor trees that contain at least one report.md are touched.
    results_dir.mkdir(parents=True, exist_ok=True)
    rollup_dirs = _auditor_dirs_for_comparison_rollup(
        results_dir,
        auditors,
        report_only=args.report_only,
        wanted_model=wanted_model,
    )
    if not rollup_dirs:
        print(
            "No audit reports found to roll up. Run audits first or pass "
            "--model to select an auditor tree.",
            file=sys.stderr,
        )
        return 1
    for auditor_dir in rollup_dirs:
        comparison_path = _write_auditor_comparison(auditor_dir)
        print_line(f"Comparison table + statistical summary written: {comparison_path}")
        _print_calibration_warnings(auditor_dir)

    print_line(
        "Next: run scripts/run_meta_analysis.py to dispatch the cross-auditor "
        "AI meta-analysis."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
