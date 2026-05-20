"""Tests for scripts/benchmark/full_pipeline.py build matrix."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.full_pipeline import (  # noqa: E402
    BASELINE_STEPS,
    OLLAMA_BUILD_HARNESSES,
    build_matrix,
    ollama_cloud_slugs,
    reject_forwarded_model_flag,
)

MODELS_CONFIG = REPO_ROOT / "config" / "models.json"


def test_ollama_cloud_slug_count() -> None:
    from benchmark.util import load_json

    registry = load_json(MODELS_CONFIG)["models"]
    assert len(ollama_cloud_slugs(registry)) == 9


def test_build_matrix_includes_all_ollama_on_three_harnesses() -> None:
    steps = build_matrix(MODELS_CONFIG)
    ollama_slugs = set(ollama_cloud_slugs(load_json_models()))
    for harness in OLLAMA_BUILD_HARNESSES:
        harness_slugs = {s.model_slug for s in steps if s.harness == harness}
        assert ollama_slugs <= harness_slugs, harness

    baseline_keys = {(h, s) for h, s, _ in BASELINE_STEPS}
    step_keys = {(s.harness, s.model_slug) for s in steps}
    assert baseline_keys <= step_keys


def test_build_matrix_step_count() -> None:
    steps = build_matrix(MODELS_CONFIG)
    # 9 ollama models × 3 harnesses + 2 baselines (opus/gpt already counted only as baselines)
    assert len(steps) == 9 * 3 + 2


def test_reject_forwarded_model_flag() -> None:
    try:
        reject_forwarded_model_flag(["--force", "--model", "x"])
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_list_steps_cli() -> None:
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_full_benchmark.py"), "--list-steps"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    lines = [ln for ln in completed.stdout.strip().splitlines() if ln]
    assert len(lines) == 9 * 3 + 2
    assert "claude_opus_4_7" in completed.stdout
    assert "codex_gpt_5_5" in completed.stdout


def load_json_models() -> list:
    from benchmark.util import load_json

    return load_json(MODELS_CONFIG)["models"]
