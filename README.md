# LLM Python Coding Benchmark

Benchmark harness for autonomous coding agents building the same Python app: a
Django + Channels chat SPA that streams responses from a local Ollama model.

The benchmark records how each agent/harness performs, then supports automated
runtime verification and LLM-based audit passes over the generated projects.

## What agents build

Each model receives `prompts/benchmark_prompt.txt` and is asked to build:

- Django + Django Channels with an ASGI WebSocket consumer.
- A real local Ollama integration using `OLLAMA_HOST` and `OLLAMA_MODEL`.
- HTMX + WebSocket extension or small vanilla JavaScript for streaming UI.
- Tailwind styling.
- pytest, ruff, mypy, bandit, coverage.py, and pip-audit setup.
- Dockerfile + Docker Compose running Daphne or Uvicorn.

The follow-up prompt in `prompts/benchmark_followup_prompt.txt` asks the agent
to boot the app and validate Docker when that phase is enabled for the model.

## Project layout

```text
python-benchmark/
├── README.md
├── CONTEXT.md
├── AGENTS.md
├── CLAUDE.md
├── config/
│   ├── harnesses.json
│   └── models.json
├── prompts/
│   ├── benchmark_prompt.txt
│   ├── benchmark_followup_prompt.txt
│   ├── audit_prompt_template.txt
│   └── audit_meta_analysis_prompt.txt
├── scripts/
│   ├── run_benchmark.py
│   ├── run_full_benchmark.py
│   ├── run_audit.py
│   ├── run_meta_analysis.py
│   ├── validate_results.py
│   ├── analyze_results_runtime.py
│   ├── browser_probe.mjs
│   └── benchmark/
├── scripts/tests/
├── docs/
│   ├── configuration.md
│   ├── workflows.md
│   ├── outputs.md
│   └── troubleshooting.md
├── results/
└── audit-reports/
```

`results/` and `audit-reports/` are runtime output locations. Treat generated
projects under `results/<harness>-<slug>/project/` as untrusted code.

## Prerequisites

- Python 3.10+ available as `python3`.
- `pytest` for the harness regression suite.
- Docker + Docker Compose for runtime verification.
- Node for `scripts/browser_probe.mjs`.
- Ollama reachable through `OLLAMA_HOST` for runtime verification.
- One or more agent CLIs on `PATH`: `opencode`, `codex`, `claude`, or `agent`
  for Cursor CLI.
- Required auth for the selected harness/provider, such as `OPENROUTER_API_KEY`
  for OpenRouter-backed opencode runs or CLI login for subscription-backed
  Codex, Claude, and Cursor runs.

Do not commit API keys, generated home config, or benchmark credentials.

## Quickstart

Run one benchmark model:

```bash
python3 scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6
```

Check whether a benchmark run finished cleanly (harness status + project scaffold):

```bash
python3 scripts/validate_results.py --only opencode-claude_sonnet_4_6
python3 scripts/validate_results.py --remove-on-fail
```

`run_benchmark.py` runs the same checks after each model and retries from scratch
up to three times on failure (see `--max-validation-retries` / `--no-result-validation`).

Validate generated projects boot locally and in Docker:

```bash
python3 scripts/analyze_results_runtime.py --only opencode-claude_sonnet_4_6
```

Run one audit pass:

```bash
python3 scripts/run_audit.py \
  --harness claude \
  --model claude_opus_4_7 \
  --target opencode-claude_sonnet_4_6
```

Run harness tests:

```bash
pytest scripts/tests
```

## Core commands

```bash
# Benchmark by harness. Model rows come from config/models.json.
python3 scripts/run_benchmark.py --harness opencode
python3 scripts/run_benchmark.py --harness codex
python3 scripts/run_benchmark.py --harness claude
python3 scripts/run_benchmark.py --harness cursor

# Select models. Repeat --model for more than one slug.
python3 scripts/run_benchmark.py --harness codex --model codex_gpt_5_5

# Use a non-default model registry.
python3 scripts/run_benchmark.py --harness codex --models-config config/models.json

# Force a rerun even when result.json has a terminal status.
python3 scripts/run_benchmark.py --harness opencode --model kimi_k2_6_ollama_cloud --force

# Full build + audit + meta-analysis pipeline.
python3 scripts/run_full_benchmark.py --list-steps
python3 scripts/run_full_benchmark.py -- --force
```

See `docs/workflows.md` for the benchmark, audit, meta-analysis, and runtime
verification flows.

## Configuration

The active source of truth is:

- `config/models.json`: shared model registry.
- `config/harnesses.json`: harness command metadata.

Routing is derived from each model's `provider` and selected `--harness`. For
example, `provider: "openai"` runs on Codex, `provider: "anthropic"` runs on
Claude, `provider: "cursor"` runs on Cursor, and `provider: "ollama_cloud"` can
run through Claude, Codex, or opencode with `ollama launch` routing.

See `docs/configuration.md` for field-level details.

## Outputs

- `results/<harness>-<slug>/`: generated project, logs, prompts, and result
  metadata for one benchmark run.
- `audit-reports/<auditor>/<target>/`: one audit report and audit metadata.
- `results/runtime_verification_summary.json`: runtime verification summary.

See `docs/outputs.md` for artifact ownership and cleanup guidance.

## Result tiers

Use audit reports and runtime verification to classify generated projects:

- Tier 1: correct Ollama + Channels wiring, tests, local boot, Docker boot, and
  browser probe success.
- Tier 2: mostly correct primary path with integration, Docker, test, or routing
  defects.
- Tier 3: hallucinated or non-working primary integration.

Tier classification requires reading generated code or running the audit workflow.

## Safety

Generated projects may contain unsafe commands, dependency choices, or broken
configuration. Prefer `scripts/analyze_results_runtime.py` over ad hoc manual
execution. Do not run generated migrations, shell scripts, or installers against
shared services.

Secrets must stay in environment variables, CLI auth stores, or ignored local
files. If a secret appears in logs or generated files, rotate it.

## Troubleshooting

See `docs/troubleshooting.md` for common issues: missing `python`, missing CLIs,
agent auth, Docker/Ollama failures, stale opencode locks, and slow runs.
