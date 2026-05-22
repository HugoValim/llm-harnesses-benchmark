"""Tests for run_benchmark post-run validation retry loop."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.result_validation import ValidationResult  # noqa: E402
from run_benchmark import _run_with_result_validation  # noqa: E402


def test_run_with_validation_retries_until_pass(tmp_path: Path, monkeypatch) -> None:
    result_dir = tmp_path / "opencode-demo"
    result_dir.mkdir()
    calls: list[int] = []

    def run_once() -> dict:
        calls.append(1)
        return {"status": "failed"}

    outcomes = [
        ValidationResult(
            ok=False,
            result_dir=result_dir,
            slug="demo",
            harness="opencode",
            issues=[],
        ),
        ValidationResult(
            ok=True,
            result_dir=result_dir,
            slug="demo",
            harness="opencode",
        ),
    ]

    monkeypatch.setattr(
        "run_benchmark.validate_benchmark_result",
        lambda *args, **kwargs: outcomes.pop(0),
    )
    monkeypatch.setattr(
        "run_benchmark.validation_retryable",
        lambda payload: True,
    )
    wiped: list[Path] = []
    monkeypatch.setattr(
        "run_benchmark.wipe_result_dir",
        lambda path: wiped.append(path),
    )

    payload = _run_with_result_validation(
        "demo",
        result_dir,
        {"slug": "demo", "provider": "ollama_cloud"},
        expect_followup=False,
        max_retries=2,
        run_once=run_once,
    )

    assert payload == {"status": "failed"}
    assert calls == [1, 1]
    assert wiped == [result_dir]


def test_run_with_validation_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        _run_with_result_validation(
            "demo",
            Path("/tmp/x"),
            {},
            expect_followup=False,
            max_retries=-1,
            run_once=lambda: {},
        )
