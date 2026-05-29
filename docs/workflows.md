# Workflows

## Benchmark

`scripts/run_benchmark.py` is the main entrypoint. It sends
`prompts/benchmark_prompt.txt` to the selected harness and writes one result
directory per model under `results/`.

```bash
python3 scripts/run_benchmark.py --harness opencode
python3 scripts/run_benchmark.py --harness codex
python3 scripts/run_benchmark.py --harness claude
python3 scripts/run_benchmark.py --harness cursor
```

Useful flags:

- `--model <slug>`: select one model. Repeat for multiple models.
- `--models-config <path>`: use a non-default model registry.
- `--results-dir <path>`: change the benchmark output root.
- `--force`: rerun even when a terminal `result.json` exists.
- `--jobs N`: max concurrent model runs (default: 2; use `--jobs 1` for sequential).
- `--max-validation-retries N`: after each model run, validate `result.json` and the
  generated `project/` scaffold; on failure wipe `results/<harness>-<slug>/` and
  rerun from scratch (default: 3 retries, 4 attempts total). Use
  `--no-result-validation` to disable.

## Result validation

`scripts/validate_results.py` checks existing benchmark outputs without re-running
agents:

```bash
python3 scripts/validate_results.py
python3 scripts/validate_results.py --only opencode-qwen3_5_ollama_cloud
python3 scripts/validate_results.py --remove-on-fail
```

The same rules run automatically at the end of each `run_benchmark.py` model
invocation unless `--no-result-validation` is set.

Local GPU models (`provider: "ollama"`) share one lock so only one loads at a
time; other models can still run in parallel up to `--jobs`.

## Full Pipeline

`scripts/run_full_benchmark.py` runs the build matrix, then audit, then
meta-analysis.

```bash
python3 scripts/run_full_benchmark.py --list-steps
python3 scripts/run_full_benchmark.py -- --force
```

Useful flags:

- `--dry-run`: print subprocess commands without launching agents.
- `--skip-build`: skip benchmark generation.
- `--skip-audit`: skip Role 1 audits.
- `--skip-meta`: skip Role 2 meta-analysis.

Useful environment variables:

- `AUDITOR_SLUG`: audit model slug for Role 1 (default: `codex_gpt_5_5`, GPT-5.5 xhigh via Codex).
- `META_ANALYSIS_AUDITOR_SLUG`: model slug for Role 2 (default: same as `AUDITOR_SLUG`).
- `META_ANALYSIS_HARNESS`: harness for Role 2 dispatch (default: derived from the meta model, `codex` for `codex_gpt_5_5`).
- `META_ANALYSIS_INPUT_DIR`: audit input directory for Role 2 (default: Role 1 auditor slug).

## Runtime Verification

`scripts/analyze_results_runtime.py` validates generated Django projects.

```bash
python3 scripts/analyze_results_runtime.py
python3 scripts/analyze_results_runtime.py --only opencode-claude_sonnet_4_6
python3 scripts/analyze_results_runtime.py --max-projects 1
python3 scripts/analyze_results_runtime.py --install-timeout 1800
```

Per project, the analyzer discovers `manage.py`, creates an isolated venv under
`_runtime_verification/`, installs dependencies, runs migrations, boots the dev
server, runs the browser probe, builds Docker, runs Docker Compose, repeats the
browser probe, and tears the Compose stack down.

The analyzer injects default `OLLAMA_HOST` and `OLLAMA_MODEL` values when they
are absent.

## Audit

`scripts/run_audit.py` dispatches one LLM auditor over generated projects and
writes rubric reports under `audit-reports/`.

```bash
# Defaults: --harness codex --model codex_gpt_5_5 (GPT-5.5 xhigh)
python3 scripts/run_audit.py --target opencode-claude_sonnet_4_6

python3 scripts/run_audit.py \
  --harness claude \
  --model claude_opus_4_7 \
  --target opencode-claude_sonnet_4_6
```

Useful flags:

- `--harness <slug>`: audit dispatch harness from `config/harnesses.json`.
- `--model <slug>`: one auditor model from `config/models.json`.
- `--target <name>`: target result directory or bare model slug. Repeatable.
- `--benchmark-results-dir <path>`: where benchmark outputs live.
- `--results-dir <path>`: where audit reports are written.
- `--skip-quality-probe`: skip local static-analysis probe.
- `--report-only`: rebuild comparison reports from existing audits.
- `--jobs N`: run audits concurrently.

## Meta-Analysis

`scripts/run_meta_analysis.py` reads audit reports and writes a cross-auditor
analysis.

```bash
# Defaults: --harness codex --model codex_gpt_5_5
python3 scripts/run_meta_analysis.py --meta-input-dir codex_gpt_5_5

python3 scripts/run_meta_analysis.py --harness claude --model claude_opus_4_7
```

Useful flags:

- `--meta-input-dir <path-or-name>`: audit report source. Repeatable.
- `--meta-output-dir <path>`: output directory for meta-analysis files.
- `--force`: rerun even when cached output exists.
