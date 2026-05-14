# CONTEXT.md — Harness domain glossary

Canonical vocabulary used by maintainers and agents in this repository.

---

## harness

One of three execution backends: `opencode`, `codex`, or `claude`. Selected with `--harness` on `run_benchmark.py`. Governs which CLI is shelled out to (`opencode run`, `codex exec`, or `claude -p`), how output events are streamed (opencode/codex NDJSON vs Claude `stream-json`), and which config file and runner module are loaded.

## model

A single LLM entry in `config/models.json` (opencode/codex registry). Required fields: `slug`, `id`, `label`, `provider`, `selection_reason`. Optional: `runner_type` (`opencode` default | `codex`), `command_prefix`, `enable_followup`, `skip_by_default`, `opencode_model_options`. The `slug` is the canonical identifier used in result directory names (`<harness>-<slug>`).

## variant

A Claude Code execution profile in `config/claude_code_models.json`. Same concept as a model but richer: `slug`, `label`, `main_model`, optional `subagent`, `command_prefix`, `env_overrides`, `isolate_home`. Selected with `--variant` on the `claude` harness. The slug is used in result directory names (`claude-<slug>`).

## target

The generated project produced by one (harness, model/variant) run. Lives at `results/<harness>-<slug>/project/`. This is the artefact under evaluation — the Django + Channels + Ollama chat SPA the coding agent wrote. Referenced by its parent directory name (e.g. `claude-claude_sonnet_4_6`) when selecting audit runs.

## auditor

A model entry from `config/audit_models.json` used in the Role 1 audit pass (`run_audit.py`). Same schema as a variant. An auditor reads a target's `project/` directory, applies the rubric from `prompts/audit_prompt_template.txt`, and writes `audit-reports/<auditor_slug>/<target_slug>/report.md`.

## result directory

`results/<harness>-<slug>/` — the per-run output directory. Contains: `project/` (the target), `result.json` (metadata: status, cost, tokens, elapsed), and harness-specific logs (`stream.ndjson` + `stderr.log` for Claude; `opencode-output.ndjson` + `opencode-stderr.log` for opencode/codex). May also include `session-export.json` (opencode) and `prompt.txt` (Claude).

## project workspace

The `project/` subdirectory inside a result directory. This is the working directory given to the coding agent — all generated source files must land here. Workspace escape detection alerts when an agent writes files outside this boundary (see `loop_detector.py` and the escape detector in `runner.py`).

## audit report

`audit-reports/<auditor_slug>/<target_slug>/report.md` — the LLM-scored rubric written by one auditor against one target. Covers 8 dimensions (Ollama wiring, Channels scaffolding, Docker, tests, etc.) and assigns a Tier 1/2/3 classification. Companion files in the same directory: `result.json`, `stream.ndjson`, `stderr.log`.

## run status

The `status` field in `result.json`. One of: `completed`, `completed_with_errors`, `failed`, `timeout`, `not_run`. Propagated into aggregate report tables.

## slug

The short, unique identifier for a model or variant. Used as a filesystem-safe key in result directory names, audit-report paths, CLI flags (`--model`, `--variant`, `--auditor`, `--target`), and report rows. Defined in the relevant config JSON; must be unique within a registry.

## phase

One of two sequential prompt turns sent to the coding agent. Phase 1 (`prompts/benchmark_prompt.txt`) is the full implementation brief. Phase 2 (`prompts/benchmark_followup_prompt.txt`) instructs the agent to boot the app, run `docker build`, and `docker compose up`. Phase 2 can be disabled per model via `enable_followup: false`.

## runtime verification

Post-run validation performed by `scripts/analyze_results_runtime.py`. Discovers the Django app root, installs deps in a venv, runs migrations, boots the dev server, executes a headless Chromium browser probe, and repeats the probe against a Docker Compose stack. Artifacts land in `results/<harness>-<slug>/project/_runtime_verification/`.

## meta-analysis

Role 2 output produced by `scripts/run_meta_analysis.py`. Reads every `audit-reports/<auditor>/<target>/report.md` and writes `audit-reports/meta-analysis.md` with cross-auditor verdicts: best harness, best model, cost, and per-dimension winners.
