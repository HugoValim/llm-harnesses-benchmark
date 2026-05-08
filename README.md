# LLM Python Coding Benchmark

A benchmark harness that drives autonomous coding sessions against a fixed **Python (Django + Channels + LangChain)** brief and compares the resulting projects across cloud LLMs.

This is a sibling project to the Rails-targeting `llm-coding-benchmark`. Same harness, different application target. The Python brief is built around library APIs that LLMs frequently misremember (LangChain's import paths, deprecated `LLMChain`, Channels consumer scaffolding), so the resulting projects double as a benchmarkable signal of each model's library-API knowledge.

## What each model is asked to build

A minimal ChatGPT-style chat SPA, end-to-end:

- **Web stack:** Django + Django Channels (ASGI WebSocket consumers for streaming model output).
- **LLM client:** Latest LangChain (with `langchain-anthropic`) wired to OpenRouter, calling the latest Claude Sonnet. The model picks the wiring (`ChatAnthropic` w/ custom `base_url`, or `ChatOpenAI` against the OpenAI-compat endpoint with `model="anthropic/claude-sonnet-4.6"`) — but it must be a real, working configuration.
- **UI:** HTMX + WebSocket extension (or a small amount of vanilla JS) for partial DOM updates, Tailwind for styling.
- **Quality tooling:** pytest (+ pytest-django, pytest-asyncio), ruff (lint + format), mypy, bandit, coverage.py, pip-audit.
- **Containerization:** Dockerfile + docker-compose, with daphne or uvicorn as the production ASGI server.

The brief deliberately excludes: Django REST Framework, authentication, Celery / background workers. Chat history can live in memory.

The full brief lives in `prompts/benchmark_prompt.txt`. A two-phase flow (`prompts/benchmark_followup_prompt.txt`) tells the model to actually boot the app, run `docker build`, and `docker compose up` after implementation.

## Why this brief

It mirrors what the Rails brief does for RubyLLM — picks a library that LLMs reliably hallucinate APIs for. The signals you get back:

- **LangChain hallucination surface.** `from langchain.chat_models` vs `langchain_anthropic`, deprecated `LLMChain`, fabricated streaming hooks, `.invoke` vs `.run` vs `.predict` confusion.
- **ASGI/WebSocket wiring.** Channels forces an async consumer (`AsyncWebsocketConsumer`, `ProtocolTypeRouter`, `URLRouter`, `channels.routing.get_default_application`). Tests whether the model knows the real scaffolding or hallucinates Flask/FastAPI patterns into a Django project.
- **Two-SDK glue.** LangChain calling Anthropic models *through OpenRouter* has at least two correct wirings. Models that pick one and execute cleanly are stronger than those that mix idioms.

## Project layout

```
python-benchmark/
├── README.md                              # this file
├── CLAUDE.md                              # AI agent guidance
├── config/
│   └── models.json                        # 5-model curated set
├── prompts/
│   ├── benchmark_prompt.txt               # phase 1: implementation brief
│   ├── benchmark_followup_prompt.txt      # phase 2: boot + Docker validation
│   └── audit_prompt_template.txt          # LLM-powered audit rubric
├── scripts/
│   ├── run_benchmark.py                   # main entrypoint (opencode/codex)
│   ├── run_claude_code_benchmark.py       # entrypoint for Claude Code CLI variants
│   ├── run_audit_benchmark.py             # entrypoint for LLM-powered code audits
│   ├── analyze_results_runtime.py         # post-run validator (venv, manage.py, Docker, browser probe)
│   ├── browser_probe.mjs                  # headless Chromium CDP helper
│   └── benchmark/                         # harness package (backends, runner, config, report, claude_code_runner)
├── config/
│   ├── models.json                        # opencode/codex model registry
│   ├── claude_code_models.json            # Claude Code variant registry
│   └── audit_models.json                  # Auditor model registry
├── results/<slug>/                        # per-model output (gitignored)
├── results-claude-code/<slug>/            # Claude Code variant output (gitignored)
├── audit-reports/<auditor>/<target>/      # Audit reports (gitignored)
└── docs/
    ├── report.md                          # auto-built consolidated report (opencode)
    └── report.claude-code.md              # auto-built consolidated report (Claude Code)
```

## Default model set

| Slug | Provider | Why |
|---|---|---|
| `claude_sonnet_4_6` | OpenRouter | The reference model the brief asks the build to wire into LangChain — running it as a target tests whether Sonnet can produce a working Sonnet-backed app. |
| `claude_opus_4_7` | OpenRouter | Tier-A baseline — measures whether stronger planning translates to fewer LangChain hallucinations. |
| `kimi_k2_6` | OpenRouter | Hit Tier 3 in the Rails profile by hallucinating RubyLLM's fluent API. The Python equivalent test: does it hallucinate LangChain APIs? |
| `deepseek_v4_pro` | OpenRouter | `enable_followup: false` + `reasoning: false` — opencode's ai-sdk strips `reasoning_content` but DeepSeek's API requires it echoed back, breaking multi-turn at turn 2. The runtime analyzer (below) fills in the boot/Docker validation that phase 2 would have done. |
| `minimax_m2_7` | OpenRouter | Mid-tier model whose Python-stack knowledge is largely unmeasured here. |

Edit `config/models.json` to add/remove models. Each entry needs a `slug`, `id` (provider/model id), `label`, `provider`, and `selection_reason`.

## Prerequisites

- **opencode** on `$PATH`. The runner shells out to `opencode run --agent build --format json`. Install instructions: <https://github.com/sst/opencode>.
- **Python 3.10+** (the harness uses `X | None` union syntax).
- **Docker + Docker Compose** for the runtime verification phase.
- **Node** for the browser probe (`scripts/browser_probe.mjs` uses Chromium via the CDP).
- An **OpenRouter API key** in `OPENROUTER_API_KEY` for the opencode runs. The brief tells the model to source `~/.config/zsh/secrets`; the runner picks that up too.
- A working **opencode config** at `~/.config/opencode/opencode.json` with the providers used in `config/models.json`. The runner copies this and writes a benchmark-isolated config at `config/opencode.benchmark.json` on each run.
- For the **Claude Code** runs (`run_claude_code_benchmark.py`): just `claude` on `$PATH` and a logged-in subscription (`claude login`). No `ANTHROPIC_API_KEY` needed unless you flip `runner.isolate_home` to `true` in `config/claude_code_models.json`.

## Running the benchmark

```bash
# Phase 1+2 against all five default models (opencode runner)
python scripts/run_benchmark.py

# Single model
python scripts/run_benchmark.py --model claude_sonnet_4_6

# Force re-run (overwrites existing result.json)
python scripts/run_benchmark.py --model kimi_k2_6 --force

# Rebuild docs/report.md from existing results without running anything
python scripts/run_benchmark.py --report-only
```

### Running through Claude Code instead of opencode

`run_benchmark.py` only handles `opencode`/`codex` runners. Claude Code variants (using the `claude` CLI directly) live in `config/claude_code_models.json` and use a separate runner:

```bash
# All variants not marked skip_by_default
python scripts/run_claude_code_benchmark.py

# Just Sonnet alone
python scripts/run_claude_code_benchmark.py --variant claude_sonnet_alone

# Two variants in parallel
python scripts/run_claude_code_benchmark.py \
    --variant claude_sonnet_alone \
    --variant kimi_k2_6_ollama_cloud \
    --jobs 2
```

`--jobs/-j N` runs up to N variants concurrently in a thread pool (default `1` = sequential). Use `--jobs 0` to fan out to one worker per selected variant. Each variant writes to its own result dir and spawns its `claude` subprocess in a new session group, so concurrent runs don't share state. Live log lines are prefixed with `[<slug>]` so the streams stay distinguishable.

Output lands in `results-claude-code/<slug>/`:

- `project/` — generated Django app
- `result.json` — status, elapsed, turns, tokens, cost, tool-use counts
- `stream.ndjson` — raw `claude -p --output-format stream-json` events
- `stderr.log` — stderr from the claude (or `ollama launch claude`) subprocess
- `prompt.txt` — exact prompt sent

The aggregate report is rebuilt from every `result.json` on disk (even cached ones not in the current run) and written to `docs/report.claude-code.md`. Requires the `claude` CLI on `$PATH`.

**Auth.** Claude subscription auth (the credentials saved by `claude login`) works out of the box — `runner.isolate_home` in `config/claude_code_models.json` defaults to `false` so the `claude` CLI can read its credentials from your real `~/.claude/`. If you're on API-key auth instead and want strict user-level agent isolation, set `runner.isolate_home: true` in the config and export `ANTHROPIC_API_KEY` — the runner replaces `$HOME` with the per-variant result dir for the duration of the run. (Subscription auth fails under isolation because the credentials file is unreachable.)

**Ollama-served models via Claude Code.** Each variant can declare a `command_prefix` that replaces the leading `["claude"]`. The shipped config wires three Ollama Cloud models through your `ollama launch claude` shim:

| Slug | Ollama tag | Notes |
|---|---|---|
| `kimi_k2_6_ollama_cloud` | `kimi-k2.6:cloud` | Recommended — SOTA coding, long-horizon execution, agent swarm |
| `glm_5_1_ollama_cloud` | `glm-5.1:cloud` | Long-horizon agentic engineering |
| `qwen3_5_ollama_cloud` | `qwen3.5:cloud` | Reasoning, coding, agentic tool use, vision |

For each, the runner builds (e.g.):

```text
ollama launch claude --model kimi-k2.6:cloud -- -p --output-format stream-json --dangerously-skip-permissions --verbose <prompt>
```

`ollama launch claude` consumes its own `--model` flag and forwards everything after `--` to the `claude` CLI, so the model is routed through the shim and the remaining claude args (no `--model` on that side, since the shim configures it) come after the `--` separator. The runner detects the `ollama launch` prefix automatically; the default `["claude"]` path passes `--model` directly to claude.

To run just one:

```bash
python scripts/run_claude_code_benchmark.py --variant kimi_k2_6_ollama_cloud
```

To add another Ollama-served model, append a new variant with the right `main_model` (Ollama tag) and `command_prefix: ["ollama","launch","claude"]`.

Per-model output lands in `results/<slug>/`:

- `project/` — the generated workspace
- `result.json` — normalized metadata (status, elapsed, tokens, phases)
- `opencode-output.ndjson` / `opencode-stderr.log` — raw phase 1 output
- `followup-*` — phase 2 continuation output (when `enable_followup` is true)
- `session-export.json` — opencode session snapshot (when available)

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

Per-project artifacts: `results/<slug>/project/_runtime_verification/`. Aggregate summary: `results/runtime_verification_summary.json`.

Useful flags:

```bash
# One model only
python scripts/analyze_results_runtime.py --only claude_sonnet_4_6

# Cap projects (handy for sanity checks)
python scripts/analyze_results_runtime.py --max-projects 1

# Bump install timeout for slow links
python scripts/analyze_results_runtime.py --install-timeout 1800
```

## Result tiers (interpretation)

When you read the per-model output, classify the LLM integration code by hand:

- **Tier 1** — correct LangChain + Channels wiring + proper test mocking. Boots locally, Docker compose works, browser probe sees a streamed reply.
- **Tier 2** — correct primary call but partial issues (multi-turn broken, wrong package, Dockerfile bugs, `LLMChain` deprecation warnings, broken WebSocket routing).
- **Tier 3** — hallucinated API. `from langchain.chat_models import ChatAnthropic` (not where it lives anymore), fabricated streaming callbacks, `consumer.send_to_group()` with the wrong signature. Crashes on first call.

Auto-generated `docs/report.md` only shows the harness-level signal (status + tokens + tests-passing claims). The Tier classification has to come from reading the LLM-integration code by hand.

## Adding a new model

1. Edit `config/models.json` — append a `models[]` entry. Use a unique `slug`. The `id` must match a model exposed by the providers in your home opencode config (e.g. `openrouter/anthropic/claude-sonnet-4.6`).
2. If the model is on a provider you haven't wired into your home opencode config yet, add it there first — see the opencode docs.
3. Run: `python scripts/run_benchmark.py --model <new-slug>`.
4. Run: `python scripts/analyze_results_runtime.py --only <new-slug>`.
5. Read the LLM-integration code by hand to decide Tier 1/2/3.

You can also use the automated audit runner instead of manual reading:

```bash
# Run the default auditor (Claude Opus 4.7) against the new model's output
python scripts/run_audit_benchmark.py --variant <new-slug>
```

## Secrets handling

- The brief sources `~/.config/zsh/secrets` for `OPENROUTER_API_KEY`.
- The runtime analyzer does the same when launching the local server and Docker compose, so the generated apps can talk to OpenRouter during the browser probe.
- **Never commit, echo, or log the API key.** If you suspect a secret leaked into a log or generated file, rotate it immediately.

## Known harness pitfalls (inherited from the parent project)

- Stale `run_benchmark.py` or `opencode` processes can hold the opencode SQLite DB lock at `~/.local/share/opencode/opencode.db`. The runner auto-kills stale opencode processes before each model run, but if a benchmark hangs silently it's the first thing to check.
- The opencode benchmark config at `config/opencode.benchmark.json` is auto-rewritten on every run from `~/.config/opencode/opencode.json`. Don't edit it by hand.
- DeepSeek V4 Pro multi-turn is broken on opencode (the ai-sdk strips `reasoning_content` but DeepSeek requires it echoed back). The default config already disables follow-up for it; the runtime analyzer fills in the validation gap.
