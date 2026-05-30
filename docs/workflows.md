# Workflows

Command reference: [`running.md`](running.md). Assessment design: [`methodology.md`](methodology.md).

## Benchmark → audit → meta-analysis

The standard end-to-end flow:

1. **Generate** — `run_benchmark.py` sends the implementation brief to each `(harness, model)` pair and writes `results/<harness>-<slug>/`.
2. **Validate** — `validate_results.py` (or automatic post-run checks) confirm `result.json` status and project scaffold.
3. **Audit** — `run_audit.py` dispatches Role 1 rubric scoring to `audit-reports/<auditor>/<target>/report.md`.
4. **Meta-analyze** — `run_meta_analysis.py` reads all reports and writes `audit-reports/<auditor>/meta-analysis.md`.
5. **Publish** — `publish_campaign.py` strips ephemeral artifacts and updates git allowlists (see [`published-data.md`](published-data.md)).

`run_full_benchmark.py` chains steps 1, 3, and 4 with skip flags for partial reruns.

## Runtime verification

`analyze_results_runtime.py` is a **supplementary** operational check (boot, browser probe, Docker). It does not replace the audit rubric. See [`running.md`](running.md#runtime-verification).

## Local GPU concurrency

Local GPU models (`provider: "ollama"`) share one lock so only one loads at a time. Other models can still run in parallel up to `--jobs`.

## Full pipeline shortcut

Use `run_full_benchmark.py` for the build + audit + meta-analysis chain. See [`running.md`](running.md#full-pipeline).
