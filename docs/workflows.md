# Workflows

Command reference: [`running.md`](running.md). Assessment design: [`methodology.md`](methodology.md).

## Benchmark → audit → meta-analysis

The standard end-to-end flow (shared `--run-id run_XX` on every step):

1. **Generate** — `run_benchmark.py` sends the implementation brief to each `(harness, model)` pair and writes `results/<run_id>/projects/<harness>-<slug>/`.
2. **Validate** — `validate_results.py` (or automatic post-run checks) confirm `result.json` status and project scaffold.
3. **Audit** — `run_audit.py` dispatches Role 1 rubric scoring to `results/<run_id>/audit-reports/<auditor>/<target>/report.md`.
4. **Meta-analyze** — `run_meta_analysis.py` reads all reports and writes `results/<run_id>/meta-analysis.md`.
5. **Publish** — `publish_campaign.py` strips ephemeral artifacts and updates git allowlists (see [`published-data.md`](published-data.md)).

`run_full_benchmark.py --run-id run_XX` chains steps 1, 3, and 4 with skip flags for partial reruns.

## Build concurrency (Phase 1)

By default, `run_full_benchmark.py` keeps up to `-j` build subprocesses running across **all harnesses** (global pool), scheduled in replicate waves so different models run the same replicate index together and the same `(harness, model)` never overlaps. Pass `--sequential-build` to run harness batches one after another instead.

## Runtime verification

`analyze_results_runtime.py` is a **supplementary** operational check (boot, browser probe, Docker). It does not replace the audit rubric. See [`running.md`](running.md#runtime-verification).

## Local GPU concurrency

Local GPU models (`provider: "ollama"`) share one lock so only one loads at a time. Other models can still run in parallel up to `--jobs`.

## Full pipeline shortcut

Use `run_full_benchmark.py --run-id run_XX` for the build + audit + meta-analysis chain. See [`running.md`](running.md#full-pipeline).
