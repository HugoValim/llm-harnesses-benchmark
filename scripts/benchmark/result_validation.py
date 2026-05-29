"""Validate benchmark ``results/<harness>-<slug>/`` runs and support clean retries."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.config import summarize_project
from benchmark.result_layout import split_target_slug, target_dir
from benchmark.util import USAGE_LIMIT_REACHED, load_json, migrate_to_v2


def rederive_status(row: dict[str, Any], project_summary: dict[str, Any]) -> str:
    """Recompute run status from ``result.json`` row and fresh project summary.

    Mirrors :func:`benchmark.runner.run_codex_phase` / ``run_opencode_phase`` so
    validation reflects updated scaffold detection without re-running agents.
    """
    if row.get("stalled") and row.get("stall_reason") == USAGE_LIMIT_REACHED:
        return USAGE_LIMIT_REACHED
    if row.get("timed_out"):
        return "timeout"
    if row.get("stalled"):
        return "failed"
    works = project_summary.get("works_as_intended") == "yes"
    terminal_stop = row.get("finish_reason") == "stop"
    if terminal_stop and works:
        return "completed"
    if terminal_stop:
        return "completed_with_errors"
    exit_code = row.get("exit_code")
    if exit_code == 0 and works:
        return "completed"
    if exit_code == 0:
        return "completed_with_errors"
    return "failed"

MAX_VALIDATION_RETRIES = 3


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    result_dir: Path
    slug: str
    harness: str | None
    issues: list[ValidationIssue] = field(default_factory=list)
    fresh_status: str | None = None
    fresh_project_summary: dict[str, Any] | None = None

    def summary(self) -> str:
        if self.ok:
            return "ok"
        return "; ".join(f"{i.code}: {i.message}" for i in self.issues)


def followup_expected(*, followup_prompt: str | None) -> bool:
    """True when the benchmark follow-up prompt is configured (phase 2 required)."""
    return bool(followup_prompt and followup_prompt.strip())


def wipe_result_dir(result_dir: Path, *, recreate: bool = True) -> None:
    """Remove a prior benchmark attempt so the next run starts from scratch.

    With ``recreate=True`` (default), leaves an empty result dir for harness
    runners. With ``recreate=False``, deletes the directory entirely.
    """
    resolved = result_dir.resolve()
    if resolved.exists():
        shutil.rmtree(resolved)
    if recreate:
        resolved.mkdir(parents=True, exist_ok=True)


def validation_retryable(payload: dict[str, Any] | None) -> bool:
    """False for quota / throttle failures where an immediate rerun will not help."""
    if not payload:
        return True
    if payload.get("status") == USAGE_LIMIT_REACHED:
        return False
    phases = payload.get("phases")
    if isinstance(phases, list):
        for phase in phases:
            if isinstance(phase, dict) and phase.get("status") == USAGE_LIMIT_REACHED:
                return False
    return True


def _load_result_row(result_dir: Path) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    result_path = result_dir / "result.json"
    if not result_path.exists():
        return None, [
            ValidationIssue("missing_result", f"no result.json under {result_dir}")
        ]
    try:
        row = migrate_to_v2(load_json(result_path))
    except (json.JSONDecodeError, OSError) as exc:
        return None, [
            ValidationIssue("invalid_result", f"cannot read result.json: {exc}")
        ]
    return row, []


def _validate_phase_row(
    phase: dict[str, Any],
    *,
    label: str,
    expect_works: bool,
    fresh_summary: dict[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    status = phase.get("status")
    if status != "completed":
        issues.append(
            ValidationIssue(
                f"{label}_status",
                f"expected status=completed, got {status!r}",
            )
        )
    exit_code = phase.get("exit_code")
    if exit_code not in (0, None):
        issues.append(
            ValidationIssue(
                f"{label}_exit_code",
                f"expected exit_code=0, got {exit_code!r}",
            )
        )
    if phase.get("timed_out"):
        issues.append(ValidationIssue(f"{label}_timed_out", "phase timed out"))
    if phase.get("stalled"):
        stall = phase.get("stall_reason") or "stalled"
        issues.append(ValidationIssue(f"{label}_stalled", str(stall)))

    if expect_works and "project_summary" in phase:
        works = (phase.get("project_summary") or {}).get("works_as_intended")
        if works != "yes":
            issues.append(
                ValidationIssue(
                    f"{label}_scaffold",
                    f"expected works_as_intended=yes, got {works!r}",
                )
            )
    elif expect_works and label.endswith("phase1"):
        works = fresh_summary.get("works_as_intended")
        if works != "yes":
            issues.append(
                ValidationIssue(
                    f"{label}_scaffold",
                    f"expected works_as_intended=yes, got {works!r}",
                )
            )
    return issues


def validate_benchmark_result(
    result_dir: Path,
    *,
    model: dict[str, Any] | None = None,
    followup_expected_flag: bool = False,
) -> ValidationResult:
    """Check whether a harness run produced an acceptable benchmark artifact.

    Recomputes ``project_summary`` from disk and re-derives status from the row.
    """
    result_dir = result_dir.resolve()
    harness, slug = split_target_slug(result_dir.name)
    row, load_issues = _load_result_row(result_dir)
    if row is None:
        return ValidationResult(
            ok=False,
            result_dir=result_dir,
            slug=slug,
            harness=harness,
            issues=load_issues,
        )

    model_row = model if model is not None else row.get("model")
    if not isinstance(model_row, dict):
        model_row = {}

    issues: list[ValidationIssue] = []
    if row.get("workspace_escape_detected"):
        paths = row.get("workspace_escape_paths") or []
        issues.append(
            ValidationIssue(
                "workspace_escape",
                f"files written outside project workspace: {paths}",
            )
        )

    if row.get("status") == USAGE_LIMIT_REACHED:
        issues.append(
            ValidationIssue("usage_limit", "provider usage limit reached")
        )

    project_dir = result_dir / "project"
    if not project_dir.is_dir():
        issues.append(
            ValidationIssue("missing_project", f"project dir missing: {project_dir}")
        )
        fresh_summary: dict[str, Any] = {
            "works_as_intended": "no",
            "works_note": "project directory missing",
        }
    else:
        fresh_summary = summarize_project(project_dir)

    fresh_status = rederive_status(row, fresh_summary)

    if fresh_status != "completed":
        issues.append(
            ValidationIssue(
                "status",
                f"expected status=completed, got {fresh_status!r} "
                f"({fresh_summary.get('works_note', '')})",
            )
        )
    if fresh_summary.get("works_as_intended") != "yes":
        issues.append(
            ValidationIssue(
                "scaffold",
                fresh_summary.get("works_note", "scaffold incomplete"),
            )
        )

    exit_code = row.get("exit_code")
    if exit_code not in (0, None):
        issues.append(
            ValidationIssue("exit_code", f"expected exit_code=0, got {exit_code!r}")
        )
    if row.get("timed_out"):
        issues.append(ValidationIssue("timed_out", "run timed out"))
    if row.get("stalled"):
        issues.append(
            ValidationIssue("stalled", str(row.get("stall_reason") or "stalled"))
        )

    phases = row.get("phases")
    if not isinstance(phases, list) or not phases:
        issues.append(ValidationIssue("missing_phases", "result has no phases[]"))
    else:
        phase1 = next(
            (p for p in phases if isinstance(p, dict) and p.get("phase") == "phase1"),
            phases[0] if isinstance(phases[0], dict) else None,
        )
        if isinstance(phase1, dict):
            issues.extend(
                _validate_phase_row(
                    phase1,
                    label="phase1",
                    expect_works=True,
                    fresh_summary=fresh_summary,
                )
            )
        if followup_expected_flag:
            phase2 = next(
                (
                    p
                    for p in phases
                    if isinstance(p, dict) and p.get("phase") == "phase2"
                ),
                None,
            )
            if phase2 is None:
                issues.append(
                    ValidationIssue(
                        "missing_phase2",
                        "follow-up phase expected but phases[] has no phase2",
                    )
                )
            else:
                issues.extend(
                    _validate_phase_row(
                        phase2,
                        label="phase2",
                        expect_works=True,
                        fresh_summary=fresh_summary,
                    )
                )

    return ValidationResult(
        ok=not issues,
        result_dir=result_dir,
        slug=slug,
        harness=harness,
        issues=issues,
        fresh_status=fresh_status,
        fresh_project_summary=fresh_summary,
    )


def result_dir_for(
    results_root: Path, harness: str, slug: str
) -> Path:
    return target_dir(results_root, harness, slug)
