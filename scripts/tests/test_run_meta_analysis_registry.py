"""Registry-backed meta-analysis dispatch tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_meta_analysis  # noqa: E402
from benchmark.audit_report import resolve_meta_variant  # noqa: E402


def _meta_row(
    slug: str = "sonnet_meta",
    harness: str = "claude",
    model_id: str = "claude-sonnet-4-6",
) -> dict[str, object]:
    return {
        "slug": slug,
        "id": model_id,
        "label": f"{slug} label",
        "provider": "anthropic",
        "runner_type": harness,
        "selection_reason": "test meta row",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2))


def test_resolve_meta_model_from_shared_registry() -> None:
    meta_config = {
        "models": [
            {
                **_meta_row(slug="sonnet_auditor"),
                "selection_reason": "audit row",
            },
            {**_meta_row(), "harness": "claude"},
        ],
    }

    variant = resolve_meta_variant(meta_config, "claude", "sonnet_meta")

    assert variant["slug"] == "sonnet_meta"
    assert variant["main_model"] == "claude-sonnet-4-6"


def test_resolve_meta_model_rejects_incompatible_harness() -> None:
    meta_config = {"models": [{**_meta_row(slug="codex_meta"), "harness": "codex"}]}

    with pytest.raises(ValueError, match="not a claude meta model"):
        resolve_meta_variant(meta_config, "claude", "codex_meta")


def test_cli_preserves_meta_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    models_path = config_dir / "models.json"
    _write_json(models_path, {"models": [_meta_row()]})
    _write_json(
        config_dir / "harnesses.json",
        {
            "claude": {
                "command": "claude",
                "models": {"sonnet_meta": {"id": "claude-sonnet-4-6"}},
            }
        },
    )
    prompt_path = tmp_path / "meta_prompt.txt"
    prompt_path.write_text("{audit_input_dirs} {output_path}")
    reports_dir = tmp_path / "audit-reports"
    input_dir = reports_dir / "sonnet_auditor"
    target_dir = input_dir / "opencode-target_model"
    target_dir.mkdir(parents=True)
    (target_dir / "report.md").write_text("Total score: **90 / 100**")
    seen: dict[str, object] = {}

    def fake_run_ai_meta_analysis(**kwargs: object) -> dict[str, str]:
        reports_path = kwargs["reports_dir"]
        assert isinstance(reports_path, Path)
        seen.update(kwargs)
        reports_path.joinpath("meta-analysis.md").write_text("meta")
        return {"status": "completed"}

    monkeypatch.setattr(run_meta_analysis.shutil, "which", lambda _: "/bin/tool")
    monkeypatch.setattr(
        run_meta_analysis, "run_ai_meta_analysis", fake_run_ai_meta_analysis
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_meta_analysis.py",
            "--models-config",
            str(models_path),
            "--harness",
            "claude",
            "--model",
            "sonnet_meta",
            "--results-dir",
            str(reports_dir),
            "--meta-input-dir",
            "sonnet_auditor",
            "--meta-prompt",
            str(prompt_path),
        ],
    )

    assert run_meta_analysis.main() == 0
    assert seen["reports_dir"] == reports_dir / "sonnet_meta"
    assert seen["audit_input_dirs"] == [input_dir.resolve()]
    assert seen["harness"] == "claude"
    assert (reports_dir / "sonnet_meta" / "comparison.md").exists()
