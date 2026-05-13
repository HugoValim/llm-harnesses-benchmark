# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a benchmark harness that drives autonomous coding sessions against a fixed Python (Django + Channels chat SPA against a local Ollama server) brief and compares the resulting projects across cloud LLMs. It is the sibling project to the Rails-targeting `llm-coding-benchmark` — same harness architecture, different application target.

## Common commands

Single entrypoint — pick a harness with **`--harness {opencode,codex,claude}`** (required). Runs write under `results/<harness>-<slug>/`.

Run the full opencode benchmark (default models from `config/models.json`):
```bash
python scripts/run_benchmark.py --harness opencode
```

Run the full codex benchmark (models with `"runner_type": "codex"` in the same registry, or a codex-only JSON):
```bash
python scripts/run_benchmark.py --harness codex --config config/ollama_cloud_models.json
```

Run a single model (opencode/codex):
```bash
python scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6
```

Run the Claude Code CLI benchmark (`config/claude_code_models.json` by default):
```bash
python scripts/run_benchmark.py --harness claude
```

Run a specific Claude Code variant:
```bash
python scripts/run_benchmark.py --harness claude --variant claude_sonnet_alone
```

Run the per-target audits over the shared Ollama Cloud results set (skips meta-analysis):
```bash
./scripts/run_ollama_cloud_audit.sh
```

Run only the cross-auditor meta-analysis (assumes audits already ran):
```bash
./scripts/run_ollama_cloud_meta_analysis.sh
```

Run the per-project automated code audit (Role 1 — dispatches an LLM auditor against every `results/<harness>-<slug>/project` and writes one rubric `report.md` per (auditor, target) pair):
```bash
python scripts/run_audit.py
```

Run the cross-auditor AI meta-analysis (Role 2 — reads every `audit-reports/<auditor>/<target>/report.md` and writes `audit-reports/meta-analysis.md` with best-harness / best-model / cost / dimension verdicts):
```bash
python scripts/run_meta_analysis.py
```

The legacy `scripts/run_audit_benchmark.py` is a deprecation shim that points at the two new entry points above.

Rebuild reports without re-running:
```bash
python scripts/run_benchmark.py --harness opencode --report-only
python scripts/run_benchmark.py --harness claude --report-only
python scripts/run_audit.py --report-only
```

Validate generated apps boot correctly (venv, migrate, runserver, browser probe, Docker):
```bash
python scripts/analyze_results_runtime.py
```

Validate one run only (`--only` matches the **result directory name**, e.g. `opencode-claude_sonnet_4_6`):
```bash
python scripts/analyze_results_runtime.py --only opencode-claude_sonnet_4_6
```

## High-level architecture

### Three harnesses (one entrypoint)

`scripts/run_benchmark.py` selects the agent backend with **`--harness`**:

1. **`--harness opencode`** — `opencode run --agent build --format json`. Cloud providers (OpenRouter, etc.) and local Ollama. Session IDs for multi-turn follow-up prompts.

2. **`--harness codex`** — only models with `"runner_type": "codex"` in the loaded config. Shells out via `codex exec --json --ephemeral` (bash-wrapped). Optional per-model `command_prefix` for **`ollama launch codex`** (same pattern as Claude’s `ollama launch claude`). No session continuity.

3. **`--harness claude`** — reads **`variants`** from `config/claude_code_models.json` (or `--config`). Shells out to `claude -p --output-format stream-json --dangerously-skip-permissions`. Supports subscription auth and Ollama Cloud via `ollama launch claude --model <tag>`.

`scripts/run_claude_code_benchmark.py` is **deprecated** (prints migration instructions).

### Benchmark package (`scripts/benchmark/`)

All entrypoints add `scripts/` to `sys.path` and import from the `benchmark` package:

- `backends.py` — Local model backend abstraction (`OllamaBackend`, `LlamaSwapBackend`). Handles preflight (unload/load models), GPU eviction between backends, and health checks.
- `runner.py` — Process management for opencode/codex. Spawns subprocesses, streams NDJSON stdout/stderr, detects stalls/timeouts/error loops, measures preview TPS, and kills process groups. Also handles session export and stale opencode process cleanup.
- `claude_code_runner.py` — Process management for Claude Code CLI. Similar streaming/heartbeat/stall detection but parses Claude's `stream-json` format instead of opencode's. Handles `command_prefix` for Ollama shims and `isolate_home` for agent isolation.
- `config.py` — Config loading and opencode config generation; `expand_ollama_cloud_config` flattens `ollama_cloud_models.json` for the active harness. Reads `~/.config/opencode/opencode.json`, produces a benchmark-isolated config at `config/opencode.benchmark.json` with yolo permissions and local model context overrides. Also handles multi-agent subagent registration.
- `report.py` — Markdown report generation from `result.json` files (opencode/codex).
- `claude_code_report.py` — Markdown report for Claude Code variant runs.
- `util.py` — Shared JSON I/O, SHA256, file counting, formatting helpers.
- `loop_detector.py` — Tool-call loop detection (repeated identical tool calls abort the run).

### Config hierarchy

- `config/models.json` — opencode/codex model registry. Each model has `slug`, `id`, `provider`, `selection_reason`, optional `runner_type` (`opencode` default | `codex`), `command_prefix` (for `ollama launch codex`), and optional flags like `enable_followup`, `skip_by_default`, `ollama_model_name`, `llama_swap_model`, `opencode_subagent`.
- `config/ollama_cloud_models.json` — unified Ollama Cloud model list + per-harness runner metadata; expanded at load time into `variants` (Claude) or `models` (opencode/codex/`ollama` harness).
- `config/claude_code_models.json` — Claude Code variant registry. Each variant has `slug`, `main_model`, optional `subagent`, `command_prefix`, and `env_overrides`.
- `config/audit_models.json` — Auditor registry for `run_audit.py` and `run_meta_analysis.py`. Same schema as `claude_code_models.json`.
- `config/opencode.benchmark.json` — Auto-generated on every opencode run from the home opencode config. Do not edit by hand.

### Prompts

- `prompts/benchmark_prompt.txt` — Phase 1 implementation brief (Django + Channels + Ollama chat SPA).
- `prompts/benchmark_followup_prompt.txt` — Phase 2 validation brief (boot app, run docker build, docker compose up).
- `prompts/audit_prompt_template.txt` — Rubric for automated code audits. Interpolated with `{project_dir}` and `{model_slug}`.

### Output directories

- `results/<harness>-<slug>/` — unified layout (`harness` is `opencode`, `codex`, or `claude`). Opencode/codex runs include `opencode-output.ndjson`, `opencode-stderr.log`, followup files, and `session-export.json` where applicable. Claude runs include `stream.ndjson`, `stderr.log`, `prompt.txt`.
- `audit-reports/<auditor>/<target>/` — Audit output. Contains `report.md`, `result.json`, `stream.ndjson`, `stderr.log`.
- `docs/report.md` — Auto-built aggregate report for `--harness opencode`.
- `docs/report.codex.md` — Auto-built aggregate report for `--harness codex`.
- `docs/report.claude-code.md` — Auto-built aggregate report for `--harness claude`.
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

Per-project artifacts land in `results/<harness>-<slug>/project/_runtime_verification/`.

### Important patterns

- **Subprocess isolation:** All runners use `start_new_session=True` so process groups can be killed cleanly. `kill_process_group()` sends SIGTERM, waits 10s, then SIGKILL.
- **NDJSON streaming:** opencode and Claude Code both emit newline-delimited JSON events. The harness reads line-by-line via `select.select()`, writes to disk, and parses in real time for heartbeat logging and stall detection.
- **Stall detection:** If no stdout/stderr activity and no file count change occur for `no_progress_timeout_seconds`, the run is aborted. Error loops (5 consecutive error events) also trigger abort.
- **Preview TPS gating:** opencode runs can be aborted early if average output tokens/sec over the first N steps falls below a threshold (`--min-preview-output-tps`).
- **Home isolation:** Claude Code variants can set `isolate_home: true` to replace `$HOME` with the result dir during the run. This prevents user-level `~/.claude/agents/*.md` from leaking in, but breaks subscription auth (requires `ANTHROPIC_API_KEY`).
- **GPU memory management:** When using local backends, the harness unloads competing backends before preflight and unloads models post-run to prevent OOM.
