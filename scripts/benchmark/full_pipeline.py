"""Full benchmark pipeline: build matrix, audit, and meta-analysis orchestration."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark.audit_meta import audit_model_harness
from benchmark.config import resolve_build_harness_config
from benchmark.timeouts import meta_timeout_cli_flags, timeout_cli_flags
from benchmark.util import load_json, print_line

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

OLLAMA_BUILD_HARNESSES: tuple[str, ...] = ("opencode", "codex", "claude")
BASELINE_STEPS: tuple[tuple[str, str, str], ...] = (
    ("claude", "claude_opus_4_7", "docs/report.claude-opus.md"),
    ("codex", "codex_gpt_5_5", "docs/report.codex.md"),
)

HARNESS_REPORT_PATHS: dict[str, str] = {
    "opencode": "docs/report.opencode.md",
    "codex": "docs/report.codex.md",
    "claude": "docs/report.claude-code.md",
}

STALE_AUDIT_PROMPT_MARKER = "Prompt-Version: audit-v3.0"


@dataclass(frozen=True)
class BuildStep:
    """One Phase 1 ``run_benchmark.py`` invocation."""

    harness: str
    model_slug: str
    report_path: str

    def key(self) -> tuple[str, str]:
        return (self.harness, self.model_slug)


def ollama_cloud_slugs(registry_models: Sequence[dict]) -> list[str]:
    return [
        str(m["slug"])
        for m in registry_models
        if m.get("provider") == "ollama_cloud" and m.get("slug")
    ]


def slug_in_harness(
    models_config_path: Path, harness: str, slug: str
) -> bool:
    """True when ``slug`` resolves for ``harness`` in the shared registry."""
    config = load_json(models_config_path)
    resolved = resolve_build_harness_config(config, models_config_path, harness)
    return any(m.get("slug") == slug for m in resolved.get("models", []))


def build_matrix(models_config_path: Path) -> list[BuildStep]:
    """Ollama Cloud on opencode/codex/claude plus subscription baselines."""
    registry = load_json(models_config_path).get("models", [])
    if not isinstance(registry, list):
        raise ValueError(f"{models_config_path} must contain a models array")

    steps: list[BuildStep] = []
    seen: set[tuple[str, str]] = set()

    for harness in OLLAMA_BUILD_HARNESSES:
        report = HARNESS_REPORT_PATHS[harness]
        for slug in ollama_cloud_slugs(registry):
            if not slug_in_harness(models_config_path, harness, slug):
                continue
            key = (harness, slug)
            if key in seen:
                continue
            seen.add(key)
            steps.append(BuildStep(harness, slug, report))

    for harness, slug, report in BASELINE_STEPS:
        if not slug_in_harness(models_config_path, harness, slug):
            raise ValueError(
                f"baseline {slug!r} is not configured for harness {harness!r} "
                f"in {models_config_path}"
            )
        key = (harness, slug)
        if key not in seen:
            seen.add(key)
            steps.append(BuildStep(harness, slug, report))

    return steps


def reject_forwarded_model_flag(extra_args: Sequence[str]) -> None:
    if "--model" in extra_args:
        raise SystemExit(
            "ERROR: Do not pass --model on the command line; "
            "the build matrix is defined in benchmark.full_pipeline.build_matrix()."
        )


def run_build_step(
    step: BuildStep,
    *,
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    dry_run: bool,
) -> None:
    print_line(f"==> Phase 1 build: harness={step.harness} model={step.model_slug}")
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "run_benchmark.py"),
        "--harness",
        step.harness,
        "--model",
        step.model_slug,
        "--models-config",
        str(models_config),
        "--results-dir",
        str(results_dir),
        "--report",
        step.report_path,
        *timeout_cli_flags(),
        *extra_args,
    ]
    if dry_run:
        print_line(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def phase_build(
    models_config: Path,
    results_dir: Path,
    extra_args: Sequence[str],
    *,
    dry_run: bool = False,
) -> list[BuildStep]:
    steps = build_matrix(models_config)
    print_line(f"==> Phase 1 — build matrix ({len(steps)} steps)")
    for step in steps:
        run_build_step(
            step,
            models_config=models_config,
            results_dir=results_dir,
            extra_args=extra_args,
            dry_run=dry_run,
        )
    return steps


def resolve_meta_config(
    harnesses_config: Path,
    models_config: Path,
    auditor_slug: str,
    meta_auditor_slug: str | None,
    meta_harness: str | None,
    meta_input_dir: str | None,
) -> tuple[str, str, str]:
    """Return (meta_auditor_slug, meta_harness, meta_input_dir)."""
    meta_slug = meta_auditor_slug or auditor_slug
    meta_input = meta_input_dir or auditor_slug
    harnesses = load_json(harnesses_config)
    registry = load_json(models_config)
    expected = audit_model_harness(harnesses, meta_slug, models_config=registry)

    resolved_harness = meta_harness or expected
    if resolved_harness != expected:
        raise SystemExit(
            f"ERROR: META_ANALYSIS_HARNESS={resolved_harness} but model {meta_slug} "
            f"defaults to harness={expected} in {harnesses_config}"
        )
    if resolved_harness not in ("claude", "codex"):
        raise SystemExit(
            f"ERROR: META_ANALYSIS_HARNESS must be claude or codex "
            f"(got {resolved_harness})"
        )

    print_line(f"Phase 2 auditor: {auditor_slug}")
    print_line(
        f"Phase 3 meta: slug={meta_slug} harness={resolved_harness} "
        f"input={meta_input}"
    )
    return meta_slug, resolved_harness, meta_input


def assert_no_stale_audit_reports(audit_reports_dir: Path, auditor_slug: str) -> None:
    auditor_dir = audit_reports_dir / auditor_slug
    if not auditor_dir.is_dir():
        return

    stale = [
        path
        for path in auditor_dir.glob("*/report.md")
        if STALE_AUDIT_PROMPT_MARKER in path.read_text(encoding="utf-8", errors="replace")
    ]
    if not stale:
        return

    lines = "\n".join(str(p) for p in stale)
    raise SystemExit(
        f"ERROR: stale audit-v3.0 reports under {auditor_dir}:\n{lines}\n\n"
        "The meta-analysis meta-v3.1 excludes audit-v3.0 reports. Remove them "
        "and re-run."
    )


def phase_audit(
    models_config: Path,
    results_dir: Path,
    audit_reports_dir: Path,
    auditor_slug: str,
    *,
    dry_run: bool = False,
) -> None:
    print_line("==> Phase 2 — audit (Role 1)")
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "run_audit.py"),
        "--models-config",
        str(models_config),
        "--harness",
        "claude",
        "--benchmark-results-dir",
        str(results_dir),
        "--results-dir",
        str(audit_reports_dir),
        "--model",
        auditor_slug,
        "--target",
        "all",
        "-j",
        "3",
        *timeout_cli_flags(),
    ]
    if dry_run:
        print_line(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def phase_meta_analysis(
    models_config: Path,
    audit_reports_dir: Path,
    meta_slug: str,
    meta_harness: str,
    meta_input_dir: str,
    *,
    dry_run: bool = False,
) -> None:
    print_line("==> Phase 3 — meta-analysis (Role 2)")
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "run_meta_analysis.py"),
        *meta_timeout_cli_flags(),
        "--models-config",
        str(models_config),
        "--results-dir",
        str(audit_reports_dir),
        "--harness",
        meta_harness,
        "--model",
        meta_slug,
        "--meta-input-dir",
        meta_input_dir,
        "--force",
    ]
    if dry_run:
        print_line(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)
