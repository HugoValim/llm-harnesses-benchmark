"""Prompt contract tests for benchmark and audit prompt versions."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "prompts"


def test_benchmark_prompt_v32_names_disallowed_shortcuts() -> None:
    prompt = (PROMPTS / "benchmark_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-v3.2")
    assert (
        "Do not implement browser streaming with app-owned raw `new WebSocket(...)`"
        in prompt
    )
    assert 'HTMX `hx-ext="ws"` plus `ws-connect` / `ws-send`' in prompt
    assert "Do not use Tailwind CDN" in prompt
    assert "Do not import or use the direct `ollama` Python package" in prompt
    assert "Verification summary format:" in prompt
    assert "a bare `pass` disconnect is invalid" in prompt


def test_followup_prompt_v32_rechecks_frontend_wiring() -> None:
    prompt = (PROMPTS / "benchmark_followup_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-followup-v3.2")
    assert (
        'HTMX WebSocket extension (`hx-ext="ws"` plus `ws-connect` / `ws-send`)'
        in prompt
    )
    assert "raw `new WebSocket(...)` JavaScript for the streaming path" in prompt
    assert "command/result/blocker format" in prompt


def test_audit_prompt_v36_rebalanced_weights() -> None:
    prompt = (PROMPTS / "audit_prompt_template.txt").read_text()

    assert prompt.startswith("Prompt-Version: audit-v3.6")
    assert "MUST equal `audit-v3.6`" in prompt
    assert "primary benchmark prompt must be `benchmark-v3.2`" in prompt
    assert "follow-up prompt must be `benchmark-followup-v3.2`" in prompt
    assert "Count at most one CF#11 per generated project" in prompt
    assert "`tests.py`, `test_*.py`, and `*_test.py`" in prompt
    assert "If only test files are below 65, no D10 deduction" in prompt
    assert "{d10_precomputed_block}" in prompt
    assert "award **3/10** by default" in prompt
    assert "D2 | LLM integration correctness | 10" in prompt
    assert "D3 | Test quality | 10" in prompt
    assert "D5 | Persistence / multi-turn | 5" in prompt
    assert "D7 | Architecture | 15" in prompt
    assert "D8 | Secrets & config hygiene | 5" in prompt
    assert "D9 | Production hardening | 10" in prompt
    assert "D10 | Code quality (tool-backed) | 10" in prompt
    assert "exactly **ten** rows" in prompt
    assert "D1=15, D2=10, D3=10, D4=10, D5=5, D6=10, D7=15, D8=5, D9=10, D10=10" in prompt
    assert "Tier cap:" in prompt


def test_meta_prompt_v35_filters_current_prompt_versions() -> None:
    prompt = (PROMPTS / "audit_meta_analysis_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: meta-v3.5")
    assert "audit-v3.4" in prompt
    assert "benchmark prompt metadata is `benchmark-v3.2`" in prompt
    assert "`benchmark-followup-v3.2` when follow-up is present" in prompt
