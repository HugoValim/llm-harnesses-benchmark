"""Prompt contract tests for benchmark and audit prompt versions."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "prompts"


def test_benchmark_prompt_v33_names_disallowed_shortcuts() -> None:
    prompt = (PROMPTS / "benchmark_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-v3.3")
    assert (
        "Do not implement browser streaming with app-owned raw `new WebSocket(...)`"
        in prompt
    )
    assert 'HTMX `hx-ext="ws"` plus `ws-connect` / `ws-send`' in prompt
    assert "Do not use Tailwind CDN" in prompt
    assert "Do not import or use the direct `ollama` Python package" in prompt
    assert "Verification summary format:" in prompt
    assert "a bare `pass` disconnect is invalid" in prompt
    assert "18. Production hardening" in prompt
    assert "D9.1 Docker/compose healthcheck" in prompt
    assert "D9.5 Graceful WebSocket shutdown" in prompt
    assert "asyncio.CancelledError" in prompt


def test_followup_prompt_v33_rechecks_frontend_wiring() -> None:
    prompt = (PROMPTS / "benchmark_followup_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-followup-v3.3")
    assert (
        'HTMX WebSocket extension (`hx-ext="ws"` plus `ws-connect` / `ws-send`)'
        in prompt
    )
    assert "raw `new WebSocket(...)` JavaScript for the streaming path" in prompt
    assert "command/result/blocker format" in prompt
    assert "Verify production hardening (audit D9)" in prompt
    assert "web liveness" in prompt.lower() or "web HTTP port" in prompt


def test_agent_coding_rules_v10_has_core_sections() -> None:
    rules = (PROMPTS / "agent_coding_rules.md").read_text()

    assert rules.startswith("Prompt-Version: agent-coding-rules-v1.0")
    assert "## Operating mode (AI-driver directives)" in rules
    assert "## Safety guardrails" in rules
    assert "## Verification gate" in rules
    assert "caveman mode" not in rules.lower()


def test_audit_prompt_v39_auditor_owned_d10_no_probe() -> None:
    prompt = (PROMPTS / "audit_prompt_template.txt").read_text()

    assert prompt.startswith("Prompt-Version: audit-v3.9")
    assert "MUST equal `audit-v3.9`" in prompt
    assert "primary benchmark prompt must be `benchmark-v3.3`" in prompt
    assert "follow-up prompt must be `benchmark-followup-v3.3`" in prompt
    assert "D9.1=pass|fail" in prompt
    assert "D8/D9 calibration cap" in prompt
    assert "Healthcheck distinction" in prompt
    assert "Count at most one CF#11 per generated project" in prompt
    assert "{static_analysis_path}" not in prompt
    assert "{d10_evidence_block}" not in prompt
    assert "static-analysis.json" not in prompt
    assert "_quality_probe" not in prompt
    assert "D10 | Code quality | 10" in prompt
    assert "You assign D10" in prompt
    assert "grep `{project_dir}`" in prompt
    assert "D2 | LLM integration correctness | 10" in prompt
    assert "D3 | Test quality | 10" in prompt
    assert "D5 | Persistence / multi-turn | 5" in prompt
    assert "D7 | Architecture | 15" in prompt
    assert "D8 | Secrets & config hygiene | 5" in prompt
    assert "D9 | Production hardening | 10" in prompt
    assert "D10 | Code quality | 10" in prompt
    assert "exactly **ten** rows" in prompt
    assert "D1=15, D2=10, D3=10, D4=10, D5=5, D6=10, D7=15, D8=5, D9=10, D10=10" in prompt
    assert "Tier cap:" in prompt


def test_meta_prompt_v313_includes_precomputed_rollup() -> None:
    prompt = (PROMPTS / "audit_meta_analysis_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: meta-v3.13")
    assert "Executive summary skeleton" in prompt
    assert "Best open-source model overall" in prompt
    assert "not a single paragraph" in prompt.lower() or "not** a single paragraph" in prompt
    assert "DO NOT in section 1" in prompt
    assert "Harness contest" in prompt
    assert "Cursor agent models" in prompt
    assert "Contest harnesses only" in prompt
    assert "{precomputed_rollup}" in prompt
    assert "Harness CLI versions" in prompt
    assert "mixed-harness-version" in prompt
    assert "audit-v3.9" in prompt
    assert "benchmark prompt metadata is `benchmark-v3.3`" in prompt
    assert "`benchmark-followup-v3.3` when follow-up is present" in prompt
    assert "D9 sub-check" in prompt or "D9.1" in prompt
    assert "Gen-time (min)" in prompt
    assert "Tokens (M)" in prompt
    assert "Cost (USD)" in prompt
    assert "Leader anchor" not in prompt
    assert "Check 5 — D10 floor" in prompt
    assert "D10/10" in prompt
    assert "2a. Open-source (Ollama) model ranking" in prompt
    assert "Ollama model ranking" in prompt
    assert "cross-harness Ollama average" in prompt
