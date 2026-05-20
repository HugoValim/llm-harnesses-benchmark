"""Regression tests for Ollama Cloud pipeline shell helpers."""

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
PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "run_ollama_cloud_benchmark.sh"
MODEL_HARNESS_SCRIPT = REPO_ROOT / "scripts" / "audit_model_harness.py"


def test_run_ollama_cloud_benchmark_sh_passes_bash_n() -> None:
    subprocess.run(["bash", "-n", str(PIPELINE_SCRIPT)], check=True)


def test_run_ollama_cloud_benchmark_sh_quotes_report_paths() -> None:
    """--report paths must be single-quoted so $5/$report cannot break the shell."""
    for line in PIPELINE_SCRIPT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("--report "):
            continue
        assert "--report '" in line, f"unquoted --report path: {stripped}"
        assert "\t" not in line.split("--report", 1)[1]
        path = line.split("--report", 1)[1].strip()
        assert path.startswith("'docs/report."), path
        assert path.rstrip(" \\").endswith(".md'"), path


def test_codex_gpt_report_path_survives_fifth_positional_param() -> None:
    """Regression: unquoted gpt-5-5 paths must not invoke ort.ollama-cloud... as a command."""
    report_flag = "'docs/report.ollama-cloud.codex-gpt-5-5.md'"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                "set -euo pipefail; "
                "set -- a b c d ort; "
                f"python3 -c 'import sys; print(sys.argv[-1])' --report {report_flag}"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        completed.stdout.strip() == "docs/report.ollama-cloud.codex-gpt-5-5.md"
    )


def test_audit_model_harness_lookup() -> None:
    config = load_json(HARNESSES_CONFIG)
    models_config = load_json(MODELS_CONFIG)
    assert audit_model_harness(config, "kimi_k2_6_ollama_cloud", models_config=models_config) == "claude"
    assert audit_model_harness(config, "codex_gpt_5_5", models_config=models_config) == "codex"


def test_audit_model_harness_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MODEL_HARNESS_SCRIPT),
            str(HARNESSES_CONFIG),
            "kimi_k2_6_ollama_cloud",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "claude"
