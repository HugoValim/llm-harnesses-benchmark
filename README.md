# LLM Python Coding Benchmark

A benchmark harness that drives autonomous coding sessions against a fixed **Python (Django + Channels chat SPA against local Ollama)** brief and compares the resulting projects across cloud LLMs.

This is a sibling project to the Rails-targeting `llm-coding-benchmark`. Same harness, different application target. The Python brief is built around APIs that LLMs frequently misremember (Ollama via `langchain-ollama` / the `ollama` Python client, deprecated community imports, Channels consumer scaffolding), so the resulting projects double as a benchmarkable signal of each model's library-API knowledge.

## What each model is asked to build

A minimal ChatGPT-style chat SPA, end-to-end:

- **Web stack:** Django + Django Channels (ASGI WebSocket consumers for streaming model output).
- **LLM client:** A real integration with a **local Ollama** server: `OLLAMA_HOST` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default `qwen2.5:7b`). The model may use `langchain-ollama`'s `ChatOllama` with `.astream(...)`, or the official `ollama` Python client with `AsyncClient` and `chat(..., stream=True)` — but it must stream tokens into the WebSocket consumer, not a stub.
- **UI:** HTMX + WebSocket extension (or a small amount of vanilla JS) for partial DOM updates, Tailwind for styling.
- **Quality tooling:** pytest (+ pytest-django, pytest-asyncio), ruff (lint + format), mypy, bandit, coverage.py, pip-audit.
- **Containerization:** Dockerfile + docker-compose, with daphne or uvicorn as the production ASGI server.

The brief deliberately excludes: Django REST Framework, authentication, Celery / background workers. Chat history can live in memory.

The full brief lives in `prompts/benchmark_prompt.txt`. A two-phase flow (`prompts/benchmark_followup_prompt.txt`) tells the model to actually boot the app, run `docker build`, and `docker compose up` after implementation.

## Why this brief

It mirrors what the Rails brief does for RubyLLM — picks a library surface that LLMs reliably hallucinate APIs for. The signals you get back:

- **Ollama / client wiring.** Wrong import paths, sync vs async misuse, missing `stream=True`, or hardcoded host/model instead of env-driven `OLLAMA_HOST` / `OLLAMA_MODEL`.
- **ASGI/WebSocket wiring.** Channels forces an async consumer (`AsyncWebsocketConsumer`, `ProtocolTypeRouter`, `URLRouter`, `channels.routing.get_default_application`). Tests whether the model knows the real scaffolding or hallucinates Flask/FastAPI patterns into a Django project.
- **Two valid stacks.** Either `langchain-ollama` or the raw `ollama` client can be correct; mixing idioms or inventing APIs is a failure mode.

## Project layout

```
python-benchmark/
├── README.md                              # this file
├── CLAUDE.md                              # AI agent guidance
├── prompts/
│   ├── benchmark_prompt.txt               # phase 1: implementation brief
│   ├── benchmark_followup_prompt.txt      # phase 2: boot + Docker validation
│   └── audit_prompt_template.txt          # LLM-powered audit rubric
├── scripts/
│   ├── run_benchmark.py                   # unified entrypoint: --harness opencode|codex|claude
│   ├── run_ollama_cloud_benchmark.sh      # fan-out Ollama Cloud models: Claude + Codex harnesses
│   ├── run_ollama_cloud_claude_benchmark.sh  # back-compat: Claude Ollama Cloud only
│   ├── run_claude_code_benchmark.py       # deprecated (use run_benchmark.py --harness claude)
│   ├── run_audit_benchmark.py             # entrypoint for LLM-powered code audits
│   ├── analyze_results_runtime.py         # post-run validator (venv, manage.py, Docker, browser probe)
│   ├── browser_probe.mjs                  # headless Chromium CDP helper
│   └── benchmark/                         # harness package (backends, runner, config, report, claude_code_runner)
├── config/
│   ├── models.json                        # opencode/codex model registry
│   ├── claude_code_models.json            # Claude Code variant registry
│   ├── claude_code_ollama_cloud_models.json
│   ├── codex_ollama_cloud_models.json     # Codex + ollama launch codex (pairs with Claude Ollama Cloud set)
│   └── audit_models.json                  # Auditor model registry
├── results/<harness>-<slug>/              # unified per-run dirs: opencode-*, codex-*, claude-* (gitignored)
├── audit-reports/<auditor>/<target>/      # Audit reports (gitignored)
└── docs/
    ├── report.md                          # default opencode aggregate (--harness opencode)
    ├── report.codex.md                    # default codex aggregate (--harness codex)
    ├── report.claude-code.md              # default Claude aggregate (--harness claude)
    └── report.ollama-cloud.*.md           # optional reports from run_ollama_cloud_benchmark.sh
```

## Default model set

| Slug | Provider | Why |
|---|---|---|
| `claude_sonnet_4_6` | OpenRouter | Strong baseline for whether the model can implement the Ollama-backed Django chat brief end-to-end. |
| `claude_opus_4_7` | OpenRouter | Tier-A baseline — measures whether stronger planning translates to fewer integration mistakes (Ollama client, Channels, Docker). |
| `kimi_k2_6` | OpenRouter | Hit Tier 3 in the Rails profile by hallucinating RubyLLM's fluent API. The Python equivalent test: does it hallucinate Ollama or Channels APIs? |
| `deepseek_v4_pro` | OpenRouter | `enable_followup: false` + `reasoning: false` — opencode's ai-sdk strips `reasoning_content` but DeepSeek's API requires it echoed back, breaking multi-turn at turn 2. The runtime analyzer (below) fills in the boot/Docker validation that phase 2 would have done. |
| `minimax_m2_7` | OpenRouter | Mid-tier model whose Python-stack knowledge is largely unmeasured here. |

Edit `config/models.json` to add/remove models. Each entry needs a `slug`, `id` (provider/model id), `label`, `provider`, and `selection_reason`.

## Prerequisites

- **opencode** on `$PATH`. The runner shells out to `opencode run --agent build --format json`. Install instructions: <https://github.com/sst/opencode>.
- **Python 3.10+** (the harness uses `X | None` union syntax).
- **Docker + Docker Compose** for the runtime verification phase.
- **Node** for the browser probe (`scripts/browser_probe.mjs` uses Chromium via the CDP).
- An **OpenRouter API key** in `OPENROUTER_API_KEY` if you run **opencode/codex** against cloud models in `config/models.json` (the harness agent uses your home opencode provider config). This is separate from the generated app, which talks to **Ollama** via `OLLAMA_HOST` / `OLLAMA_MODEL`.
- For **runtime verification** (`analyze_results_runtime.py`), ensure **Ollama** is running locally (or reachable at `OLLAMA_HOST`) with `OLLAMA_MODEL` pulled (e.g. `ollama pull qwen2.5:7b`); the analyzer injects defaults for `OLLAMA_HOST` and `OLLAMA_MODEL` into the subprocess environment when probing the generated project.
- A working **opencode config** at `~/.config/opencode/opencode.json` with the providers used in `config/models.json`. The runner copies this and writes a benchmark-isolated config at `config/opencode.benchmark.json` on each run.
- For **`--harness claude`**: `claude` on `$PATH` and a logged-in subscription (`claude login`). No `ANTHROPIC_API_KEY` needed unless you flip `runner.isolate_home` to `true` in `config/claude_code_models.json`.
- For **Codex** (`--harness codex`): `codex` on `$PATH`. For **`ollama launch codex`** models (`config/codex_ollama_cloud_models.json`), `ollama` must be on `$PATH` instead.

## Running the benchmark

You must pass **`--harness opencode`**, **`--harness codex`**, or **`--harness claude`**. Outputs go to **`results/<harness>-<slug>/`** (e.g. `results/opencode-claude_sonnet_4_6/`, `results/claude-kimi_k2_6_ollama_cloud/`).

```bash
# Phase 1+2 against default opencode models (config/models.json)
python scripts/run_benchmark.py --harness opencode

# Single model (opencode)
python scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6

# Codex-only registry (e.g. Ollama Cloud via ollama launch codex)
python scripts/run_benchmark.py --harness codex --config config/codex_ollama_cloud_models.json

# Codex with ChatGPT-linked models (plain codex, `codex login`)
python scripts/run_benchmark.py --harness codex --config config/codex_chatgpt_models.json
./scripts/run_codex_chatgpt_benchmark.sh

# Claude Code variants (config/claude_code_models.json by default)
python scripts/run_benchmark.py --harness claude
python scripts/run_benchmark.py --harness claude --variant claude_sonnet_alone

# Run the shared Ollama Cloud model matrix on both Claude + Codex back-to-back
./scripts/run_ollama_cloud_benchmark.sh

# Force re-run (overwrites existing result.json)
python scripts/run_benchmark.py --harness opencode --model kimi_k2_6 --force

# Rebuild aggregate docs without executing agents
python scripts/run_benchmark.py --harness opencode --report-only
python scripts/run_benchmark.py --harness claude --report-only
```

### Claude Code (`--harness claude`)

`--jobs/-j N` caps concurrent variants (default: one worker per variant). Pass `--jobs 1` for sequential execution, or `N > 1` for a bounded pool. Logs are prefixed with `[<slug>]`.

Under **`results/claude-<slug>/`**: `project/`, `result.json`, `stream.ndjson`, `stderr.log`, `prompt.txt`.

Aggregate report: **`docs/report.claude-code.md`** (default).

**Auth / isolation** — same as before: `runner.isolate_home` in `config/claude_code_models.json`; subscription vs `ANTHROPIC_API_KEY`.

**Ollama Cloud via Claude Code** — variants use `command_prefix: ["ollama","launch","claude"]` and `main_model` tags like `kimi-k2.6:cloud`. See `config/claude_code_ollama_cloud_models.json`. Pair with **`config/codex_ollama_cloud_models.json`** and `./scripts/run_ollama_cloud_benchmark.sh` for cross-harness comparison.

### Opencode / Codex (`--harness opencode` | `--harness codex`)

`--jobs/-j N` fans out concurrent cloud model runs the same way as Claude (default: one worker per cloud model). Pass `--jobs 1` for sequential execution, or `N > 1` for a bounded pool. Models with `provider: "ollama"` **always run sequentially** to avoid overlapping GPU-backed loads regardless of `--jobs`.

The runner loads **`models`** from the config and filters by `runner_type` (`opencode` default, or `codex`). Mixed registries are supported; reports only include rows for the active harness.

Typical artifacts under **`results/<harness>-<slug>/`**: `project/`, `result.json`, `opencode-output.ndjson`, `opencode-stderr.log`, optional `followup-*`, `session-export.json` (opencode).

Result statuses: `completed`, `completed_with_errors`, `failed`, `timeout`, `not_run`.

### Automated code audit (Tier scoring)

The auto-generated reports (`docs/report.md`, `docs/report.claude-code.md`) only give harness-level signal (status, cost, turns, tokens). The Tier 1/2/3 classification and the detailed 8-dimension rubric score must be done by reading the generated code.

`scripts/run_audit_benchmark.py` automates this by dispatching an LLM auditor against the generated project:

```bash
# Audit all benchmark variants with the default auditor (Claude Opus 4.7)
python scripts/run_audit_benchmark.py

# Use Sonnet as the auditor instead
python scripts/run_audit_benchmark.py --variant claude_sonnet_4_6

# Use Kimi (via Ollama Cloud) as the auditor
python scripts/run_audit_benchmark.py --variant kimi_k2_6_auditor

# Audit only the Sonnet-built project
python scripts/run_audit_benchmark.py --variant claude_sonnet_alone

# Run two auditors in parallel against two targets
python scripts/run_audit_benchmark.py \
    --variant claude_opus_4_7 \
    --variant kimi_k2_6_auditor \
    --variant claude_sonnet_alone \
    --variant kimi_k2_6_ollama_cloud \
    --jobs 4
```

How it works:
- `--variant` resolves slugs against `config/audit_models.json` first (auditors), then `config/claude_code_models.json` (targets).
- The default auditor registry (`config/audit_models.json`) ships with Claude Opus 4.7, Sonnet 4.6, Haiku 4.5, and Kimi K2.6 (Ollama Cloud).
- For Anthropic models, the script runs `claude -p` with Claude subscription auth.
- For non-Anthropic models, it runs `ollama launch claude --model <tag>`.
- The prompt is `prompts/audit_prompt_template.txt`, with `{project_dir}` and `{model_slug}` interpolated to point at the target's generated project.
- Each (auditor, target) pair writes to `audit-reports/<auditor_slug>/<target_slug>/`:
  - `report.md` — the LLM's markdown audit report (dimension scores, tier, verification)
  - `result.json` — metadata (status, elapsed, cost, tokens)
  - `stream.ndjson` / `stderr.log` — raw subprocess output
- After all runs, `audit-reports/comparison.md` aggregates side-by-side scores.

**Cost warning:** Auditing a full project with Opus is expensive. Start with `--variant claude_sonnet_alone --variant claude_opus_4_7` (one target, one auditor) to estimate cost before running a full matrix.

## Runtime verification

After the benchmark finishes, validate that the generated apps actually boot:

```bash
python scripts/analyze_results_runtime.py
```

Per project, this:

1. Discovers the Django app root (the directory containing `manage.py`).
2. Trusts any `mise.toml` / `.mise.toml` so the model's Python pin takes effect.
3. Creates a venv at `_runtime_verification/local/venv/`.
4. Installs dependencies — prefers `requirements.txt`, falls back to `pyproject.toml`.
5. Runs `python manage.py migrate --noinput` (non-fatal on failure).
6. Starts `python manage.py runserver --noreload 127.0.0.1:<free-port>`. With Channels in `INSTALLED_APPS` and a configured `ASGI_APPLICATION`, this dev server upgrades to the Channels ASGI runserver and supports WebSocket consumers.
7. Hits the URL with curl and runs the headless Chromium browser probe (sends "hello world" through the chat UI, checks for a streamed response).
8. Runs `docker build .`.
9. Runs `docker compose up --build -d`, detects the published port, runs the same browser probe, then tears down with `docker compose down -v`.

Per-project artifacts: `results/<harness>-<slug>/project/_runtime_verification/`. Aggregate summary: `results/runtime_verification_summary.json`.

Useful flags:

```bash
# One run only (--only matches the result directory name, including harness prefix)
python scripts/analyze_results_runtime.py --only opencode-claude_sonnet_4_6

# Cap projects (handy for sanity checks)
python scripts/analyze_results_runtime.py --max-projects 1

# Bump install timeout for slow links
python scripts/analyze_results_runtime.py --install-timeout 1800
```

## Result tiers (interpretation)

When you read the per-model output, classify the LLM integration code by hand:

- **Tier 1** — correct Ollama + Channels wiring + proper test mocking. Boots locally, Docker compose works, browser probe sees a streamed reply.
- **Tier 2** — correct primary call but partial issues (multi-turn broken, wrong package, Dockerfile bugs, deprecated LangChain community imports if using `langchain-ollama`, broken WebSocket routing).
- **Tier 3** — hallucinated API. Wrong `ChatOllama` import path, fabricated streaming hooks, `consumer.send_to_group()` with the wrong signature. Crashes on first call.

Auto-generated `docs/report.md` only shows the harness-level signal (status + tokens + tests-passing claims). The Tier classification has to come from reading the LLM-integration code by hand.

## Adding a new model

1. Edit `config/models.json` — append a `models[]` entry. Use a unique `slug`. The `id` must match a model exposed by the providers in your home opencode config (e.g. `openrouter/anthropic/claude-sonnet-4.6`).
2. If the model is on a provider you haven't wired into your home opencode config yet, add it there first — see the opencode docs.
3. Run: `python scripts/run_benchmark.py --harness opencode --model <new-slug>`.
4. Run: `python scripts/analyze_results_runtime.py --only opencode-<new-slug>`.
5. Read the LLM-integration code by hand to decide Tier 1/2/3.

You can also use the automated audit runner instead of manual reading:

```bash
# Run the default auditor (Claude Opus 4.7) against the new model's output
python scripts/run_audit_benchmark.py --variant <new-slug>
```

## Secrets handling

- The generated app brief uses **no API keys** for Ollama; configure `OLLAMA_HOST` and `OLLAMA_MODEL` only. Do not commit secrets into the repo.
- The runtime analyzer forwards `OLLAMA_HOST` / `OLLAMA_MODEL` (with defaults) into the environment when launching the local server and Docker compose so the generated app can reach Ollama during the browser probe.
- If you use **OpenRouter** for the harness (opencode cloud models), keep `OPENROUTER_API_KEY` in your user environment or secrets manager — **never commit, echo, or log the API key.** If you suspect a secret leaked into a log or generated file, rotate it immediately.

## Known harness pitfalls (inherited from the parent project)

- Stale `run_benchmark.py` or `opencode` processes can hold the opencode SQLite DB lock at `~/.local/share/opencode/opencode.db`. The runner auto-kills stale opencode processes before each model run, but if a benchmark hangs silently it's the first thing to check.
- The opencode benchmark config at `config/opencode.benchmark.json` is auto-rewritten on every run from `~/.config/opencode/opencode.json`. Don't edit it by hand.
- DeepSeek V4 Pro multi-turn is broken on opencode (the ai-sdk strips `reasoning_content` but DeepSeek requires it echoed back). The default config already disables follow-up for it; the runtime analyzer fills in the validation gap.
