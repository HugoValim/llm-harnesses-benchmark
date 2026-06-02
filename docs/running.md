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

Pick a run directory first (`--run-id run_02`). All phases share the same id.

Run one benchmark model:

```bash
python3 scripts/run_benchmark.py --run-id run_02 --harness opencode --model claude_sonnet_4_6
```

Validate a finished run (replicate coverage, harness artifacts on disk, `result.json` semantics, and project scaffold):

```bash
python3 scripts/validate_results.py --run-id run_02 --only opencode-claude_sonnet_4_6
python3 scripts/validate_results.py --run-id run_02 --remove-on-fail
python3 scripts/validate_results.py --run-id run_02 --verbose  # full issue text per leaf
```

With a run-scoped layout, validation walks every configured replicate leaf (`num_runs` from `config/models.json`), not only directories that already have `result.json`. A leaf with `project/` but no `result.json` fails with `missing_result`; incomplete harness logs fail with `missing_*` artifact codes.

`run_benchmark.py` runs the same checks after each model and retries from scratch up to three times on failure (see `--max-validation-retries` / `--no-result-validation`). Only validation-passed completed runs are treated as cached skips on re-run (failed terminal rows are retried without `--force`).

Validate generated projects boot locally and in Docker:

```bash
python3 scripts/analyze_results_runtime.py --run-id run_02 --only opencode-claude_sonnet_4_6
```

Run one audit pass:

```bash
python3 scripts/run_audit.py \
  --run-id run_02 \
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
python3 scripts/run_benchmark.py --run-id run_02 --harness opencode
python3 scripts/run_benchmark.py --run-id run_02 --harness codex
python3 scripts/run_benchmark.py --run-id run_02 --harness claude
python3 scripts/run_benchmark.py --run-id run_02 --harness cursor

# Single model
python3 scripts/run_benchmark.py --run-id run_02 --harness codex --model codex_gpt_5_5

# Non-default registry
python3 scripts/run_benchmark.py --run-id run_02 --harness codex --models-config config/models.json

# Force rerun
python3 scripts/run_benchmark.py --run-id run_02 --harness opencode --model kimi_k2_6_ollama_cloud --force
```

Useful flags:

- `--run-id run_XX` — run directory under `results/` (required for full pipeline)
- `--model <slug>` — repeat for multiple models
- `--results-dir <path>` — legacy flat layout only (omit `--run-id`)
- `--force` — rerun even when `result.json` has a terminal status
- `--jobs N` — concurrent model runs (default 2; local GPU models share one lock)
- `--max-validation-retries N` — wipe and retry on validation failure (default 3)
- `--no-result-validation` — skip post-run validation

## Result validation

```bash
python3 scripts/validate_results.py --run-id run_02
python3 scripts/validate_results.py --run-id run_02 --only opencode-qwen3_5_ollama_cloud
python3 scripts/validate_results.py --run-id run_02 --remove-on-fail
```

## Full pipeline

Build matrix, audit, and meta-analysis in one flow:

```bash
python3 scripts/run_full_benchmark.py --run-id run_02 --list-steps
python3 scripts/run_full_benchmark.py --run-id run_02 -- --force
```

Flags: `--dry-run`, `--skip-build`, `--skip-audit`, `--skip-meta`, `--sequential-build`

Phase 1 (default) runs a **global job pool** with **per-target pipelined replicates**: up to `-j` concurrent subprocesses (default 3) run across all `(harness, model)` targets. Each target runs replicates one at a time — `run_02` starts when **that** target's `run_01` completes — but different targets share the pool, so workers stay busy when one target is still on an earlier replicate. At most one in-flight job per `(harness, model)`. Workers may drop below `-j` only when fewer than `-j` runnable jobs remain globally or a target fails. Docker prune runs once after all build jobs finish. Use `--sequential-build` to restore the legacy behavior (one harness batch at a time, `-j` per batch).

Parallel opencode runs share `~/.local/share/opencode`; the harness kills stale opencode processes before each batch to reduce SQLite lock contention.

**Build parity (all four harnesses):** Phase 2 always runs cold — no opencode session resume, no Cursor `--continue`. The harness wraps the primary prompt with canonical agent rules before sending it to the CLI. Each harness uses your normal CLI home config (`~/.codex`, `~/.claude`, `~/.config/cursor`, opencode data dir). `result.json` records `build_parity` metadata (`runtime_isolation` is always `{}`). Existing pre-parity runs that materialized `.codex-home`, `.xdg-data`, or `.agent-home` under replicates are not comparable — re-run build jobs before cross-harness audit comparisons.

Environment variables:

- `AUDITOR_SLUG` — Role 1 auditor (default `codex_gpt_5_5`)
- `META_ANALYSIS_AUDITOR_SLUG` — Role 2 model (default same as auditor)
- `META_ANALYSIS_HARNESS` — Role 2 dispatch harness
- `META_ANALYSIS_INPUT_DIR` — audit input directory for Role 2

## Audit (Role 1)

```bash
# Defaults: --harness codex --model codex_gpt_5_5
python3 scripts/run_audit.py --run-id run_02 --target opencode-claude_sonnet_4_6

python3 scripts/run_audit.py \
  --run-id run_02 \
  --harness claude \
  --model claude_opus_4_7 \
  --target opencode-claude_sonnet_4_6
```

Flags: `--run-id`, `--target` (repeatable), `--benchmark-results-dir`, `--results-dir`, `--report-only`, `--jobs N`

## Meta-analysis (Role 2)

```bash
python3 scripts/run_meta_analysis.py --run-id run_02 --meta-input-dir codex_gpt_5_5

python3 scripts/run_meta_analysis.py --run-id run_02 --harness claude --model claude_opus_4_7
```

Flags: `--run-id`, `--meta-input-dir`, `--meta-output-dir`, `--force`, `--strict-meta-validation`

## Runtime verification

```bash
python3 scripts/analyze_results_runtime.py --run-id run_02
python3 scripts/analyze_results_runtime.py --run-id run_02 --only opencode-claude_sonnet_4_6
python3 scripts/analyze_results_runtime.py --run-id run_02 --max-projects 1
```

## Publish a campaign to git

After benchmark, audit, and meta-analysis complete:

```bash
python3 scripts/publish_campaign.py \
  --run-id run_02 \
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
