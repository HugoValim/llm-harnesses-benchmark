"""Project-workspace lifecycle for benchmark runs.

Owns:

- detection of files the coding agent wrote *outside* its sandbox
  (``results/<harness>-<slug>/project/``), so the workspace can be marked
  failed instead of silently leaving stray markers at the repo root,
- snapshotting the repo-root file set before a run begins, so we can diff
  against it after the agent exits,
- reading the opencode session-export to spot when a session was opened
  with a directory other than the project dir.

Extracted from ``runner.py`` to give workspace logic a focused module
maintainers can navigate without reading the orchestration giant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.config import summarize_project

# File names whose appearance at the repo root indicates an agent wrote
# outside its sandbox. Matches typical Django/Docker/JS project markers
# the benchmark prompt would produce.
_ROOT_WORKSPACE_ESCAPE_MARKERS: frozenset[str] = frozenset(
    {
        "manage.py",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "requirements.txt",
        "pyproject.toml",
        "chat",
        "templates",
    }
)


def snapshot_root_generated_markers(root_dir: Path, results_dir: Path) -> frozenset[str]:
    """Return root-level generated app markers, excluding the benchmark results tree."""
    if not root_dir.exists():
        return frozenset()
    results_name = results_dir.resolve().name
    return frozenset(
        child.name
        for child in root_dir.iterdir()
        if child.name != results_name and child.name in _ROOT_WORKSPACE_ESCAPE_MARKERS
    )


def _read_opencode_session_directory(session_export_path: Path | None) -> Path | None:
    if session_export_path is None or not session_export_path.exists():
        return None
    try:
        session_export = json.loads(session_export_path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(session_export, dict):
        return None
    info = session_export.get("info")
    if not isinstance(info, dict):
        return None
    directory = info.get("directory")
    if not isinstance(directory, str) or not directory:
        return None
    return Path(directory).resolve()


def _escaped_session_directory(
    session_export_path: Path | None, project_dir: Path
) -> Path | None:
    session_directory = _read_opencode_session_directory(session_export_path)
    if session_directory is None:
        return None
    if session_directory == project_dir.resolve():
        return None
    return session_directory


def detect_workspace_escape(
    payload: dict[str, Any],
    *,
    root_dir: Path,
    results_dir: Path,
    project_dir: Path,
    before_markers: frozenset[str],
    session_export_path: Path | None = None,
) -> dict[str, Any]:
    """Mark phase payload failed when new root markers appear and project output is incomplete."""
    project_summary = payload.get("project_summary")
    if not isinstance(project_summary, dict):
        project_summary = summarize_project(project_dir)
    current_markers = snapshot_root_generated_markers(root_dir, results_dir)
    unexpected_paths = sorted(current_markers - before_markers)
    session_directory = _escaped_session_directory(session_export_path, project_dir)
    if session_directory is None and (
        not unexpected_paths or project_summary.get("works_as_intended") == "yes"
    ):
        return payload
    checked = dict(payload)
    checked["status"] = "failed"
    checked["workspace_escape_detected"] = True
    checked["workspace_escape_paths"] = unexpected_paths
    if session_directory is not None:
        checked["workspace_escape_session_directory"] = str(session_directory)
    return checked
