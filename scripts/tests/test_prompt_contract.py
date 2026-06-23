"""Prompt contract tests for benchmark and audit prompt versions."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "prompts"


def test_benchmark_prompt_v36_names_disallowed_shortcuts() -> None:
    prompt = (PROMPTS / "benchmark_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-v3.6")
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
    assert "VERIFY.md" in prompt
    assert "conftest.py" in prompt
    assert "second** `.astream()`" in prompt
    assert "AIMessage" in prompt
    assert "DJANGO_SECRET_KEY=" in prompt
    assert "SECRET_KEY=" in prompt
    assert "LLM Protocol" in prompt
    assert "Settings split" in prompt
    assert "pythonjsonlogger" in prompt
    assert "docker build --secret" in prompt
    assert "test_multi_turn_history.py" in prompt


def test_followup_prompt_v36_rechecks_frontend_wiring() -> None:
    prompt = (PROMPTS / "benchmark_followup_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: benchmark-followup-v3.6")
    assert (
        'HTMX WebSocket extension (`hx-ext="ws"` plus `ws-connect` / `ws-send`)'
        in prompt
    )
    assert "raw `new WebSocket(...)` JavaScript for the streaming path" in prompt
    assert "command/result/blocker format" in prompt
    assert "Verify production hardening (audit D9)" in prompt
    assert "web liveness" in prompt.lower() or "web HTTP port" in prompt
    assert "JSON or structured" in prompt or 'dictConfig `"()"`' in prompt
    assert "conftest.py" in prompt
    assert "DJANGO_SECRET_KEY=" in prompt


def test_agent_coding_rules_v11_has_core_sections() -> None:
    rules = (PROMPTS / "agent_coding_rules.md").read_text()

    assert rules.startswith("Prompt-Version: agent-coding-rules-v1.1")
    assert "## Operating mode (AI-driver directives)" in rules
    assert "## Safety guardrails" in rules
    assert "## Architecture (Django / Channels benchmark)" in rules
    assert "typing.Protocol" in rules
    assert "## Verification gate" in rules
    assert "caveman mode" not in rules.lower()


def test_audit_prompt_v316_anchor_calibration() -> None:
    prompt = (PROMPTS / "audit_prompt_template.txt").read_text()

    assert prompt.startswith("Prompt-Version: audit-v3.16")
    assert "{audit_preflight_block}" in prompt
    assert "MUST equal `audit-v3.16`" in prompt
    assert "primary benchmark prompt must be `benchmark-v3.5` or `benchmark-v3.6`" in prompt
    assert "follow-up prompt must be `benchmark-followup-v3.5` or `benchmark-followup-v3.6`" in prompt
    assert "D9.1=pass|fail" in prompt
    assert "Partial credit (v3.11)" in prompt
    assert "D9.1 view verification (v3.11)" in prompt
    assert "D9.2 structured logging (v3.16)" in prompt
    assert "CF#1-R (runtime tier)" in prompt
    assert "CF#1-B (build tier" in prompt
    assert "CF#1-D (documentation tier, v3.16 split)" in prompt
    assert "CF#1-D-secret-generation-example" in prompt
    assert "D8+bare-except calibration cap (v3.15, automatic)" in prompt
    assert "Core-quality D10 floor (v3.16, automatic)" in prompt
    assert "max(computed_d10, 8)" in prompt
    assert "Partial credit ladder (v3.16)" in prompt
    assert "non-empty prior assistant content" in prompt
    assert "Anchor ranking check (calibration #6)" in prompt
    assert "claude_opus_4_8" in prompt
    assert 'dictConfig `"()"`' in prompt
    assert '"class"' in prompt
    assert "D9.3 restart policy (v3.12)" in prompt
    assert "D9.5 SIGTERM handling (v3.16)" in prompt
    assert "delegated" in prompt.lower()
    assert "async for" in prompt
    assert "Independent evidence (v3.12)" in prompt
    assert "D6 cross-check (v3.11)" in prompt
    assert "${VAR:-placeholder}" in prompt
    assert "Harness preflight (v3.16)" in prompt
    assert "CF#1-B-*" in prompt
    assert "CF#9 cap (split, v3.10)" in prompt
    assert "integration-heavy" in prompt
    assert "D8 calibration cap (v3.15, automatic)" in prompt
    assert "D9 calibration cap (v3.12, automatic)" in prompt
    assert "Single stream-path handler (v3.16)" in prompt
    assert "Settings modularity (v3.16)" in prompt
    assert "Bare-handler ceiling (v3.11)" in prompt
    assert "Saturation bar (v3.11)" in prompt
    assert "Multi-turn test bar (v3.12)" in prompt
    assert "LLM Protocol (v3.12, mandatory)" in prompt
    assert "Settings split (v3.12, mandatory)" in prompt
    assert "Healthcheck distinction" in prompt
    assert "Count at most one CF#11 per generated project" in prompt
    assert "| 1-B |" in prompt
    assert "| 1-D-g |" in prompt
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
    assert "conftest.py" in prompt
    assert "VERIFY.md" in prompt


def test_anchor_v316_recovery_from_codex_gpt_5_5_run_02_pattern() -> None:
    """v3.15 dimension pattern from codex-codex_gpt_5_5/run_02 should reach ≥90 under v3.16."""
    v315_dimensions = {
        "D1": 15,
        "D2": 10,
        "D3": 10,
        "D4": 10,
        "D5": 4,
        "D6": 10,
        "D7": 11,
        "D8": 1,
        "D9": 10,
        "D10": 8,
    }
    v316_deltas = {
        "D7": 1,  # partial settings modularity (logging.py split)
        "D8": 1,  # CF#1-D generation-example tier (−1 not −2)
    }
    recovered = {
        dim: score + v316_deltas.get(dim, 0)
        for dim, score in v315_dimensions.items()
    }
    assert sum(v315_dimensions.values()) == 89
    assert sum(recovered.values()) >= 90


def test_benchmark_prompt_forbids_env_example_debug_true() -> None:
    prompt = (PROMPTS / "benchmark_prompt.txt").read_text()
    assert "`.env.example` must **not** set `DEBUG=True`" in prompt
    assert "Architecture requirements (maps to audit D7)" in prompt
    assert "typing.Protocol" in prompt


def test_meta_prompt_v318_includes_precomputed_rollup() -> None:
    prompt = (PROMPTS / "audit_meta_analysis_prompt.txt").read_text()

    assert prompt.startswith("Prompt-Version: meta-v3.18")
    assert "Methodology skeleton" in prompt
    assert "Harness inference summary" in prompt
    assert "Harness verdict" in prompt
    assert "Best quality–time tradeoff" in prompt
    assert "Executive summary skeleton" in prompt
    assert "Best open-source model overall" in prompt
    assert "not a single paragraph" in prompt.lower() or "not** a single paragraph" in prompt
    assert "DO NOT in section 1" in prompt
    assert "Harness contest" in prompt
    assert "Cursor agent models" in prompt
    assert "Contest harnesses only" in prompt
    assert "{precomputed_rollup}" in prompt
    assert "Impersonal voice" in prompt
    assert "audit-v3.16" in prompt
    assert "WARN" in prompt
    assert "absolute target band" in prompt
    assert "benchmark prompt metadata is `benchmark-v3.5`" in prompt or "benchmark-v3.6" in prompt
    assert "`benchmark-followup-v3.5` when follow-up is present" in prompt or "benchmark-followup-v3.6" in prompt
    assert "D9 sub-check" in prompt or "D9.1" in prompt
    assert "Gen-time (min)" in prompt
    assert "Tokens (M)" in prompt
    assert "Cost (USD)" in prompt
    assert "Leader anchor" not in prompt
    assert "Check 6 — Anchor ranking" in prompt
    assert "D10/10" in prompt
    assert "2a. Open-source (Ollama) model ranking" in prompt
    assert "Ollama model ranking" in prompt
    assert "cross-harness Ollama average" in prompt
