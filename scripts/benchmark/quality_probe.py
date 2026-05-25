"""Audit-time static-analysis probe.

Runs a pinned, reproducible toolchain (``ruff`` / ``mypy`` / ``bandit`` /
``radon cc`` / ``radon mi``) against one generated project and writes a
compact JSON evidence file the LLM auditor can cite for the audit-v3.4
D10 (Code quality, tool-backed) dimension.

The probe venv lives at ``_quality_probe/venv/`` and is shared across all
audits so every target is graded with identical tool builds — the only
source of cross-target variance is the generated code itself.

Public surface:
    probe(project_dir, out_path, *, repo_root=None) -> dict
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from benchmark.util import save_json_preserve_order


REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent.parent
PROBE_DIR_NAME = "_quality_probe"
PROBE_VENV_NAME = "venv"
PROBE_REQUIREMENTS = "requirements.txt"
PROBE_MYPY_CONFIG = "mypy.ini"

# Top-offender cap. Five keeps the auditor's context tight; more than that
# is rarely actionable and just lengthens the prompt.
TOP_OFFENDER_CAP = 5

# Dirs that should never be linted: generated, vendored, or fixture trees.
# Pruned from os.walk, radon, ruff, mypy, and bandit traversals.
_BASE_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "_runtime_verification",
    "_quality_probe",
    "staticfiles",
    "htmlcov",
    "dist",
    "build",
    "migrations",
    "site-packages",
    "lib",
    "lib64",
    "include",
    "bin",
    "Scripts",
)

# LOC above this threshold usually means a venv or vendor tree was scanned.
_LOC_SANITY_WARN = 50_000


def _is_venv_dirname(name: str) -> bool:
    """True for ``venv``, ``env``, and any ``.venv*`` layout."""
    if name in ("venv", "env"):
        return True
    return name.startswith(".venv")


def _is_excluded_dirname(name: str) -> bool:
    if name in _BASE_EXCLUDE_DIRS:
        return True
    return _is_venv_dirname(name)


def _discover_extra_exclude_dirs(project_dir: Path) -> list[str]:
    """Walk once and collect venv-like directory names not in the base set."""
    found: set[str] = set()
    for root, dirnames, _ in os.walk(project_dir):
        for name in dirnames:
            if _is_venv_dirname(name):
                found.add(name)
        dirnames[:] = [d for d in dirnames if not _is_excluded_dirname(d)]
    return sorted(found)


def _collect_exclude_dirnames(project_dir: Path) -> tuple[str, ...]:
    extra = _discover_extra_exclude_dirs(project_dir)
    merged = list(_BASE_EXCLUDE_DIRS)
    for name in extra:
        if name not in merged:
            merged.append(name)
    return tuple(merged)


def _exclude_arg_comma(exclude_dirs: tuple[str, ...]) -> str:
    return ",".join(exclude_dirs)


def _mypy_exclude_regex(exclude_dirs: tuple[str, ...]) -> str:
    parts = [re.escape(d) for d in exclude_dirs]
    parts.extend(r"\.venv[^/]*", r"venv", r"env")
    return "|".join(parts)


def _discover_application_roots(project_dir: Path) -> list[str]:
    """Return relative dirs containing ``manage.py`` (Django app roots)."""
    roots: list[str] = []
    for path in sorted(project_dir.rglob("manage.py")):
        if any(_is_excluded_dirname(part) for part in path.relative_to(project_dir).parts):
            continue
        rel = path.parent.relative_to(project_dir)
        roots.append("." if rel == Path(".") else str(rel))
    if not roots:
        roots.append(".")
    return sorted(set(roots))


def _is_excluded_path(filepath: str) -> bool:
    normalized = filepath.replace("\\", "/").lstrip("./")
    for part in normalized.split("/"):
        if _is_excluded_dirname(part):
            return True
    return False


def probe(
    project_dir: Path,
    out_path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run the toolchain against ``project_dir``; write ``out_path``.

    Returns the JSON payload that was written. Never raises on tool
    failures — those land in the per-tool ``status`` field. Only raises
    on filesystem errors writing ``out_path`` or on a venv setup failure
    that prevents every tool from running.
    """
    project_dir = project_dir.resolve()
    repo_root = (repo_root or REPO_ROOT_DEFAULT).resolve()
    if not project_dir.is_dir():
        payload = _missing_project_payload(project_dir)
        save_json_preserve_order(out_path, payload)
        return payload

    try:
        py = ensure_probe_venv(repo_root)
    except RuntimeError as exc:
        payload = _venv_error_payload(project_dir, str(exc))
        save_json_preserve_order(out_path, payload)
        return payload

    mypy_config = repo_root / PROBE_DIR_NAME / PROBE_MYPY_CONFIG
    payload = _run_all_tools(py, project_dir, mypy_config=mypy_config)
    save_json_preserve_order(out_path, payload)
    return payload


def ensure_probe_venv(repo_root: Path) -> Path:
    """Create and populate the shared probe venv if missing; return its python.

    Idempotent: if the venv exists and the requirements file is unchanged
    since the venv's marker stamp, the venv is reused as-is.
    """
    probe_dir = repo_root / PROBE_DIR_NAME
    venv_dir = probe_dir / PROBE_VENV_NAME
    requirements = probe_dir / PROBE_REQUIREMENTS
    if not requirements.exists():
        raise RuntimeError(f"probe requirements file missing: {requirements}")
    python = venv_dir / "bin" / "python"
    stamp = venv_dir / ".requirements.sha"
    want = _hash_text(requirements.read_text())
    if python.exists() and stamp.exists() and stamp.read_text().strip() == want:
        return python
    _create_venv(venv_dir, requirements)
    stamp.write_text(want)
    return python


def _create_venv(venv_dir: Path, requirements: Path) -> None:
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    create = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        raise RuntimeError(
            f"venv create failed: {create.stderr.strip() or create.stdout.strip()}"
        )
    pip = venv_dir / "bin" / "pip"
    install = subprocess.run(
        [str(pip), "install", "--quiet", "--upgrade", "-r", str(requirements)],
        check=False,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        raise RuntimeError(
            f"probe pip install failed: {install.stderr.strip() or install.stdout.strip()}"
        )


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_all_tools(
    python: Path, project_dir: Path, *, mypy_config: Path | None = None
) -> dict[str, Any]:
    exclude_dirs = _collect_exclude_dirnames(project_dir)
    skipped_venv_dirs = _discover_extra_exclude_dirs(project_dir)
    application_roots = _discover_application_roots(project_dir)
    ruff = _run_ruff(python, project_dir, exclude_dirs=exclude_dirs)
    mypy = _run_mypy(
        python, project_dir, config_file=mypy_config, exclude_dirs=exclude_dirs
    )
    bandit = _run_bandit(python, project_dir, exclude_dirs=exclude_dirs)
    radon_cc = _run_radon_cc(python, project_dir, exclude_dirs=exclude_dirs)
    radon_mi = _run_radon_mi(python, project_dir, exclude_dirs=exclude_dirs)
    versions = _tool_versions(python)
    loc = _count_lines_of_code(project_dir, exclude_dirs=exclude_dirs)
    probe_warnings: list[str] = []
    if skipped_venv_dirs:
        probe_warnings.append(
            f"skipped venv-like dirs from application scope: {', '.join(skipped_venv_dirs)}"
        )
    if loc > _LOC_SANITY_WARN:
        probe_warnings.append(
            f"lines_of_code={loc} exceeds sanity threshold {_LOC_SANITY_WARN}; "
            "verify exclusions"
        )
    overall_status = (
        "ok"
        if any(
            t.get("status") == "ok" for t in (ruff, mypy, bandit, radon_cc, radon_mi)
        )
        else "error"
    )
    return {
        "status": overall_status,
        "project_dir": str(project_dir),
        "application_roots": application_roots,
        "exclude_dirs": list(exclude_dirs),
        "probe_warnings": probe_warnings,
        "tool_versions": versions,
        "lines_of_code": loc,
        "ruff": ruff,
        "mypy": mypy,
        "bandit": bandit,
        "radon_cc": radon_cc,
        "radon_mi": radon_mi,
    }


def _tool_versions(python: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for tool in ("ruff", "mypy", "bandit", "radon"):
        completed = subprocess.run(
            [str(python.parent / tool), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        version = (completed.stdout or completed.stderr).strip().splitlines()
        out[tool] = version[0] if version else "unknown"
    return out


def _bin(python: Path, tool: str) -> str:
    return str(python.parent / tool)


def _run_ruff(
    python: Path, project_dir: Path, *, exclude_dirs: tuple[str, ...]
) -> dict[str, Any]:
    # --isolated bypasses any pyproject.toml ruff config in the target so
    # every submission is graded against the same probe-owned rule set.
    # Rule selection: bug-finding only — F (pyflakes), B (bugbear),
    # UP (pyupgrade), SIM (simplify), RET (returns), C90 (mccabe complexity),
    # E9 (runtime errors). Stylistic rules (E5xx line-length, W whitespace)
    # are excluded so longer line limits do not penalise otherwise-clean code.
    completed = subprocess.run(
        [
            _bin(python, "ruff"),
            "check",
            "--isolated",
            "--select",
            "F,B,UP,SIM,RET,C90,E9",
            "--output-format",
            "json",
            "--exclude",
            _exclude_arg_comma(exclude_dirs),
            "--no-cache",
            ".",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    return _parse_ruff_output(
        completed.stdout, completed.stderr, completed.returncode
    )


def _parse_ruff_output(stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
    try:
        diagnostics = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return {"status": "error", "stderr": stderr.strip() or stdout[:500]}
    if not isinstance(diagnostics, list):
        return {"status": "error", "stderr": "ruff returned non-list JSON"}
    by_category: dict[str, int] = {}
    offenders: list[dict[str, Any]] = []
    for diag in diagnostics:
        code = str(diag.get("code") or "unknown")
        by_category[code] = by_category.get(code, 0) + 1
        if len(offenders) < TOP_OFFENDER_CAP:
            offenders.append(_ruff_offender_row(diag))
    return {
        "status": "ok",
        "total_errors": len(diagnostics),
        "by_category": by_category,
        "top_offenders": offenders,
        "exit_code": returncode,
    }


def _ruff_offender_row(diag: dict[str, Any]) -> dict[str, Any]:
    location = diag.get("location") or {}
    return {
        "file": str(diag.get("filename") or ""),
        "line": int(location.get("row") or 0),
        "code": str(diag.get("code") or ""),
        "message": str(diag.get("message") or "")[:200],
    }


_MYPY_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?:\d+:)?\s+(?P<level>error|note):\s+(?P<msg>.+)$"
)


def _run_mypy(
    python: Path,
    project_dir: Path,
    *,
    config_file: Path | None = None,
    exclude_dirs: tuple[str, ...] = _BASE_EXCLUDE_DIRS,
) -> dict[str, Any]:
    excludes = _mypy_exclude_regex(exclude_dirs)
    argv = [
        _bin(python, "mypy"),
        "--no-error-summary",
        "--no-pretty",
        "--no-incremental",
        "--ignore-missing-imports",
        "--exclude",
        excludes,
    ]
    if config_file is not None and config_file.exists():
        argv += ["--config-file", str(config_file)]
    argv.append(".")
    completed = subprocess.run(
        argv, check=False, capture_output=True, text=True, cwd=project_dir
    )
    return _parse_mypy_output(completed.stdout, completed.stderr)


def _parse_mypy_output(stdout: str, stderr: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for line in (stdout or "").splitlines():
        match = _MYPY_LINE_RE.match(line.strip())
        if not match or match.group("level") != "error":
            continue
        errors.append(
            {
                "file": match.group("file"),
                "line": int(match.group("line")),
                "message": match.group("msg")[:200],
            }
        )
    if not errors and stderr.strip() and "error:" not in stdout:
        head = stderr.strip().splitlines()[0][:300]
        if "no python source files" in head.lower():
            return {"status": "ok", "total_errors": 0, "top_offenders": []}
        return {"status": "error", "stderr": head}
    return {
        "status": "ok",
        "total_errors": len(errors),
        "top_offenders": errors[:TOP_OFFENDER_CAP],
    }


def _run_bandit(
    python: Path, project_dir: Path, *, exclude_dirs: tuple[str, ...]
) -> dict[str, Any]:
    exclude_args = ",".join(f"./{d}" for d in exclude_dirs)
    completed = subprocess.run(
        [
            _bin(python, "bandit"),
            "-r",
            ".",
            "-f",
            "json",
            "--quiet",
            "-x",
            exclude_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    return _parse_bandit_output(completed.stdout, completed.stderr)


def _parse_bandit_output(stdout: str, stderr: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "error", "stderr": stderr.strip() or stdout[:500]}
    results = data.get("results") or []
    app_counts = {"high": 0, "medium": 0, "low": 0}
    noise_counts = {"high": 0, "medium": 0, "low": 0}
    offenders: list[dict[str, Any]] = []
    for entry in results:
        severity = str(entry.get("issue_severity", "")).lower()
        filename = str(entry.get("filename") or "")
        excluded = _is_excluded_path(filename)
        bucket = noise_counts if excluded else app_counts
        if severity in bucket:
            bucket[severity] += 1
        if not excluded and len(offenders) < TOP_OFFENDER_CAP:
            offenders.append(
                {
                    "file": filename,
                    "line": int(entry.get("line_number") or 0),
                    "severity": severity,
                    "test_id": str(entry.get("test_id") or ""),
                    "message": str(entry.get("issue_text") or "")[:200],
                }
            )
    return {
        "status": "ok",
        "high": app_counts["high"],
        "medium": app_counts["medium"],
        "low": app_counts["low"],
        "total": sum(app_counts.values()),
        "dependency_noise": {
            **noise_counts,
            "total": sum(noise_counts.values()),
        },
        "top_offenders": offenders,
    }


def _radon_exclude_arg(exclude_dirs: tuple[str, ...]) -> str:
    patterns = [f"{d}/*" for d in exclude_dirs]
    patterns.extend(".venv*/*", "venv/*", "env/*")
    return ",".join(patterns)


def _run_radon_cc(
    python: Path, project_dir: Path, *, exclude_dirs: tuple[str, ...]
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            _bin(python, "radon"),
            "cc",
            "-j",
            "-s",
            "-e",
            _radon_exclude_arg(exclude_dirs),
            ".",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    return _parse_radon_cc_output(completed.stdout, completed.stderr)


def _parse_radon_cc_output(stdout: str, stderr: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "error", "stderr": stderr.strip() or stdout[:500]}
    offenders: list[dict[str, Any]] = []
    grade_d_or_worse = 0
    for filename, entries in data.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            complexity = int(entry.get("complexity") or 0)
            if complexity >= 11:  # grade C threshold; D = 21+, E = 31+, F = 41+
                offenders.append(
                    {
                        "file": filename,
                        "function": str(entry.get("name") or ""),
                        "line": int(entry.get("lineno") or 0),
                        "complexity": complexity,
                        "rank": str(entry.get("rank") or ""),
                    }
                )
            if complexity >= 21:
                grade_d_or_worse += 1
    offenders.sort(key=lambda r: r["complexity"], reverse=True)
    return {
        "status": "ok",
        "functions_grade_d_or_worse": grade_d_or_worse,
        "top_offenders": offenders[:TOP_OFFENDER_CAP],
    }


def _run_radon_mi(
    python: Path, project_dir: Path, *, exclude_dirs: tuple[str, ...]
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            _bin(python, "radon"),
            "mi",
            "-j",
            "-s",
            "-e",
            _radon_exclude_arg(exclude_dirs),
            ".",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    return _parse_radon_mi_output(completed.stdout, completed.stderr)


def _parse_radon_mi_output(stdout: str, stderr: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "error", "stderr": stderr.strip() or stdout[:500]}
    source_offenders, test_offenders = _split_radon_mi_offenders(data)
    return {
        "status": "ok",
        "modules_below_65": len(source_offenders),
        "test_modules_below_65": len(test_offenders),
        "top_offenders": source_offenders[:TOP_OFFENDER_CAP],
        "test_top_offenders": test_offenders[:TOP_OFFENDER_CAP],
    }


def _split_radon_mi_offenders(
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_offenders: list[dict[str, Any]] = []
    test_offenders: list[dict[str, Any]] = []
    for filename, entry in data.items():
        offender = _low_mi_offender(filename, entry)
        if offender is None:
            continue
        if _is_test_module_path(filename):
            test_offenders.append(offender)
        else:
            source_offenders.append(offender)
    source_offenders.sort(key=lambda r: r["mi"])
    test_offenders.sort(key=lambda r: r["mi"])
    return source_offenders, test_offenders


def _low_mi_offender(filename: str, entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    mi_value = float(entry.get("mi") or 0)
    if mi_value >= 65:
        return None
    return _radon_mi_offender(filename, mi_value, entry)


def _radon_mi_offender(
    filename: str, mi_value: float, entry: dict[str, Any]
) -> dict[str, Any]:
    return {
        "file": filename,
        "mi": round(mi_value, 2),
        "rank": str(entry.get("rank") or ""),
    }


def _is_test_module_path(filename: str) -> bool:
    normalized = filename.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    parts = normalized.split("/")
    return (
        "tests" in parts
        or name == "tests.py"
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _count_lines_of_code(
    project_dir: Path, *, exclude_dirs: tuple[str, ...] | None = None
) -> int:
    exclude_dirs = exclude_dirs or _collect_exclude_dirnames(project_dir)
    excluded = set(exclude_dirs)
    total = 0
    for root, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in excluded and not _is_venv_dirname(d)]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            try:
                with open(
                    Path(root) / name, encoding="utf-8", errors="ignore"
                ) as handle:
                    total += sum(1 for _ in handle)
            except OSError:
                continue
    return total


def _missing_project_payload(project_dir: Path) -> dict[str, Any]:
    return {
        "status": "error",
        "project_dir": str(project_dir),
        "error": "project_dir does not exist or is not a directory",
    }


def _venv_error_payload(project_dir: Path, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "project_dir": str(project_dir),
        "error": f"probe venv unavailable: {message}",
    }
