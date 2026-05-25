"""Registry-backed audit dispatch tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_audit  # noqa: E402
from run_audit import build_audit_prompt, resolve_auditors_and_targets  # noqa: E402
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
    (benchmark_results_dir / "opencode-target_model" / "project").mkdir(parents=True)
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
    (benchmark_results_dir / "opencode-target_model" / "project").mkdir(parents=True)
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
    from benchmark.harnesses import HARNESS_REGISTRY, Harness

    fake_harness = Harness(
        name="claude",
        run_variant=fake_run_variant,
        run_model=None,
        cli_binary="claude",
        accepts_isolate_home=True,
    )
    monkeypatch.setitem(HARNESS_REGISTRY, "claude", fake_harness)
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


def test_report_only_without_model_skips_empty_auditor_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_reports_dir = tmp_path / "audit-reports"
    kimi_dir = audit_reports_dir / "kimi_k2_6_ollama_cloud" / "claude-foo"
    kimi_dir.mkdir(parents=True)
    kimi_dir.joinpath("report.md").write_text("Total score: **80 / 100**")
    (audit_reports_dir / "claude_opus_4_7").mkdir(parents=True)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_audit.py",
            "--report-only",
            "--results-dir",
            str(audit_reports_dir),
        ],
    )

    assert run_audit.main() == 0
    assert (audit_reports_dir / "kimi_k2_6_ollama_cloud" / "comparison.md").exists()
    assert not (audit_reports_dir / "claude_opus_4_7" / "comparison.md").exists()


def test_report_only_with_model_skips_auditor_without_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    models_path = config_dir / "models.json"
    _write_json(models_path, {"models": [_audit_row(slug="sonnet_auditor")]})
    _write_json(
        config_dir / "harnesses.json",
        {"claude": {"command": "claude", "isolate_home": False}},
    )
    audit_reports_dir = tmp_path / "audit-reports"
    (audit_reports_dir / "sonnet_auditor").mkdir(parents=True)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_audit.py",
            "--report-only",
            "--models-config",
            str(models_path),
            "--harness",
            "claude",
            "--model",
            "sonnet_auditor",
            "--results-dir",
            str(audit_reports_dir),
        ],
    )

    assert run_audit.main() == 1


def test_build_audit_prompt_interpolates_static_analysis_path(tmp_path: Path) -> None:
    template = (
        "model={model_slug} project={project_dir} "
        "output={output_path} qa={static_analysis_path}"
    )
    project = tmp_path / "project"
    project.mkdir()
    output = tmp_path / "report.md"
    qa = tmp_path / "static-analysis.json"

    prompt = build_audit_prompt(
        template,
        project_dir=project,
        model_slug="demo_model",
        output_path=output,
        static_analysis_path=qa,
    )

    assert "model=demo_model" in prompt
    assert f"project={project.resolve()}" in prompt
    assert f"output={output.resolve()}" in prompt
    assert f"qa={qa.resolve()}" in prompt
    # When the placeholder is unset, the literal must not leak through.
    assert "{static_analysis_path}" not in prompt


def test_build_audit_prompt_leaves_placeholder_when_path_omitted() -> None:
    # Backward-compatibility safety: callers that don't pass the path still
    # produce a usable prompt; the placeholder is left as-is so the auditor
    # treats D10 as unverified by the audit-v3.3 rubric.
    template = "qa={static_analysis_path}"
    prompt = build_audit_prompt(template, Path("/tmp/p"), "m", output_path=None)
    assert prompt == "qa={static_analysis_path}"


def test_build_audit_prompt_interpolates_generation_metrics(tmp_path: Path) -> None:
    from benchmark.pricing import format_generation_metrics_block

    template = (
        "Metrics:\n{generation_metrics_block}\n"
        "Pricing: {pricing_doc_path}\n"
        "Result: {benchmark_result_path}\n"
    )
    block = format_generation_metrics_block({"model_slug": "x", "harness": "claude"})
    prompt = build_audit_prompt(
        template,
        tmp_path / "project",
        "x",
        generation_metrics_block=block,
        pricing_doc_path=REPO_ROOT / "docs" / "PRICING.md",
        benchmark_result_path=tmp_path / "result.json",
    )
    assert "Estimated-Cost-USD" in prompt
    assert "docs/PRICING.md" in prompt or str((REPO_ROOT / "docs" / "PRICING.md").resolve()) in prompt


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
