"""Tests for retry target runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def test_run_retry_targets_dry_run(capsys) -> None:
    manifest = REPO_ROOT / "config" / "retry_targets_run_03.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_retry_targets.py"),
            "--targets",
            str(manifest),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "codex-gemma4" in result.stdout or "gemma4" in result.stdout
    assert "run_benchmark.py" in result.stdout
