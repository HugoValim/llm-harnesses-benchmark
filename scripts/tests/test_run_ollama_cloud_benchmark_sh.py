"""Regression tests for full-benchmark pipeline entrypoints."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import audit_model_harness  # noqa: E402
from benchmark.util import load_json  # noqa: E402

HARNESSES_CONFIG = REPO_ROOT / "config" / "harnesses.json"
MODELS_CONFIG = REPO_ROOT / "config" / "models.json"
PIPELINE_PY = REPO_ROOT / "scripts" / "run_full_benchmark.py"
MODEL_HARNESS_SCRIPT = REPO_ROOT / "scripts" / "audit_model_harness.py"


def test_run_full_benchmark_py_passes_compile() -> None:
    subprocess.run([sys.executable, "-m", "py_compile", str(PIPELINE_PY)], check=True)


def test_audit_model_harness_lookup() -> None:
    config = load_json(HARNESSES_CONFIG)
    models_config = load_json(MODELS_CONFIG)
    assert (
        audit_model_harness(config, "deepseek_v4_pro_ollama_cloud", models_config=models_config)
        == "claude"
    )
    assert audit_model_harness(config, "kimi_k2_6_ollama_cloud", models_config=models_config) == "claude"
    assert audit_model_harness(config, "codex_gpt_5_5", models_config=models_config) == "codex"


def test_audit_model_harness_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MODEL_HARNESS_SCRIPT),
            str(HARNESSES_CONFIG),
            "deepseek_v4_pro_ollama_cloud",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "claude"
