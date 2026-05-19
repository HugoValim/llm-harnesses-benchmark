"""Regression tests for Ollama Cloud pipeline shell helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_report import audit_variant_runner_type  # noqa: E402
from benchmark.util import load_json  # noqa: E402

AUDIT_CONFIG = REPO_ROOT / "config" / "audit_models.json"
PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "run_ollama_cloud_benchmark.sh"
RUNNER_TYPE_SCRIPT = REPO_ROOT / "scripts" / "audit_variant_runner_type.py"


def test_run_ollama_cloud_benchmark_sh_passes_bash_n() -> None:
    subprocess.run(["bash", "-n", str(PIPELINE_SCRIPT)], check=True)


def test_audit_variant_runner_type_lookup() -> None:
    config = load_json(AUDIT_CONFIG)
    assert audit_variant_runner_type(config, "kimi_k2_6_ollama_cloud") == "claude"


def test_audit_variant_runner_type_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER_TYPE_SCRIPT),
            str(AUDIT_CONFIG),
            "kimi_k2_6_ollama_cloud",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "claude"
