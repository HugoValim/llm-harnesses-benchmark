"""Tests for scripts/benchmark/full_pipeline.py build matrix."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.full_pipeline import (  # noqa: E402
    BASELINE_STEPS,
    OLLAMA_BUILD_HARNESSES,
    build_benchmark_argv,
    build_matrix,
    group_build_batches,
    ollama_cloud_slugs,
    reject_forwarded_model_flag,
)

MODELS_CONFIG = REPO_ROOT / "config" / "models.json"


def test_ollama_cloud_slug_count() -> None:
    from benchmark.util import load_json

    registry = load_json(MODELS_CONFIG)["models"]
    assert len(ollama_cloud_slugs(registry)) == 8


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
    registry = load_json_models()
    steps = build_matrix(MODELS_CONFIG)
    n = len(ollama_cloud_slugs(registry))
    assert len(steps) == n * len(OLLAMA_BUILD_HARNESSES) + len(BASELINE_STEPS)


def test_reject_forwarded_model_flag() -> None:
    try:
        reject_forwarded_model_flag(["--force", "--model", "x"])
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_group_build_batches_batches_by_harness_and_report() -> None:
    steps = build_matrix(MODELS_CONFIG)
    batches = group_build_batches(steps)
    assert len(batches) == 4
    claude_batches = [b for b in batches if b.harness == "claude"]
    assert len(claude_batches) == 2
    assert {b.report_path for b in claude_batches} == {
        "docs/report.claude-code.md",
        "docs/report.claude-opus.md",
    }


def test_build_benchmark_argv_includes_jobs() -> None:
    steps = build_matrix(MODELS_CONFIG)
    batch = group_build_batches(steps)[0]
    argv = build_benchmark_argv(
        batch,
        models_config=MODELS_CONFIG,
        results_dir=REPO_ROOT / "results",
        jobs=2,
        extra_args=[],
    )
    j_index = argv.index("-j")
    assert argv[j_index + 1] == "2"


def test_list_steps_cli() -> None:
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "run_full_benchmark.py"), "--list-steps"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    registry = load_json_models()
    lines = [ln for ln in completed.stdout.strip().splitlines() if ln]
    expected = len(ollama_cloud_slugs(registry)) * len(OLLAMA_BUILD_HARNESSES) + len(
        BASELINE_STEPS
    )
    assert len(lines) == expected
    assert "claude_opus_4_7" in completed.stdout
    assert "codex_gpt_5_5" in completed.stdout


def load_json_models() -> list:
    from benchmark.util import load_json

    return load_json(MODELS_CONFIG)["models"]
