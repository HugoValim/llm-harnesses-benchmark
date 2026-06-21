"""Regression tests for opencode token aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark.phase_result import sum_phase_tokens  # noqa: E402
from benchmark.runner import extract_metrics  # noqa: E402


def _step_finish(input_tokens: int, output_tokens: int) -> dict[str, object]:
    return {
        "type": "step_finish",
        "part": {
            "reason": "stop",
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "reasoning": 0,
                "total": input_tokens + output_tokens,
                "cache": {"read": 0, "write": 0},
            },
        },
    }


def test_extract_metrics_sums_all_step_finish_tokens() -> None:
    events = [
        _step_finish(100, 10),
        {"type": "text", "part": {"text": "hello"}},
        _step_finish(50, 5),
    ]

    metrics = extract_metrics(events)

    assert metrics["tokens"]["input"] == 150
    assert metrics["tokens"]["output"] == 15
    assert metrics["tokens"]["total"] == 165
    assert metrics["finish_reason"] == "stop"


def test_sum_phase_tokens_adds_phase_counters() -> None:
    phases = [
        {
            "tokens": {
                "input": 100,
                "output": 10,
                "reasoning": 0,
                "total": 110,
                "cache": {"read": 1, "write": 2},
            }
        },
        {
            "tokens": {
                "input": 40,
                "output": 4,
                "reasoning": 0,
                "total": 44,
                "cache": {"read": 3, "write": 0},
            }
        },
    ]

    totals = sum_phase_tokens(phases)

    assert totals["input"] == 140
    assert totals["output"] == 14
    assert totals["total"] == 154
    assert totals["cache"] == {"read": 4, "write": 2}


def test_extract_metrics_matches_run_02_opencode_glm_5_2_streams() -> None:
    project_dir = (
        REPO_ROOT / "results/run_02/projects/opencode-glm_5_2/run_01"
    )
    if not project_dir.is_dir():
        return

    from benchmark.runner import parse_event_stream

    phase_totals: list[dict[str, object]] = []
    for stream_name in ("opencode-output.ndjson", "followup-opencode-output.ndjson"):
        stream_path = project_dir / stream_name
        if not stream_path.is_file():
            continue
        metrics = extract_metrics(parse_event_stream(stream_path.read_text()))
        phase_totals.append(metrics["tokens"])

    combined = sum_phase_tokens([{"tokens": tokens} for tokens in phase_totals])

    assert combined["total"] > 5_000_000
    assert combined["total"] < 6_000_000
