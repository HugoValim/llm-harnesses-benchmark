# CONTEXT.md — Harness domain glossary

Canonical vocabulary used by maintainers and agents in this repository.

---

## harness

One execution backend declared in `config/harnesses.json`: `opencode`, `codex`, `claude`, or `cursor`. Selected with `--harness` on `run_benchmark.py`, `run_audit.py`, and `run_meta_analysis.py`. Governs which CLI is shelled out to (`opencode run`, `codex exec`, `claude -p`, or `agent -p`) and how output events are streamed.

## model

A single LLM identity in `config/models.json`. Required fields: `slug`, `label`, `provider`, `harness` (a list of registry harness values), and `selection_reason`. Optional `num_runs` (default `1`) controls how many replicate attempts the benchmark dispatches **per harness** in the list. Runner command metadata lives in `config/harnesses.json`. Selected with `--model`. The `slug` is the canonical identifier used in result directory names (`<harness>-<slug>`) and audit report paths.

## run_id

Explicit campaign directory name under `results/` (e.g. `run_02`). Required on all full-pipeline commands via `--run-id`. Resolved by `RunLayout` in `scripts/benchmark/result_layout.py` into `projects/`, `audit-reports/`, and `meta-analysis.md` paths. **Not** the same as replicate folder names (`run_01`, `run_02`, …) under each target group.

## replicate

One benchmark attempt for a `(harness, model)` pair. Replicate folders are named `run_01`, `run_02`, … (`run_{index:02d}`) under the target group directory. Count comes from `num_runs` on the model row in `config/models.json`. Even `num_runs: 1` uses nested `run_01/` (not a flat `project/` at the group root).

## RunLayout

Central path helper for run-scoped output. Given `run_id`, yields `results/<run_id>/projects/`, `results/<run_id>/audit-reports/`, and `results/<run_id>/meta-analysis.md`.

## target

The generated project produced by one `(harness, model, replicate)` run. Lives at `results/<run_id>/projects/<harness>-<slug>/run_XX/project/`. This is the artefact under evaluation — the Django + Channels + Ollama chat SPA the coding agent wrote. Audit and CLI filters use the projects-relative slug (e.g. `claude-kimi_k2_6/run_01` or the target group `claude-kimi_k2_6`).

## auditor

A model selected for the Role 1 audit pass (`run_audit.py`). An auditor reads a target's `project/` directory, applies the rubric from `prompts/audit_prompt_template.txt`, and writes `results/<run_id>/audit-reports/<auditor_slug>/<target_group>/run_XX/report.md` (nested replicate layout).

## result directory

`results/<run_id>/projects/<harness>-<slug>/run_XX/` — one replicate attempt. Contains: `project/` (the target), `result.json` (metadata: status, tokens, elapsed, `replicate_index`, `num_runs` — **not** USD cost), and harness-specific logs (`stream.ndjson` + `stderr.log` for Claude; `opencode-output.ndjson` + `opencode-stderr.log` for opencode/codex). May also include `session-export.json` (opencode) and `prompt.txt`. Legacy campaigns may still use a flat `project/` directly under the target group (no `run_XX/`).

## pricing

Repo-owned snapshot at `docs/PRICING.md`. Generation cost is computed in Python during audit dispatch (`scripts/run_audit.py`) and written to `results/<run_id>/audit-reports/<auditor>/<target>/generation-metrics.json`; section H of `report.md` copies those values verbatim.

## project workspace

The `project/` subdirectory inside a result directory. This is the working directory given to the coding agent — all generated source files must land here. Workspace escape detection alerts when an agent writes files outside this boundary (see `scripts/benchmark/stream_state.py` and the escape detector in `scripts/benchmark/runner.py`).

## audit report

`results/<run_id>/audit-reports/<auditor_slug>/<target_group>/run_XX/report.md` — the LLM-scored rubric written by one auditor against one replicate. Covers ten dimensions (Ollama wiring, Channels scaffolding, Docker, tests, code quality, etc.) and assigns a practical tier. Companion files in the same directory: `result.json`, `generation-metrics.json`, `stream.ndjson`, `stderr.log`. Meta-analysis aggregates scores across replicates per `(harness, model)`.

## run status

The `status` field in `result.json`. One of: `completed`, `completed_with_errors`, `failed`, `timeout`, `not_run`. Propagated into aggregate report tables.

## slug

The short, unique identifier for a model. Used as a filesystem-safe key in result directory names, audit-report paths, CLI flags (`--model`, `--target`), and report rows. Defined once in `config/models.json`.

## phase

One of two sequential prompt turns sent to the coding agent. Phase 1 (`prompts/benchmark_prompt.txt`) is the full implementation brief. Phase 2 (`prompts/benchmark_followup_prompt.txt`) instructs the agent to boot the app, run `docker build`, and `docker compose up`. Every model run executes both phases when phase 1 completes without timeout, stall, or usage-limit failure.

## runtime verification

Post-run validation performed by `scripts/analyze_results_runtime.py`. Discovers the Django app root, installs deps in a venv, runs migrations, boots the dev server, executes a headless Chromium browser probe, and repeats the probe against a Docker Compose stack. Artifacts land in `results/<run_id>/projects/<harness>-<slug>/run_XX/project/_runtime_verification/`.

## meta-analysis

Role 2 output produced by `scripts/run_meta_analysis.py`. Reads every audit `report.md` and writes `results/<run_id>/meta-analysis.md` with cross-run verdicts: best harness, best model, cost, and per-dimension winners. The stable GitHub entry point is `results/latest-meta-analysis.md` (copied on publish); `results/latest/` remains a local symlink to the current run directory.

## campaign

A published benchmark round indexed under `data/campaigns/<id>/manifest.json`. Documents prompt versions, auditor slug, target list, and paths to published audit/benchmark artifacts. `data/campaigns/latest` symlinks to the current campaign.

## published data

Curated subset of `results/<run_id>/` tracked in git after `scripts/publish_campaign.py` strips ephemeral artifacts (venv, stream logs, tool caches) and updates `.gitignore` allowlists. See `docs/published-data.md`.
