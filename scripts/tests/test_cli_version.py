"""Tests for harness CLI version probing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.util import (  # noqa: E402
    probe_cli_version,
    resolve_harness_cli_versions,
)


def test_probe_cli_version_returns_first_line() -> None:
    mock_completed = MagicMock()
    mock_completed.stdout = "opencode 1.2.3\n"
    mock_completed.stderr = ""
    with patch("benchmark.util.subprocess.run", return_value=mock_completed) as run:
        version = probe_cli_version(["opencode"])
    assert version == "opencode 1.2.3"
    run.assert_called_once()
    assert run.call_args[0][0] == ["opencode", "--version"]


def test_probe_cli_version_falls_back_to_stderr() -> None:
    mock_completed = MagicMock()
    mock_completed.stdout = ""
    mock_completed.stderr = "codex-cli 0.9.0\n"
    with patch("benchmark.util.subprocess.run", return_value=mock_completed):
        version = probe_cli_version(["codex"])
    assert version == "codex-cli 0.9.0"


def test_probe_cli_version_empty_argv() -> None:
    assert probe_cli_version([]) is None


def test_probe_cli_version_timeout() -> None:
    with patch(
        "benchmark.util.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1),
    ):
        assert probe_cli_version(["missing"]) is None


def test_resolve_harness_cli_versions_plain_claude() -> None:
    with patch(
        "benchmark.util.probe_cli_version",
        side_effect=lambda argv: f"v:{argv[0]}",
    ):
        fields = resolve_harness_cli_versions(harness="claude")
    assert fields["harness_cli_version"] == "v:claude"
    assert fields["harness_cli_probe_argv"] == ["claude", "--version"]
    assert fields["command_shim_version"] is None


def test_resolve_harness_cli_versions_ollama_shim() -> None:
    with patch(
        "benchmark.util.probe_cli_version",
        side_effect=lambda argv: f"v:{argv[0]}",
    ):
        fields = resolve_harness_cli_versions(
            harness="codex",
            command_prefix=["ollama", "launch", "--yes", "codex"],
        )
    assert fields["harness_cli_version"] == "v:codex"
    assert fields["command_shim_version"] == "v:ollama"
    assert fields["command_shim_probe_argv"] == ["ollama", "--version"]
