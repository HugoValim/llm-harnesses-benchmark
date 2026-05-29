"""Tests for deterministic D10 scoring and reconciliation."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.audit_d10 import (  # noqa: E402
    compute_d10_from_probe,
    format_d10_precomputed_block,
    reconcile_report_d10,
)


def test_compute_d10_clean_probe() -> None:
    payload = {
        "status": "ok",
        "lines_of_code": 500,
        "ruff": {"total_errors": 0},
        "mypy": {"total_errors": 0},
        "bandit": {"high": 0, "medium": 0},
        "radon_cc": {"top_offenders": []},
        "radon_mi": {"modules_below_65": 0},
    }
    result = compute_d10_from_probe(payload)
    assert result.score == 10
    assert result.verified is True
    assert result.cf13 is False


def test_compute_d10_bandit_high_triggers_cf13() -> None:
    payload = {
        "status": "ok",
        "lines_of_code": 500,
        "ruff": {"total_errors": 0},
        "mypy": {"total_errors": 0},
        "bandit": {"high": 2, "medium": 0},
        "radon_cc": {"top_offenders": []},
        "radon_mi": {"modules_below_65": 0},
    }
    result = compute_d10_from_probe(payload)
    assert result.score == 0
    assert result.cf13 is True


def test_compute_d10_unverified_when_probe_missing() -> None:
    result = compute_d10_from_probe(None)
    assert result.score == 3
    assert result.verified is False


def test_format_d10_precomputed_block() -> None:
    from benchmark.audit_d10 import D10Result

    block = format_d10_precomputed_block(D10Result(score=8, reasons=["ok"]))
    assert "Precomputed D10" in block
    assert "8/10" in block
    assert "Mandatory" in block


def test_reconcile_report_patches_inflated_d10(tmp_path: Path) -> None:
    from benchmark.audit_d10 import D10Result

    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "| 10 | Code quality (tool-backed) | 9 / 10 | inflated |",
                "",
                "C. **Total score / 100**",
                "",
                "**95 / 100**",
            ]
        )
    )
    recon_path = tmp_path / "d10-reconciliation.json"
    payload = reconcile_report_d10(
        report,
        D10Result(score=7, reasons=["bandit.high=1: -2"]),
        reconciliation_path=recon_path,
    )
    assert payload["action"] == "patched_downward"
    assert payload["patched"] is True
    text = report.read_text()
    assert "| 10 | Code quality (tool-backed) | 7 / 10 |" in text
    assert "**93 / 100**" in text or "**92 / 100**" in text
