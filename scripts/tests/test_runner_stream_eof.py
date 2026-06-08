"""Regression tests for stream_process_output pipe EOF handling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.runner import stream_process_output  # noqa: E402


def test_stream_process_output_exits_when_child_fails_with_stderr_only(
    tmp_path: Path,
) -> None:
    """Closed stderr pipes must not spin after the child exits immediately."""

    process = subprocess.Popen(
        ["bash", "-lc", 'echo "Config invalid" >&2; exit 1'],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_path = tmp_path / "stdout.ndjson"
    stderr_path = tmp_path / "stderr.log"

    result = stream_process_output(
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        project_dir=tmp_path,
        model_slug="test:model/phase1",
        backend=None,
        timeout_seconds=30,
        no_progress_timeout_seconds=30,
        min_preview_output_tps=None,
        min_preview_samples=0,
    )

    assert process.returncode == 1
    assert result.timed_out is False
    assert result.stalled is False
    assert "Config invalid" in result.stderr
    assert result.stdout == ""
