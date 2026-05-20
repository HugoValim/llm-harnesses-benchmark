"""Registry-backed audit dispatch tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_audit  # noqa: E402
from run_audit import resolve_auditors_and_targets  # noqa: E402
from benchmark.config import resolve_audit_harness_config  # noqa: E402
from benchmark.util import load_json  # noqa: E402


def _audit_row(
    slug: str = "sonnet_auditor",
    harness: str = "claude",
    model_id: str = "claude-sonnet-4-6",
) -> dict[str, object]:
    return {
        "slug": slug,
        "id": model_id,
        "label": f"{slug} label",
        "provider": "anthropic",
        "runner_type": harness,
        "selection_reason": "test row",
    }


def _build_row(slug: str, label: str) -> dict[str, object]:
    return {
        "slug": slug,
        "id": "claude-sonnet-4-6",
        "label": label,
        "selection_reason": "build metadata",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2))


@pytest.mark.parametrize("old_flag", ["--auditor", "--audit-config"])
def test_old_audit_selector_flags_are_removed(
    old_flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["run_audit.py", old_flag, "x"])

    with pytest.raises(SystemExit):
        run_audit.parse_args()


def test_resolve_audit_model_from_shared_registry(tmp_path: Path) -> None:
    benchmark_results_dir = tmp_path / "results"
    (benchmark_results_dir / "opencode-target_model" / "project").mkdir(
        parents=True
    )
    audit_config = {
        "runner": {"command": "claude"},
        "models": [
            _audit_row(),
            _build_row("sonnet_builder", "Sonnet builder"),
        ],
    }

    auditors, targets = resolve_auditors_and_targets(
        wanted_model="sonnet_auditor",
        wanted_targets=None,
        audit_config=audit_config,
        benchmark_config={},
        benchmark_results_dir=benchmark_results_dir,
        harness="claude",
    )

    assert [auditor["slug"] for auditor in auditors] == ["sonnet_auditor"]
    assert auditors[0]["main_model"] == "claude-sonnet-4-6"
    assert [target["slug"] for target in targets] == ["opencode-target_model"]


def test_resolve_audit_model_rejects_incompatible_harness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    audit_config = {
        "models": [
            {
                **_audit_row(slug="codex_auditor", model_id="gpt-5.4"),
                "harness": "codex",
            }
        ],
    }

    with pytest.raises(SystemExit) as excinfo:
        resolve_auditors_and_targets(
            wanted_model="codex_auditor",
            wanted_targets=None,
            audit_config=audit_config,
            benchmark_config={},
            benchmark_results_dir=tmp_path / "results",
            harness="claude",
        )

    assert excinfo.value.code == 1
    assert "not a claude audit model" in capsys.readouterr().err


def test_target_metadata_uses_shared_model_rows(tmp_path: Path) -> None:
    benchmark_results_dir = tmp_path / "results"
    (benchmark_results_dir / "claude-shared_slug" / "project").mkdir(parents=True)
    audit_config = {"models": [_audit_row(slug="auditor")]}
    benchmark_config = {
        "models": [
            _build_row("shared_slug", "Build target"),
        ]
    }

    _, targets = resolve_auditors_and_targets(
        wanted_model="auditor",
        wanted_targets=None,
        audit_config=audit_config,
        benchmark_config=benchmark_config,
        benchmark_results_dir=benchmark_results_dir,
        harness="claude",
    )

    assert targets[0]["label"] == "Build target"
    assert targets[0]["selection_reason"] == "build metadata"


def test_cli_preserves_audit_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    models_path = config_dir / "models.json"
    _write_json(models_path, {"models": [_audit_row()]})
    _write_json(
        config_dir / "harnesses.json",
        {
            "claude": {
                "command": "claude",
                "isolate_home": False,
                "models": {"sonnet_auditor": {"id": "claude-sonnet-4-6"}},
            }
        },
    )
    prompt_path = tmp_path / "audit_prompt.txt"
    prompt_path.write_text("{project_dir} {model_slug} {output_path}")
    benchmark_results_dir = tmp_path / "results"
    (benchmark_results_dir / "opencode-target_model" / "project").mkdir(
        parents=True
    )
    audit_reports_dir = tmp_path / "audit-reports"
    seen_result_dirs: list[Path] = []

    def fake_run_variant(**kwargs: object) -> dict[str, str]:
        result_dir = kwargs["explicit_result_dir"]
        assert isinstance(result_dir, Path)
        seen_result_dirs.append(result_dir)
        result_dir.joinpath("report.md").write_text("Total score: **90 / 100**")
        return {"status": "completed"}

    monkeypatch.setattr(
        run_audit, "_verify_auditor_binaries", lambda auditors: (True, "")
    )
    monkeypatch.setattr(run_audit, "run_variant", fake_run_variant)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_audit.py",
            "--models-config",
            str(models_path),
            "--harness",
            "claude",
            "--model",
            "sonnet_auditor",
            "--target",
            "opencode-target_model",
            "--prompt",
            str(prompt_path),
            "--results-dir",
            str(audit_reports_dir),
            "--benchmark-results-dir",
            str(benchmark_results_dir),
        ],
    )

    assert run_audit.main() == 0
    assert seen_result_dirs == [
        audit_reports_dir / "sonnet_auditor" / "opencode-target_model"
    ]
    assert (
        audit_reports_dir / "sonnet_auditor" / "opencode-target_model" / "report.md"
    ).exists()


def test_default_models_registry_resolves_audit_harnesses() -> None:
    config_path = REPO_ROOT / "config" / "models.json"
    raw = load_json(config_path)

    claude = resolve_audit_harness_config(raw, config_path, "claude")
    codex = resolve_audit_harness_config(raw, config_path, "codex")

    assert claude["runner"]["command"] == "claude"
    assert codex["runner"]["command"] == "codex"
    assert len(claude["models"]) > 0
    assert len(codex["models"]) > 0
    raw_models = raw["models"]
    assert all("role" not in model for model in raw_models)
    assert all("harness" not in model for model in raw_models)
