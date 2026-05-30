# CONTEXT.md — Harness domain glossary

Canonical vocabulary used by maintainers and agents in this repository.

---

## harness

One execution backend declared in `config/harnesses.json`: `opencode`, `codex`, `claude`, or `cursor`. Selected with `--harness` on `run_benchmark.py`, `run_audit.py`, and `run_meta_analysis.py`. Governs which CLI is shelled out to (`opencode run`, `codex exec`, `claude -p`, or `agent -p`) and how output events are streamed.

## model

A single LLM identity in `config/models.json`. Required fields: `slug`, `label`, `provider`, and `selection_reason`. Harness-specific runnable IDs, command prefixes, and runner options live in `config/harnesses.json`. Selected with `--model`. The `slug` is the canonical identifier used in result directory names (`<harness>-<slug>`) and audit report paths.

## run_id

Explicit campaign directory name under `results/` (e.g. `run_02`). Required on all full-pipeline commands via `--run-id`. Resolved by `RunLayout` in `scripts/benchmark/result_layout.py` into `projects/`, `audit-reports/`, and `meta-analysis.md` paths.

## RunLayout

Central path helper for run-scoped output. Given `run_id`, yields `results/<run_id>/projects/`, `results/<run_id>/audit-reports/`, and `results/<run_id>/meta-analysis.md`.

## target

The generated project produced by one `(harness, model)` run. Lives at `results/<run_id>/projects/<harness>-<slug>/project/`. This is the artefact under evaluation — the Django + Channels + Ollama chat SPA the coding agent wrote. Referenced by its parent directory name (e.g. `claude-claude_sonnet_4_6`) when selecting audit runs.

## auditor

A model selected for the Role 1 audit pass (`run_audit.py`). An auditor reads a target's `project/` directory, applies the rubric from `prompts/audit_prompt_template.txt`, and writes `results/<run_id>/audit-reports/<auditor_slug>/<target_slug>/report.md`.

## result directory

`results/<run_id>/projects/<harness>-<slug>/` — the per-target output directory. Contains: `project/` (the target), `result.json` (metadata: status, tokens, elapsed — **not** USD cost), and harness-specific logs (`stream.ndjson` + `stderr.log` for Claude; `opencode-output.ndjson` + `opencode-stderr.log` for opencode/codex). May also include `session-export.json` (opencode) and `prompt.txt` (Claude).

## pricing

Repo-owned snapshot at `docs/PRICING.md`. Generation cost is computed in Python during audit dispatch (`scripts/run_audit.py`) and written to `results/<run_id>/audit-reports/<auditor>/<target>/generation-metrics.json`; section H of `report.md` copies those values verbatim.

## project workspace

The `project/` subdirectory inside a result directory. This is the working directory given to the coding agent — all generated source files must land here. Workspace escape detection alerts when an agent writes files outside this boundary (see `scripts/benchmark/stream_state.py` and the escape detector in `scripts/benchmark/runner.py`).

## audit report

`results/<run_id>/audit-reports/<auditor_slug>/<target_slug>/report.md` — the LLM-scored rubric written by one auditor against one target. Covers ten dimensions (Ollama wiring, Channels scaffolding, Docker, tests, code quality, etc.) and assigns a practical tier. Companion files in the same directory: `result.json`, `generation-metrics.json`, `stream.ndjson`, `stderr.log`.

## run status

The `status` field in `result.json`. One of: `completed`, `completed_with_errors`, `failed`, `timeout`, `not_run`. Propagated into aggregate report tables.

## slug

The short, unique identifier for a model. Used as a filesystem-safe key in result directory names, audit-report paths, CLI flags (`--model`, `--target`), and report rows. Defined once in `config/models.json`.

## phase

One of two sequential prompt turns sent to the coding agent. Phase 1 (`prompts/benchmark_prompt.txt`) is the full implementation brief. Phase 2 (`prompts/benchmark_followup_prompt.txt`) instructs the agent to boot the app, run `docker build`, and `docker compose up`. Every model run executes both phases when phase 1 completes without timeout, stall, or usage-limit failure.

## runtime verification

Post-run validation performed by `scripts/analyze_results_runtime.py`. Discovers the Django app root, installs deps in a venv, runs migrations, boots the dev server, executes a headless Chromium browser probe, and repeats the probe against a Docker Compose stack. Artifacts land in `results/<run_id>/projects/<harness>-<slug>/project/_runtime_verification/`.

## meta-analysis

Role 2 output produced by `scripts/run_meta_analysis.py`. Reads every audit `report.md` and writes `results/<run_id>/meta-analysis.md` with cross-run verdicts: best harness, best model, cost, and per-dimension winners. The stable entry point is `results/latest/meta-analysis.md` (symlink to the current run directory).

## campaign

A published benchmark round indexed under `data/campaigns/<id>/manifest.json`. Documents prompt versions, auditor slug, target list, and paths to published audit/benchmark artifacts. `data/campaigns/latest` symlinks to the current campaign.

## published data

Curated subset of `results/<run_id>/` tracked in git after `scripts/publish_campaign.py` strips ephemeral artifacts (venv, stream logs, tool caches) and updates `.gitignore` allowlists. See `docs/published-data.md`.
