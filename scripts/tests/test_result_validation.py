"""Tests for benchmark.result_validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.config import existing_acceptable_result  # noqa: E402
from benchmark.result_validation import (  # noqa: E402
    MAX_VALIDATION_RETRIES,
    ValidationIssue,
    followup_expected,
    validate_benchmark_result,
    validate_replicate_leaf,
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


def _write_opencode_artifacts(
    result_dir: Path,
    *,
    include_followup: bool = False,
    include_session_export: bool = False,
) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "prompt.txt").write_text("phase 1 prompt\n")
    (result_dir / "opencode-output.ndjson").write_text("{}\n")
    (result_dir / "opencode-stderr.log").write_text("")
    if include_followup:
        (result_dir / "followup-prompt.txt").write_text("phase 2 prompt\n")
        (result_dir / "followup-opencode-output.ndjson").write_text("{}\n")
        (result_dir / "followup-opencode-stderr.log").write_text("")
    if include_session_export:
        (result_dir / "session-export.json").write_text('{"info": {"directory": "/tmp"}}\n')


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


def test_followup_expected_when_prompt_configured() -> None:
    assert followup_expected(followup_prompt="phase 2")
    assert not followup_expected(followup_prompt=None)
    assert not followup_expected(followup_prompt="   ")


def test_validate_replicate_leaf_fails_without_result_json(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-qwen3_5" / "run_02"
    _write_project(result_dir / "project")

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        followup_expected_flag=True,
    )

    assert not vr.ok
    assert any(i.code == "missing_result" for i in vr.issues)


def test_validate_replicate_leaf_requires_followup_artifacts(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-qwen3_5" / "run_01"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=False)
    row = _completed_row(phases=[_completed_row()["phases"][0]])
    row["status"] = "failed"
    row["exit_code"] = -15
    row["phases"][0]["status"] = "failed"
    row["phases"][0]["exit_code"] = -15
    row["phases"][0]["project_summary"]["works_as_intended"] = "partial"
    row["project_summary"]["works_as_intended"] = "partial"
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        followup_expected_flag=True,
    )

    assert not vr.ok
    assert any(i.code == "missing_followup_prompt" for i in vr.issues)
    assert any(i.code == "missing_phase2" for i in vr.issues)


def test_validate_replicate_leaf_skips_followup_requirements_when_phase1_stalled(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "opencode-qwen3_5" / "run_01"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=False)
    row = _completed_row(phases=[_completed_row()["phases"][0]])
    row["status"] = "failed"
    row["exit_code"] = -15
    row["stalled"] = True
    row["phases"][0]["status"] = "failed"
    row["phases"][0]["exit_code"] = -15
    row["phases"][0]["stalled"] = True
    row["phases"][0]["project_summary"]["works_as_intended"] = "partial"
    row["project_summary"]["works_as_intended"] = "partial"
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        followup_expected_flag=True,
    )

    assert not vr.ok
    assert not any(i.code.startswith("missing_followup_") for i in vr.issues)
    assert not any(i.code == "missing_phase2" for i in vr.issues)


def test_validate_replicate_leaf_fails_when_recorded_path_missing(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    row["paths"] = {
        "project_dir": str(result_dir / "project"),
        "prompt": str(result_dir / "missing-prompt.txt"),
        "stdout": str(result_dir / "opencode-output.ndjson"),
        "stderr": str(result_dir / "opencode-stderr.log"),
    }
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        followup_expected_flag=True,
    )

    assert not vr.ok
    assert any(i.code == "missing_path_artifact" for i in vr.issues)


def test_validate_replicate_leaf_passes_completed_run(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True, include_session_export=True)
    row = _completed_row()
    row["session_exported"] = True
    row["opencode_session_id"] = "sess-demo"
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        model={"slug": "demo", "provider": "ollama_cloud"},
        followup_expected_flag=True,
    )

    assert vr.ok


def test_validate_replicate_leaf_codex_skips_session_export_when_not_exported(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "codex-codex_gpt_5_5" / "run_01"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    row["harness"] = "codex"
    row["opencode_session_id"] = "thread-abc"
    row["session_exported"] = False
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="codex",
        model={"slug": "codex_gpt_5_5", "provider": "openai"},
        followup_expected_flag=True,
    )

    assert vr.ok


def test_validate_replicate_leaf_opencode_requires_session_export_when_exported(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "opencode-demo" / "run_01"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    row["harness"] = "opencode"
    row["opencode_session_id"] = "sess-demo"
    row["session_exported"] = True
    (result_dir / "result.json").write_text(json.dumps(row))

    vr = validate_replicate_leaf(
        result_dir,
        harness="opencode",
        model={"slug": "demo", "provider": "ollama_cloud"},
        followup_expected_flag=True,
    )

    assert not vr.ok
    assert any(i.code == "missing_session_export" for i in vr.issues)


def test_existing_acceptable_result_rejects_failed_run(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    row["status"] = "failed"
    row["exit_code"] = 1
    (result_dir / "result.json").write_text(json.dumps(row))

    assert (
        existing_acceptable_result(
            result_dir / "result.json",
            model={"slug": "demo", "harness": "opencode"},
            followup_expected_flag=True,
        )
        is None
    )


def test_existing_acceptable_result_accepts_completed_run(tmp_path: Path) -> None:
    result_dir = tmp_path / "opencode-demo"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    (result_dir / "result.json").write_text(json.dumps(row))

    cached = existing_acceptable_result(
        result_dir / "result.json",
        model={"slug": "demo", "harness": "opencode"},
        followup_expected_flag=True,
    )

    assert cached is not None
    assert cached["status"] == "completed"


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


def _write_run_scoped_result(
    results_base: Path,
    *,
    run_id: str,
    target_group: str,
    model_slug: str,
) -> None:
    result_dir = results_base / run_id / "projects" / target_group / "run_01"
    _write_project(result_dir / "project")
    _write_opencode_artifacts(result_dir, include_followup=True)
    row = _completed_row()
    row["model"]["slug"] = model_slug
    (result_dir / "result.json").write_text(json.dumps(row))


def test_validate_results_defaults_to_latest_run(tmp_path: Path) -> None:
    import subprocess

    results_base = tmp_path / "results"
    _write_run_scoped_result(
        results_base,
        run_id="run_01",
        target_group="codex-old",
        model_slug="old",
    )
    _write_run_scoped_result(
        results_base,
        run_id="run_02",
        target_group="codex-new",
        model_slug="new",
    )

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
            "--no-enforce-replicates",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "codex-new" in completed.stdout
    assert "codex-old" not in completed.stdout
    assert "checked=1" in completed.stdout


def test_validate_results_enforces_replicates_for_auto_resolved_run(
    tmp_path: Path,
) -> None:
    import subprocess

    results_base = tmp_path / "results"
    _write_run_scoped_result(
        results_base,
        run_id="run_02",
        target_group="codex-demo",
        model_slug="demo",
    )

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_base),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 1
    assert "replicate_gaps=" in completed.stdout


def test_validate_results_brief_output_omits_issue_details(tmp_path: Path) -> None:
    import subprocess

    results_base = tmp_path / "results" / "run_02" / "projects"
    result_dir = results_base / "opencode-demo" / "run_01"
    _write_project(result_dir / "project")
    row = _completed_row()
    row["status"] = "failed"
    (result_dir / "result.json").write_text(json.dumps(row))

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(tmp_path / "results"),
            "--run-id",
            "run_02",
            "--no-enforce-replicates",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 1
    assert "[FAIL] opencode-demo/run_01" in completed.stdout
    assert "missing_followup" not in completed.stdout


def test_validate_results_verbose_includes_issue_details(tmp_path: Path) -> None:
    import subprocess

    results_base = tmp_path / "results" / "run_02" / "projects"
    result_dir = results_base / "opencode-demo" / "run_01"
    _write_project(result_dir / "project")
    row = _completed_row(phases=[_completed_row()["phases"][0]])
    (result_dir / "result.json").write_text(json.dumps(row))

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(tmp_path / "results"),
            "--run-id",
            "run_02",
            "--no-enforce-replicates",
            "--verbose",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 1
    assert "missing_phase2" in completed.stdout


def test_validate_results_checks_expected_leaves_without_result_json(
    tmp_path: Path,
) -> None:
    import subprocess

    results_base = tmp_path / "results" / "run_02" / "projects"
    run_01 = results_base / "opencode-demo" / "run_01"
    run_02 = results_base / "opencode-demo" / "run_02"
    _write_project(run_01 / "project")
    _write_opencode_artifacts(run_01, include_followup=False)
    row = _completed_row(phases=[_completed_row()["phases"][0]])
    row["status"] = "failed"
    (run_01 / "result.json").write_text(json.dumps(row))
    _write_project(run_02 / "project")

    import shutil

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "config" / "harnesses.json",
        config_dir / "harnesses.json",
    )
    models_config = config_dir / "models.json"
    models_config.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "demo",
                        "label": "Demo",
                        "provider": "openai",
                        "id": "demo",
                        "harness": "opencode",
                        "num_runs": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    script = REPO_ROOT / "scripts" / "validate_results.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(tmp_path / "results"),
            "--run-id",
            "run_02",
            "--models-config",
            str(models_config),
            "--only",
            "opencode-demo",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "[FAIL] opencode-demo/run_01" in completed.stdout
    assert "[FAIL] opencode-demo/run_02" in completed.stdout
    assert "checked=2" in completed.stdout


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
