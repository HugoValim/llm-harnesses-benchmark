"""Grep-based D9 production-hardening preflight for generated benchmark projects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

D9_SUBCHECK_KEYS = (
    "healthcheck",
    "logging",
    "restart",
    "non_root_user",
    "sigterm_shutdown",
)

_DOCKERFILE_NAMES = ("Dockerfile", "dockerfile")
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _find_project_file(project_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    return None


def _settings_files(project_dir: Path) -> list[Path]:
    root_settings = project_dir / "settings.py"
    found = [root_settings] if root_settings.is_file() else []
    found.extend(sorted(project_dir.glob("**/settings.py")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _consumer_files(project_dir: Path) -> list[Path]:
    return sorted(project_dir.glob("**/consumers.py"))


def _check_healthcheck(project_dir: Path) -> tuple[bool, str | None]:
    dockerfile = _find_project_file(project_dir, _DOCKERFILE_NAMES)
    compose = _find_project_file(project_dir, _COMPOSE_NAMES)
    evidence: list[str] = []
    if dockerfile and re.search(r"\bHEALTHCHECK\b", _read_text(dockerfile), re.I):
        evidence.append(str(dockerfile.relative_to(project_dir)))
    if compose and re.search(r"^\s*healthcheck\s*:", _read_text(compose), re.I | re.M):
        evidence.append(str(compose.relative_to(project_dir)))
    if evidence:
        return True, ", ".join(evidence)
    return False, None


def _check_logging(project_dir: Path) -> tuple[bool, str | None]:
    for settings_path in _settings_files(project_dir):
        if re.search(r"^\s*LOGGING\s*=", _read_text(settings_path), re.M):
            return True, str(settings_path.relative_to(project_dir))
    return False, None


def _check_restart(project_dir: Path) -> tuple[bool, str | None]:
    compose = _find_project_file(project_dir, _COMPOSE_NAMES)
    if compose and re.search(r"^\s*restart\s*:", _read_text(compose), re.I | re.M):
        return True, str(compose.relative_to(project_dir))
    return False, None


def _check_non_root_user(project_dir: Path) -> tuple[bool, str | None]:
    dockerfile = _find_project_file(project_dir, _DOCKERFILE_NAMES)
    if not dockerfile:
        return False, None
    for line in _read_text(dockerfile).splitlines():
        match = re.match(r"^\s*USER\s+(\S+)", line, re.I)
        if match and match.group(1).lower() not in {"root", "0"}:
            return True, f"{dockerfile.relative_to(project_dir)}:{line}"
    return False, None


def _check_sigterm_shutdown(project_dir: Path) -> tuple[bool, str | None]:
    for consumer_path in _consumer_files(project_dir):
        text = _read_text(consumer_path)
        if "CancelledError" not in text:
            continue
        if ".astream" in text or "astream(" in text:
            return True, str(consumer_path.relative_to(project_dir))
    return False, None


def scan_d9_preflight(project_dir: Path) -> dict[str, Any]:
    """Return pass/fail map for D9 sub-checks under ``project_dir``."""
    project_dir = project_dir.resolve()
    checks: dict[str, dict[str, object]] = {}
    scanners = {
        "healthcheck": _check_healthcheck,
        "logging": _check_logging,
        "restart": _check_restart,
        "non_root_user": _check_non_root_user,
        "sigterm_shutdown": _check_sigterm_shutdown,
    }
    passed = 0
    for key, scanner in scanners.items():
        ok, evidence = scanner(project_dir)
        if ok:
            passed += 1
        checks[key] = {"pass": ok, "evidence": evidence}
    return {
        "prompt_version": "benchmark-v3.5",
        "project_dir": str(project_dir),
        "checks": checks,
        "passed_count": passed,
        "total_count": len(D9_SUBCHECK_KEYS),
    }


def write_d9_preflight(result_dir: Path, project_dir: Path) -> Path | None:
    """Write ``d9-preflight.json`` beside ``result.json``; return path or None."""
    if not project_dir.is_dir():
        return None
    payload = scan_d9_preflight(project_dir)
    out_path = result_dir.resolve() / "d9-preflight.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def load_d9_preflight(path: Path) -> dict[str, Any] | None:
    """Load a preflight JSON file; return None if missing or invalid."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def infer_benchmark_projects_root(source_dirs: list[Path] | None) -> Path | None:
    """Locate ``results/<run_id>/projects`` from audit input directory layout."""
    if not source_dirs:
        return None
    for source in source_dirs:
        for parent in source.resolve().parents:
            projects = parent / "projects"
            if projects.is_dir():
                return projects
    return None


def _d9_subcheck_label(key: str) -> str:
    labels = {
        "healthcheck": "D9.1 healthcheck",
        "logging": "D9.2 logging",
        "restart": "D9.3 restart",
        "non_root_user": "D9.4 non-root USER",
        "sigterm_shutdown": "D9.5 SIGTERM shutdown",
    }
    return labels.get(key, key)


def build_d9_subcheck_cohort_section(
    *,
    benchmark_projects_root: Path | None = None,
    source_dirs: list[Path] | None = None,
) -> str:
    """Cohort pass rates for D9 sub-checks from ``d9-preflight.json`` or live scan."""
    projects_root = benchmark_projects_root
    if projects_root is None:
        projects_root = infer_benchmark_projects_root(source_dirs)
    if projects_root is None or not projects_root.is_dir():
        return ""

    rows: list[tuple[str, dict[str, bool]]] = []
    for target_dir in sorted(projects_root.iterdir()):
        if not target_dir.is_dir():
            continue
        preflight_path = target_dir / "d9-preflight.json"
        payload = load_d9_preflight(preflight_path)
        if payload is None:
            project_dir = target_dir / "project"
            if not project_dir.is_dir():
                continue
            payload = scan_d9_preflight(project_dir)
        checks = payload.get("checks")
        if not isinstance(checks, dict):
            continue
        passed: dict[str, bool] = {}
        for key in D9_SUBCHECK_KEYS:
            entry = checks.get(key)
            passed[key] = bool(
                isinstance(entry, dict) and entry.get("pass") is True
            )
        rows.append((target_dir.name, passed))

    if not rows:
        return ""

    lines = [
        "## D9 sub-check cohort (preflight)",
        "",
        "Pass rate per D9 sub-check across benchmark project dirs "
        f"under `{projects_root}`. Harness preflight only — not audit scores.",
        "",
        "| Sub-check | Pass | Total | Rate |",
        "|---|---:|---:|---:|",
    ]
    total = len(rows)
    for key in D9_SUBCHECK_KEYS:
        pass_count = sum(1 for _, row_passed in rows if row_passed.get(key))
        rate = (100.0 * pass_count / total) if total else 0.0
        lines.append(
            f"| {_d9_subcheck_label(key)} | {pass_count} | {total} | {rate:.1f}% |"
        )
    lines.append("")
    lines.append(
        f"Targets with 0/5 passes: "
        f"{sum(1 for _, p in rows if not any(p.values()))}; "
        f"5/5 passes: {sum(1 for _, p in rows if all(p.values()))}."
    )
    return "\n".join(lines) + "\n"
