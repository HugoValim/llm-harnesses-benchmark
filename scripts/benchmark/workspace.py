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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.util import (
    count_files,
    count_files_matching,
    has_file_matching,
    init_project_git,
    validate_benchmark_workspace,
    write_project_context,
)


@dataclass(frozen=True)
class ProjectWorkspace:
    """Filesystem lifecycle for one generated project workspace."""

    results_dir: Path
    result_dir: Path
    project_dir: Path

    def prepare(self, *, include_agent_rules: bool = True) -> None:
        """Create, isolate, validate, and seed the workspace context files."""
        prepare_project_workspace(
            self.results_dir,
            self.result_dir,
            self.project_dir,
            include_agent_rules=include_agent_rules,
        )

    def summarize(self) -> dict[str, Any]:
        """Return scaffold summary for the generated project."""
        return summarize_project(self.project_dir)


def prepare_project_workspace(
    results_dir: Path,
    result_dir: Path,
    project_dir: Path,
    *,
    include_agent_rules: bool = True,
) -> None:
    """Create and validate one isolated generated-project workspace."""
    result_dir.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    init_project_git(project_dir)
    validate_benchmark_workspace(results_dir, result_dir, project_dir)
    write_project_context(project_dir, include_agent_rules=include_agent_rules)

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


def summarize_project(project_dir: Path) -> dict[str, Any]:
    """Summarize whether ``project_dir`` contains the expected Django scaffold."""
    checks = {
        "manage_py": project_dir / "manage.py",
        "requirements_txt": project_dir / "requirements.txt",
        "pyproject_toml": project_dir / "pyproject.toml",
        "readme_md": project_dir / "README.md",
        "readme_lower": project_dir / "readme.md",
        "dockerfile": project_dir / "Dockerfile",
        "docker_compose_yml": project_dir / "docker-compose.yml",
        "docker_compose_yaml": project_dir / "docker-compose.yaml",
        "compose_yml": project_dir / "compose.yml",
        "compose_yaml": project_dir / "compose.yaml",
    }
    present = {name: path.exists() for name, path in checks.items()}
    _add_tree_markers(project_dir, present)
    return _project_summary_from_markers(project_dir, present)


def _add_tree_markers(project_dir: Path, present: dict[str, bool]) -> None:
    present["settings_py"] = has_file_matching(project_dir, "settings.py")
    present["asgi_py"] = has_file_matching(project_dir, "asgi.py")
    present["tests_present"] = (
        count_files_matching(project_dir, "test_*.py", limit=1) > 0
        or count_files_matching(project_dir, "*_test.py", limit=1) > 0
        or count_files_matching(project_dir, "tests.py", limit=1) > 0
    )


def _project_summary_from_markers(
    project_dir: Path,
    present: dict[str, bool],
) -> dict[str, Any]:
    files = count_files(project_dir)
    readme_present = present["readme_md"] or present["readme_lower"]
    docker_present = present["dockerfile"] and _compose_present(present)
    django_present = _python_present(present) and present["settings_py"]
    channels_present = present["asgi_py"]
    intended, note = _scaffold_intent(
        files=files,
        django_present=django_present,
        channels_present=channels_present,
        tests_present=present["tests_present"],
        readme_present=readme_present,
        docker_present=docker_present,
    )
    return {
        "file_count": files,
        "present": present,
        "works_as_intended": intended,
        "works_note": note,
    }


def _compose_present(present: dict[str, bool]) -> bool:
    return any(
        present[name]
        for name in (
            "docker_compose_yml",
            "docker_compose_yaml",
            "compose_yml",
            "compose_yaml",
        )
    )


def _python_present(present: dict[str, bool]) -> bool:
    return present["manage_py"] and (
        present["requirements_txt"] or present["pyproject_toml"]
    )


def _scaffold_intent(
    *,
    files: int,
    django_present: bool,
    channels_present: bool,
    tests_present: bool,
    readme_present: bool,
    docker_present: bool,
) -> tuple[str, str]:
    if (
        django_present
        and channels_present
        and tests_present
        and readme_present
        and docker_present
    ):
        return (
            "yes",
            "Django + Channels app, tests, README, and container files detected.",
        )
    if files == 0:
        return "no", "Project directory is empty."
    if django_present or readme_present or docker_present or tests_present:
        return (
            "partial",
            "Some expected benchmark artifacts exist, but the scaffold looks incomplete.",
        )
    return "no", "Generated files do not resemble the requested Django project."
