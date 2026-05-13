#!/usr/bin/env python3
"""Role 1: per-project AI audit dispatch.

Reads benchmark outputs under ``results/<harness>-<slug>/project`` and
dispatches an LLM auditor (Claude Code variant) against each, using the
rubric template at ``prompts/audit_prompt_template.txt``. Audit outputs land
in ``audit-reports/<auditor_slug>/<target_slug>/`` (one ``report.md`` per
(auditor, target) pair).

After dispatch, rebuilds ``audit-reports/comparison.md`` from every
``report.md`` on disk via :func:`benchmark.audit_report.build_comparison_table`
and :func:`build_statistical_summary`.

This script is the per-project leg of the audit pipeline. The cross-auditor
meta-analysis is its own entry point: ``scripts/run_meta_analysis.py``.

Auth:
  - Anthropic auditors use Claude subscription auth (``claude login``).
  - Non-Anthropic auditors are routed via ``ollama launch claude --model <tag>``
    using the variant's ``command_prefix`` field in audit_models.json.
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

from benchmark.audit_report import (  # noqa: E402
    build_comparison_table,
    build_statistical_summary,
)
from benchmark.claude_code_runner import run_variant  # noqa: E402
from benchmark.runner import run_codex_variant  # noqa: E402
from benchmark.util import load_json, print_line  # noqa: E402


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
AUDIT_CONFIG_PATH = REPO_ROOT / "config" / "audit_models.json"
BENCHMARK_CONFIG_PATH = REPO_ROOT / "config" / "claude_code_models.json"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "prompts" / "audit_prompt_template.txt"
DEFAULT_RESULTS_DIR = REPO_ROOT / "audit-reports"
DEFAULT_BENCHMARK_RESULTS_DIR = REPO_ROOT / "results"


# Harness prefixes recognised when stripping ``results/<harness>-<slug>/`` →
# ``<slug>``. Anything that doesn't match one of these is treated as a legacy
# ``results/<slug>/project`` layout and the dirname itself becomes the slug.
HARNESS_PREFIXES: tuple[str, ...] = ("claude", "codex", "ollama", "opencode")


def discover_project_dirs(
    benchmark_results_dir: Path,
    config_targets_by_slug: dict[str, dict] | None = None,
) -> list[dict]:
    """Scan ``benchmark_results_dir`` for every ``<name>/project`` subdir.

    Returns one target dict per discovered project, sorted by dir name:

    - ``slug``: the directory name (e.g. ``claude-kimi_k2_6_ollama_cloud``).
      Used as the audit output dir name; unique by construction.
    - ``model_slug``: the slug with the harness prefix stripped, or the dir
      name itself when no harness prefix is recognised.
    - ``harness``: ``"claude" | "codex" | "ollama" | "opencode" | "unknown"``.
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
        harness = "unknown"
        model_slug = name
        for prefix in HARNESS_PREFIXES:
            if name.startswith(f"{prefix}-"):
                harness = prefix
                model_slug = name[len(prefix) + 1 :]
                break
        target: dict = {
            "slug": name,
            "model_slug": model_slug,
            "harness": harness,
            "project_dir": project_dir,
        }
        extra = config_targets_by_slug.get(model_slug)
        if extra:
            for k in ("label", "main_model", "selection_reason"):
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
        "--audit-config",
        default=str(AUDIT_CONFIG_PATH),
        help="Path to audit_models.json (auditor registry).",
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
            "Select target(s) by full dirname (e.g. claude-kimi_k2_6_ollama_cloud) "
            "or by bare model slug (matches every harness that has that slug). "
            "Repeatable. Use 'all' to select every discovered project. "
            "Default: every discovered project."
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
        help="Rebuild comparison.md from existing reports without running audits.",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Number of concurrent audits (default: 1 = sequential). Use 0 for one worker per job.",
    )
    return parser.parse_args()


def resolve_auditors_and_targets(
    wanted_auditors: set[str] | None,
    wanted_targets: set[str] | None,
    audit_config: dict,
    benchmark_config: dict,
    benchmark_results_dir: Path,
) -> tuple[list[dict], list[dict]]:
    """Resolve auditor and target lists from CLI flags.

    Auditors come from ``audit_config``. Targets are discovered on disk via
    :func:`discover_project_dirs` and optionally enriched with metadata from
    ``benchmark_config`` when a model_slug matches.

    Default (both wanted sets are None): all non-skipped auditors × every
    discovered project.
    """
    all_auditors = [
        v for v in audit_config.get("variants", []) if not v.get("skip_by_default")
    ]
    audit_slugs = {v["slug"] for v in all_auditors}

    config_targets_by_slug = {
        v["slug"]: v for v in benchmark_config.get("variants", [])
    }
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

    if wanted_auditors is not None or wanted_targets is not None:
        auditors = [v for v in all_auditors if v["slug"] in (wanted_auditors or set())]
        targets = _filter_discovered(discovered, wanted_targets or set())

        missing_auditors = (wanted_auditors or set()) - audit_slugs - {"all"}
        missing_targets = (wanted_targets or set()) - known_target_keys - {"all"}
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
            _emit_unknown_targets(missing_targets)
            sys.exit(1)
        if wanted_auditors is None:
            auditors = all_auditors
        if wanted_targets is None:
            targets = discovered
        return auditors, targets

    return all_auditors, discovered


def build_audit_prompt(
    template: str,
    project_dir: Path,
    model_slug: str,
    output_path: Path | None = None,
) -> str:
    """Interpolate placeholders into the audit prompt template."""
    prompt = template.replace("{project_dir}", str(project_dir.resolve()))
    prompt = prompt.replace("{model_slug}", model_slug)
    if output_path is not None:
        prompt = prompt.replace("{output_path}", str(output_path.resolve()))
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


def main() -> int:
    args = parse_args()
    audit_config_path = Path(args.audit_config)
    benchmark_config_path = Path(args.benchmark_config)
    prompt_template_path = Path(args.prompt)
    results_dir = Path(args.results_dir)
    benchmark_results_dir = Path(args.benchmark_results_dir)

    audit_config = load_json(audit_config_path)
    benchmark_config = load_json(benchmark_config_path)
    prompt_template = prompt_template_path.read_text()

    wanted_auditors = set(args.auditor) if args.auditor else None
    wanted_targets = set(args.target) if args.target else None
    auditors, targets = resolve_auditors_and_targets(
        wanted_auditors,
        wanted_targets,
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

    if not args.report_only:
        ok, err = _verify_auditor_binaries(auditors)
        if not ok:
            print(err, file=sys.stderr)
            return 1

    jobs: list[tuple[dict, dict]] = []
    for auditor in auditors:
        for target in targets:
            jobs.append((auditor, target))

    jobs_count = args.jobs if args.jobs > 0 else len(jobs)
    jobs_count = max(1, min(jobs_count, len(jobs))) if jobs else 1

    print_line(
        f"Audit benchmark: {len(auditors)} auditors × {len(targets)} targets = "
        f"{len(jobs)} runs, jobs={jobs_count}"
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

            result_dir = results_dir / auditor_slug / target_slug
            result_dir.mkdir(parents=True, exist_ok=True)

            project_dir = target["project_dir"]
            model_slug_for_prompt = target.get("model_slug", target_slug)
            audit_prompt = build_audit_prompt(
                prompt_template,
                project_dir,
                model_slug_for_prompt,
                output_path=result_dir / "report.md",
            )

            (result_dir / "prompt.txt").write_text(audit_prompt)

            try:
                runner_type = auditor.get("runner_type", "claude")
                if runner_type in _CODEX_RUNNER_TYPES:
                    run_codex_variant(
                        variant=auditor,
                        prompt=audit_prompt,
                        results_dir=results_dir / auditor_slug,
                        timeout_seconds=timeout_seconds,
                        no_progress_timeout_seconds=no_progress_timeout_seconds,
                        force=args.force,
                        harness=runner_type,
                        explicit_result_dir=result_dir,
                    )
                else:
                    run_variant(
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
                # The LLM should have written report.md via the Write tool. If
                # not, fall back to extracting the last assistant text from
                # stream.ndjson so the comparison table still has something.
                report_path = result_dir / "report.md"
                if not report_path.exists():
                    stream_path = result_dir / "stream.ndjson"
                    if stream_path.exists():
                        _extract_final_report(stream_path, report_path)

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

    # Cross-auditor comparison + regex rollup are written every run (including
    # --report-only). They are NOT inputs to the AI meta-analyst; they exist
    # for at-a-glance browsing and post-hoc calibration.
    results_dir.mkdir(parents=True, exist_ok=True)
    comparison_md = build_comparison_table(results_dir)
    statistical_md = build_statistical_summary(results_dir)
    comparison_path = results_dir / "comparison.md"
    comparison_path.write_text(comparison_md.rstrip() + "\n\n" + statistical_md)
    print_line(f"Comparison table + statistical summary written: {comparison_path}")

    print_line(
        "Next: run scripts/run_meta_analysis.py to dispatch the cross-auditor "
        "AI meta-analysis."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
