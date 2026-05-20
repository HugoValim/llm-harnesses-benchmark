# CONTEXT.md — Harness domain glossary

Canonical vocabulary used by maintainers and agents in this repository.

---

## harness

One execution backend declared in `config/harnesses.json`: `opencode`, `codex`, `claude`, or `cursor`. Selected with `--harness` on `run_benchmark.py`, `run_audit.py`, and `run_meta_analysis.py`. Governs which CLI is shelled out to (`opencode run`, `codex exec`, `claude -p`, or `agent -p`) and how output events are streamed.

## model

A single LLM identity in `config/models.json`. Required fields: `slug`, `label`, `provider`, and `selection_reason`. Harness-specific runnable IDs, command prefixes, and runner options live in `config/harnesses.json`. Selected with `--model`. The `slug` is the canonical identifier used in result directory names (`<harness>-<slug>`) and audit report paths.

## target

The generated project produced by one `(harness, model)` run. Lives at `results/<harness>-<slug>/project/`. This is the artefact under evaluation — the Django + Channels + Ollama chat SPA the coding agent wrote. Referenced by its parent directory name (e.g. `claude-claude_sonnet_4_6`) when selecting audit runs.

## auditor

A model selected for the Role 1 audit pass (`run_audit.py`). An auditor reads a target's `project/` directory, applies the rubric from `prompts/audit_prompt_template.txt`, and writes `audit-reports/<auditor_slug>/<target_slug>/report.md`.

## result directory

`results/<harness>-<slug>/` — the per-run output directory. Contains: `project/` (the target), `result.json` (metadata: status, cost, tokens, elapsed), and harness-specific logs (`stream.ndjson` + `stderr.log` for Claude; `opencode-output.ndjson` + `opencode-stderr.log` for opencode/codex). May also include `session-export.json` (opencode) and `prompt.txt` (Claude).

## project workspace

The `project/` subdirectory inside a result directory. This is the working directory given to the coding agent — all generated source files must land here. Workspace escape detection alerts when an agent writes files outside this boundary (see `loop_detector.py` and the escape detector in `runner.py`).

## audit report

`audit-reports/<auditor_slug>/<target_slug>/report.md` — the LLM-scored rubric written by one auditor against one target. Covers 8 dimensions (Ollama wiring, Channels scaffolding, Docker, tests, etc.) and assigns a Tier 1/2/3 classification. Companion files in the same directory: `result.json`, `stream.ndjson`, `stderr.log`.

## run status

The `status` field in `result.json`. One of: `completed`, `completed_with_errors`, `failed`, `timeout`, `not_run`. Propagated into aggregate report tables.

## slug

The short, unique identifier for a model. Used as a filesystem-safe key in result directory names, audit-report paths, CLI flags (`--model`, `--target`), and report rows. Defined once in `config/models.json`.

## phase

One of two sequential prompt turns sent to the coding agent. Phase 1 (`prompts/benchmark_prompt.txt`) is the full implementation brief. Phase 2 (`prompts/benchmark_followup_prompt.txt`) instructs the agent to boot the app, run `docker build`, and `docker compose up`. Phase 2 can be disabled per model via `enable_followup: false`.

## runtime verification

Post-run validation performed by `scripts/analyze_results_runtime.py`. Discovers the Django app root, installs deps in a venv, runs migrations, boots the dev server, executes a headless Chromium browser probe, and repeats the probe against a Docker Compose stack. Artifacts land in `results/<harness>-<slug>/project/_runtime_verification/`.

## meta-analysis

Role 2 output produced by `scripts/run_meta_analysis.py`. Reads every `audit-reports/<auditor>/<target>/report.md` and writes `audit-reports/meta-analysis.md` with cross-auditor verdicts: best harness, best model, cost, and per-dimension winners.
