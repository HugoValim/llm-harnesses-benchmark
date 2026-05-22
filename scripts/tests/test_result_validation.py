"""Tests for benchmark.result_validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import model_enables_followup  # noqa: E402
from benchmark.result_validation import (  # noqa: E402
    MAX_VALIDATION_RETRIES,
    ValidationIssue,
    followup_expected,
    validate_benchmark_result,
    validation_retryable,
    wipe_result_dir,
)


def _write_project(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "manage.py").write_text("print('ok')\n")
    (project_dir / "requirements.txt").write_text("django\n")
    (project_dir / "README.md").write_text("# demo\n")
    (project_dir / "Dockerfile").write_text("FROM python:3.13\n")
    (project_dir / "docker-compose.yml").write_text("services: {}\n")
    settings = project_dir / "config"
    settings.mkdir()
    (settings / "settings.py").write_text("SECRET_KEY = 'x'\n")
    (project_dir / "asgi.py").write_text("application = None\n")
    tests = project_dir / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_ok():\n    assert True\n")


def _completed_row(*, works: str = "yes", phases: list | None = None) -> dict:
    summary = {
        "file_count": 8,
        "works_as_intended": works,
        "works_note": "ok" if works == "yes" else "incomplete",
        "present": {},
    }
    phase1 = {
        "phase": "phase1",
        "status": "completed",
        "exit_code": 0,
        "timed_out": False,
        "stalled": False,
        "project_summary": summary,
    }
    phase2 = {
        "phase": "phase2",
        "status": "completed",
        "exit_code": 0,
        "timed_out": False,
        "stalled": False,
        "project_summary": summary,
    }
    return {
        "result_schema_version": 2,
        "harness": "opencode",
        "status": "completed",
        "exit_code": 0,
        "finish_reason": "stop",
        "timed_out": False,
        "stalled": False,
        "project_summary": summary,
        "phases": phases if phases is not None else [phase1, phase2],
        "model": {"slug": "demo", "provider": "ollama_cloud"},
    }


def test_followup_expected_for_ollama_cloud() -> None:
    model = {"slug": "x", "provider": "ollama_cloud"}
    assert followup_expected(model, followup_prompt="phase 2", no_followup=False)
    assert not followup_expected(model, followup_prompt="phase 2", no_followup=True)
    assert not followup_expected(model, followup_prompt=None, no_followup=False)


def test_model_enables_followup_codex_default_off() -> None:
    model = {"slug": "x", "provider": "codex"}
    assert not model_enables_followup(model)


def test_validate_passes_completed_run(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    project_dir = result_dir / "project"
    _write_project(project_dir)
    (result_dir / "result.json").write_text(json.dumps(_completed_row()))

    vr = validate_benchmark_result(
        result_dir,
        model={"slug": "demo", "provider": "ollama_cloud"},
        followup_expected_flag=True,
    )
    assert vr.ok
    assert vr.fresh_status == "completed"


def test_validate_fails_on_stalled_run(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    project_dir = result_dir / "project"
    _write_project(project_dir)
    row = _completed_row()
    row["stalled"] = True
    row["status"] = "failed"
    row["phases"][0]["stalled"] = True
    row["phases"][0]["status"] = "failed"
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_benchmark_result(result_dir)
    assert not vr.ok
    assert any(i.code == "stalled" for i in vr.issues)


def test_validate_requires_phase2_when_expected(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    project_dir = result_dir / "project"
    _write_project(project_dir)
    row = _completed_row(phases=[_completed_row()["phases"][0]])
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_benchmark_result(result_dir, followup_expected_flag=True)
    assert not vr.ok
    assert any(i.code == "missing_phase2" for i in vr.issues)


def test_wipe_result_dir_removes_artifacts(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    result_dir.mkdir()
    (result_dir / "result.json").write_text("{}")
    (result_dir / "project").mkdir()

    wipe_result_dir(result_dir)

    assert result_dir.is_dir()
    assert not (result_dir / "result.json").exists()
    assert not (result_dir / "project").exists()


def test_wipe_result_dir_without_recreate_deletes_dir(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    result_dir.mkdir()
    (result_dir / "result.json").write_text("{}")

    wipe_result_dir(result_dir, recreate=False)

    assert not result_dir.exists()


def test_validation_retryable_usage_limit() -> None:
    assert not validation_retryable({"status": "usage_limit_reached"})
    assert validation_retryable({"status": "failed"})


def test_max_validation_retries_constant() -> None:
    assert MAX_VALIDATION_RETRIES == 3


def test_validate_results_remove_on_fail_cli(tmp_path: Path) -> None:
    import subprocess

    results_dir = tmp_path / "results"
    result_dir = results_dir / "opencode-bad"
    project_dir = result_dir / "project"
    _write_project(project_dir)
    row = _completed_row()
    row["status"] = "failed"
    row["exit_code"] = 1
    row["phases"][0]["status"] = "failed"
    row["phases"][0]["exit_code"] = 1
    (result_dir / "result.json").write_text(json.dumps(row))

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_dir),
            "--no-followup",
            "--remove-on-fail",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert "removed" in completed.stdout
    assert not result_dir.exists()
