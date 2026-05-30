# Running the benchmark

Operational guide for benchmark generation, validation, audit, meta-analysis, and
runtime verification. For assessment design see [`methodology.md`](methodology.md).

## Prerequisites

- Python 3.10+ as `python3`
- `pytest` for the harness regression suite
- Docker + Docker Compose for runtime verification
- Node for `scripts/browser_probe.mjs`
- Ollama reachable via `OLLAMA_HOST` for runtime verification
- One or more agent CLIs on `PATH`: `opencode`, `codex`, `claude`, or `agent` (Cursor)
- Auth for the selected harness/provider (`OPENROUTER_API_KEY`, CLI login, etc.)

Do not commit API keys, generated home config, or benchmark credentials.

## Quickstart

Run one benchmark model:

```bash
python3 scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6
```

Validate a finished run (harness status + project scaffold):

```bash
python3 scripts/validate_results.py --only opencode-claude_sonnet_4_6
python3 scripts/validate_results.py --remove-on-fail
```

`run_benchmark.py` runs the same checks after each model and retries from scratch up to three times on failure (see `--max-validation-retries` / `--no-result-validation`).

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

## Benchmark commands

```bash
# Full harness matrix (models from config/models.json)
python3 scripts/run_benchmark.py --harness opencode
python3 scripts/run_benchmark.py --harness codex
python3 scripts/run_benchmark.py --harness claude
python3 scripts/run_benchmark.py --harness cursor

# Single model
python3 scripts/run_benchmark.py --harness codex --model codex_gpt_5_5

# Non-default registry
python3 scripts/run_benchmark.py --harness codex --models-config config/models.json

# Force rerun
python3 scripts/run_benchmark.py --harness opencode --model kimi_k2_6_ollama_cloud --force
```

Useful flags:

- `--model <slug>` — repeat for multiple models
- `--results-dir <path>` — change output root
- `--force` — rerun even when `result.json` has a terminal status
- `--jobs N` — concurrent model runs (default 2; local GPU models share one lock)
- `--max-validation-retries N` — wipe and retry on validation failure (default 3)
- `--no-result-validation` — skip post-run validation

## Result validation

```bash
python3 scripts/validate_results.py
python3 scripts/validate_results.py --only opencode-qwen3_5_ollama_cloud
python3 scripts/validate_results.py --remove-on-fail
```

## Full pipeline

Build matrix, audit, and meta-analysis in one flow:

```bash
python3 scripts/run_full_benchmark.py --list-steps
python3 scripts/run_full_benchmark.py -- --force
```

Flags: `--dry-run`, `--skip-build`, `--skip-audit`, `--skip-meta`

Environment variables:

- `AUDITOR_SLUG` — Role 1 auditor (default `codex_gpt_5_5`)
- `META_ANALYSIS_AUDITOR_SLUG` — Role 2 model (default same as auditor)
- `META_ANALYSIS_HARNESS` — Role 2 dispatch harness
- `META_ANALYSIS_INPUT_DIR` — audit input directory for Role 2

## Audit (Role 1)

```bash
# Defaults: --harness codex --model codex_gpt_5_5
python3 scripts/run_audit.py --target opencode-claude_sonnet_4_6

python3 scripts/run_audit.py \
  --harness claude \
  --model claude_opus_4_7 \
  --target opencode-claude_sonnet_4_6
```

Flags: `--target` (repeatable), `--benchmark-results-dir`, `--results-dir`, `--report-only`, `--jobs N`

## Meta-analysis (Role 2)

```bash
python3 scripts/run_meta_analysis.py --meta-input-dir codex_gpt_5_5

python3 scripts/run_meta_analysis.py --harness claude --model claude_opus_4_7
```

Flags: `--meta-input-dir`, `--meta-output-dir`, `--force`, `--strict-meta-validation`

## Runtime verification

```bash
python3 scripts/analyze_results_runtime.py
python3 scripts/analyze_results_runtime.py --only opencode-claude_sonnet_4_6
python3 scripts/analyze_results_runtime.py --max-projects 1
```

## Publish a campaign to git

After benchmark, audit, and meta-analysis complete:

```bash
python3 scripts/publish_campaign.py \
  --campaign-id 2026-05-ollama-cloud-v3.2 \
  --label "Ollama Cloud grid — benchmark v3.2" \
  --auditor codex_gpt_5_5 \
  --auto-discover-targets \
  --campaign-date 2026-05-29
```

See [`published-data.md`](published-data.md) for artifact rules.

## Pricing validation

```bash
python3 scripts/validate_pricing.py
python3 scripts/fetch_openrouter_pricing.py --check
```

## Troubleshooting

See [`troubleshooting.md`](troubleshooting.md) for missing CLIs, auth, Docker/Ollama failures, stale locks, and slow runs.
