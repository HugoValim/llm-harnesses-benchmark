# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a benchmark harness that drives autonomous coding sessions against a fixed Python (Django + Channels chat SPA against a local Ollama server) brief and compares the resulting projects across cloud LLMs. It is the sibling project to the Rails-targeting `llm-coding-benchmark` — same harness architecture, different application target.

## Common commands

Single entrypoint — pick a harness with **`--harness {opencode,codex,claude,cursor}`** (required). Runs write under `results/<harness>-<slug>/`.

Run the full opencode benchmark (default models from `config/models.json`):
```bash
python scripts/run_benchmark.py --harness opencode
```

Run the full codex benchmark:
```bash
python scripts/run_benchmark.py --harness codex
```

Run a single model:
```bash
python scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6
```

Run the Claude Code CLI benchmark:
```bash
python scripts/run_benchmark.py --harness claude
```

Run a specific Claude Code model:
```bash
python scripts/run_benchmark.py --harness claude --model claude_sonnet_4_6
```

After a benchmark batch, the harness prunes Docker build cache and unused images by default (`docker builder prune -a` then `docker system prune -a`). Use `--no-docker-prune` to skip.

Run the per-target audits over the shared Ollama Cloud results set (skips meta-analysis):
```bash
./scripts/run_ollama_cloud_audit.sh
```

Run only the cross-auditor meta-analysis (assumes audits already ran):
```bash
./scripts/run_ollama_cloud_meta_analysis.sh
```

Run the per-project automated code audit (Role 1 — dispatches an LLM auditor against every `results/<harness>-<slug>/project` and writes one rubric `report.md` per (auditor, target) pair). By default audits **all** discovered `results/` targets and exits non-zero if any lack a scored `report.md` (use `--no-enforce-coverage` to opt out):
```bash
python scripts/run_audit.py
```

Validate pricing table coverage and refresh OpenRouter drift checks:
```bash
python scripts/validate_pricing.py
python scripts/fetch_openrouter_pricing.py --check
```

Generation cost is computed at audit time from `docs/PRICING.md` into `audit-reports/<auditor>/<target>/generation-metrics.json` (not in benchmark `result.json`).

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

2. **`--harness codex`** — models whose registry row has `"harness": "codex"`. Shells out via `codex exec --json --ephemeral` (bash-wrapped). Optional per-model `command_prefix` for **`ollama launch codex`**. No session continuity.

3. **`--harness claude`** — models whose registry row has `"harness": "claude"`. Shells out to `claude -p --output-format stream-json --dangerously-skip-permissions`. Supports subscription auth and Ollama Cloud via `ollama launch claude --model <tag>`.

4. **`--harness cursor`** — models whose registry row has `"harness": "cursor"`. Shells out to Cursor Agent CLI `agent -p --output-format stream-json --force --trust`.

`scripts/run_claude_code_benchmark.py` is **deprecated** (prints migration instructions).

### Benchmark package (`scripts/benchmark/`)

All entrypoints add `scripts/` to `sys.path` and import from the `benchmark` package:

- `backends.py` — Local model backend abstraction (`OllamaBackend`, `LlamaSwapBackend`). Handles preflight (unload/load models), GPU eviction between backends, and health checks.
- `runner.py` — Process management for opencode/codex. Spawns subprocesses, streams NDJSON stdout/stderr, detects stalls/timeouts/error loops, measures preview TPS, and kills process groups. Also handles session export and stale opencode process cleanup.
- `claude_code_runner.py` — Process management for Claude Code CLI. Similar streaming/heartbeat/stall detection but parses Claude's `stream-json` format instead of opencode's. Handles `command_prefix` for Ollama shims and `isolate_home` for agent isolation.
- `config.py` — Config loading and opencode config generation. Reads `config/models.json` plus `config/harnesses.json`, produces a benchmark-isolated config at `config/opencode.benchmark.json` with yolo permissions and local model context overrides. Also handles multi-agent subagent registration.
- `report.py` — Markdown report generation from `result.json` files (opencode/codex).
- `claude_code_report.py` — Markdown report for Claude Code model runs.
- `util.py` — Shared JSON I/O, SHA256, file counting, formatting helpers.
- `loop_detector.py` — Tool-call loop detection (repeated identical tool calls abort the run).

### Config hierarchy

- `config/models.json` — source model registry. Each model is a harness-neutral identity with `slug`, `label`, `provider`, and `selection_reason`.
- `config/harnesses.json` — source harness registry. Contains runner metadata plus the per-harness model map: model IDs, providers, command prefixes, runner type, follow-up behavior, and harness-specific options.
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
- **Stall detection:** If no stdout/stderr activity and no file count change occur for `no_progress_timeout_seconds` (default 15 minutes), the run is aborted. Error loops (5 consecutive error events) also trigger abort. Default wall-clock timeout per agent run is 50 minutes (`scripts/benchmark/timeouts.py`).
- **Preview TPS gating:** opencode runs can be aborted early if average output tokens/sec over the first N steps falls below a threshold (`--min-preview-output-tps`).
- **Home isolation:** Claude Code model rows can set `isolate_home: true` to replace `$HOME` with the result dir during the run. This prevents user-level `~/.claude/agents/*.md` from leaking in, but breaks subscription auth (requires `ANTHROPIC_API_KEY`).
- **GPU memory management:** When using local backends, the harness unloads competing backends before preflight and unloads models post-run to prevent OOM.
