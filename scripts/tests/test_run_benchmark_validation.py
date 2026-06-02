"""Tests for run_benchmark post-run validation retry loop."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.result_validation import ValidationResult  # noqa: E402
from benchmark.campaign_dispatch import (  # noqa: E402
    previous_attempt_stalled,
    run_with_result_validation,
)


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
        "benchmark.campaign_dispatch.validate_replicate_leaf",
        lambda *args, **kwargs: outcomes.pop(0),
    )
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.validation_retryable",
        lambda payload: True,
    )
    wiped: list[Path] = []
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.wipe_result_dir",
        lambda path: wiped.append(path),
    )

    payload = run_with_result_validation(
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
        run_with_result_validation(
            "demo",
            Path("/tmp/x"),
            {},
            expect_followup=False,
            max_retries=-1,
            run_once=lambda: {},
        )


def test_previous_attempt_stalled_none_payload() -> None:
    assert previous_attempt_stalled(None) is False


def test_previous_attempt_stalled_top_level_flag() -> None:
    assert previous_attempt_stalled({"stalled": True}) is True


def test_previous_attempt_stalled_phase_flag() -> None:
    payload = {"phases": [{"phase": "phase1"}, {"phase": "phase2", "stalled": True}]}
    assert previous_attempt_stalled(payload) is True


def test_previous_attempt_stalled_clean_payload() -> None:
    payload = {"status": "completed", "phases": [{"phase": "phase1", "stalled": False}]}
    assert previous_attempt_stalled(payload) is False


def test_run_with_validation_sleeps_after_stalled_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    result_dir = tmp_path / "opencode-demo"
    result_dir.mkdir()

    payloads = [
        {"status": "failed", "stalled": True},
        {"status": "completed", "stalled": False},
    ]

    def run_once() -> dict:
        return payloads.pop(0)

    outcomes = [
        ValidationResult(
            ok=False, result_dir=result_dir, slug="demo", harness="opencode", issues=[]
        ),
        ValidationResult(
            ok=True, result_dir=result_dir, slug="demo", harness="opencode"
        ),
    ]
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.validate_replicate_leaf",
        lambda *a, **k: outcomes.pop(0),
    )
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.validation_retryable", lambda _payload: True
    )
    monkeypatch.setattr("benchmark.campaign_dispatch.wipe_result_dir", lambda _p: None)
    sleeps: list[float] = []
    monkeypatch.setattr("benchmark.campaign_dispatch.time.sleep", lambda s: sleeps.append(s))

    run_with_result_validation(
        "demo",
        result_dir,
        {"slug": "demo", "provider": "ollama_cloud"},
        expect_followup=False,
        max_retries=2,
        run_once=run_once,
    )

    assert sleeps == [60]


def test_run_with_validation_no_sleep_on_non_stall_failure(
    tmp_path: Path, monkeypatch
) -> None:
    result_dir = tmp_path / "opencode-demo"
    result_dir.mkdir()
    payloads = [
        {"status": "failed"},
        {"status": "completed"},
    ]
    outcomes = [
        ValidationResult(
            ok=False, result_dir=result_dir, slug="demo", harness="opencode", issues=[]
        ),
        ValidationResult(
            ok=True, result_dir=result_dir, slug="demo", harness="opencode"
        ),
    ]
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.validate_replicate_leaf",
        lambda *a, **k: outcomes.pop(0),
    )
    monkeypatch.setattr(
        "benchmark.campaign_dispatch.validation_retryable", lambda _payload: True
    )
    monkeypatch.setattr("benchmark.campaign_dispatch.wipe_result_dir", lambda _p: None)
    sleeps: list[float] = []
    monkeypatch.setattr("benchmark.campaign_dispatch.time.sleep", lambda s: sleeps.append(s))

    run_with_result_validation(
        "demo",
        result_dir,
        {"slug": "demo", "provider": "openrouter"},
        expect_followup=False,
        max_retries=2,
        run_once=lambda: payloads.pop(0),
    )

    assert sleeps == []
