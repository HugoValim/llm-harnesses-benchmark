# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a benchmark harness that drives autonomous coding sessions against a fixed Python (Django + Channels + LangChain) brief and compares the resulting projects across cloud LLMs. It is the sibling project to the Rails-targeting `llm-coding-benchmark` — same harness architecture, different application target.

## Common commands

Run the full opencode/codex benchmark:
```bash
python scripts/run_benchmark.py
```

Run a single model:
```bash
python scripts/run_benchmark.py --model claude_sonnet_4_6
```

Run the Claude Code CLI benchmark:
```bash
python scripts/run_claude_code_benchmark.py
```

Run a specific Claude Code variant:
```bash
python scripts/run_claude_code_benchmark.py --variant claude_sonnet_alone
```

Run the automated code audit (dispatches an LLM auditor against generated projects):
```bash
python scripts/run_audit_benchmark.py
```

Rebuild reports without re-running:
```bash
python scripts/run_benchmark.py --report-only
python scripts/run_claude_code_benchmark.py --report-only
python scripts/run_audit_benchmark.py --report-only
```

Validate generated apps boot correctly (venv, migrate, runserver, browser probe, Docker):
```bash
python scripts/analyze_results_runtime.py
```

Validate one model only:
```bash
python scripts/analyze_results_runtime.py --only claude_sonnet_4_6
```

## High-level architecture

### Three runner types

The harness supports three distinct ways to invoke an LLM agent:

1. **opencode** (`scripts/run_benchmark.py`) — shells out to `opencode run --agent build --format json`. Supports cloud providers (OpenRouter, etc.) and local Ollama models. Uses session IDs for multi-turn follow-up prompts.

2. **codex** (`scripts/run_benchmark.py` with `runner_type: codex` in config) — shells out to `codex exec --json --ephemeral`. Cloud-only, no session continuity. Uses bash wrapper to ensure shell environment (mise, node) is available.

3. **Claude Code** (`scripts/run_claude_code_benchmark.py`) — shells out to `claude -p --output-format stream-json --dangerously-skip-permissions`. Supports Anthropic subscription auth and Ollama-served models via `ollama launch claude --model <tag>`.

### Benchmark package (`scripts/benchmark/`)

All entrypoints add `scripts/` to `sys.path` and import from the `benchmark` package:

- `backends.py` — Local model backend abstraction (`OllamaBackend`, `LlamaSwapBackend`). Handles preflight (unload/load models), GPU eviction between backends, and health checks.
- `runner.py` — Process management for opencode/codex. Spawns subprocesses, streams NDJSON stdout/stderr, detects stalls/timeouts/error loops, measures preview TPS, and kills process groups. Also handles session export and stale opencode process cleanup.
- `claude_code_runner.py` — Process management for Claude Code CLI. Similar streaming/heartbeat/stall detection but parses Claude's `stream-json` format instead of opencode's. Handles `command_prefix` for Ollama shims and `isolate_home` for agent isolation.
- `config.py` — Config loading and opencode config generation. Reads `~/.config/opencode/opencode.json`, produces a benchmark-isolated config at `config/opencode.benchmark.json` with yolo permissions and local model context overrides. Also handles multi-agent subagent registration.
- `report.py` — Markdown report generation from `result.json` files.
- `util.py` — Shared JSON I/O, SHA256, file counting, formatting helpers.
- `loop_detector.py` — Tool-call loop detection (repeated identical tool calls abort the run).

### Config hierarchy

- `config/models.json` — opencode/codex model registry. Each model has `slug`, `id`, `provider`, `selection_reason`, and optional flags like `enable_followup`, `skip_by_default`, `ollama_model_name`, `llama_swap_model`, `opencode_subagent`.
- `config/claude_code_models.json` — Claude Code variant registry. Each variant has `slug`, `main_model`, optional `subagent`, `command_prefix`, and `env_overrides`.
- `config/audit_models.json` — Auditor registry for `run_audit_benchmark.py`. Same schema as `claude_code_models.json`.
- `config/opencode.benchmark.json` — Auto-generated on every opencode run from the home opencode config. Do not edit by hand.

### Prompts

- `prompts/benchmark_prompt.txt` — Phase 1 implementation brief (Django + Channels + LangChain chat SPA).
- `prompts/benchmark_followup_prompt.txt` — Phase 2 validation brief (boot app, run docker build, docker compose up).
- `prompts/audit_prompt_template.txt` — Rubric for automated code audits. Interpolated with `{project_dir}` and `{model_slug}`.

### Output directories

- `results/<slug>/` — opencode/codex output. Contains `project/`, `result.json`, `opencode-output.ndjson`, `opencode-stderr.log`, followup files, and `session-export.json`.
- `results-claude-code/<slug>/` — Claude Code output. Contains `project/`, `result.json`, `stream.ndjson`, `stderr.log`, `prompt.txt`.
- `audit-reports/<auditor>/<target>/` — Audit output. Contains `report.md`, `result.json`, `stream.ndjson`, `stderr.log`.
- `docs/report.md` — Auto-built aggregate report for opencode runs.
- `docs/report.claude-code.md` — Auto-built aggregate report for Claude Code runs.
- `audit-reports/comparison.md` — Side-by-side audit score comparison.

### Runtime verification (`scripts/analyze_results_runtime.py`)

Post-run validator that operates on generated projects:
1. Discovers Django app root (directory containing `manage.py`).
2. Respects `mise.toml` / `.mise.toml` for Python version pinning.
3. Creates a venv at `_runtime_verification/local/venv/`.
4. Installs dependencies (prefers `requirements.txt`, falls back to `pyproject.toml`).
5. Runs `manage.py migrate --noinput`.
6. Boots `manage.py runserver --noreload` on a free port.
7. Runs curl + headless Chromium browser probe (sends "hello world", checks for streamed response).
8. Runs `docker build .` and `docker compose up --build -d`, then repeats the browser probe.

Per-project artifacts land in `results/<slug>/project/_runtime_verification/`.

### Important patterns

- **Subprocess isolation:** All runners use `start_new_session=True` so process groups can be killed cleanly. `kill_process_group()` sends SIGTERM, waits 10s, then SIGKILL.
- **NDJSON streaming:** opencode and Claude Code both emit newline-delimited JSON events. The harness reads line-by-line via `select.select()`, writes to disk, and parses in real time for heartbeat logging and stall detection.
- **Stall detection:** If no stdout/stderr activity and no file count change occur for `no_progress_timeout_seconds`, the run is aborted. Error loops (5 consecutive error events) also trigger abort.
- **Preview TPS gating:** opencode runs can be aborted early if average output tokens/sec over the first N steps falls below a threshold (`--min-preview-output-tps`).
- **Home isolation:** Claude Code variants can set `isolate_home: true` to replace `$HOME` with the result dir during the run. This prevents user-level `~/.claude/agents/*.md` from leaking in, but breaks subscription auth (requires `ANTHROPIC_API_KEY`).
- **GPU memory management:** When using local backends, the harness unloads competing backends before preflight and unloads models post-run to prevent OOM.
