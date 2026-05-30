# Outputs

Runtime paths used during benchmark runs. For git-published campaign artifacts see
[`published-data.md`](published-data.md).

## Run-scoped layout (current)

Every campaign uses an explicit run directory (`--run-id run_XX`):

```text
results/
└── run_XX/
    ├── meta-analysis.md
    ├── runtime_verification_summary.json
    ├── ollama_warmup.json
    ├── audit-reports/
    │   └── <auditor_slug>/
    │       ├── comparison.md
    │       ├── _meta-analysis-runs/
    │       └── <harness>-<slug>/
    │           ├── report.md
    │           ├── generation-metrics.json
    │           └── result.json
    └── projects/
        └── <harness>-<slug>/
            ├── project/
            ├── result.json
            └── stream logs
```

Stable README links use [`results/latest`](../../results/latest) (symlink retargeted on publish).

## Benchmark results (`projects/`)

Each benchmark run writes to:

```text
results/<run_id>/projects/<harness>-<slug>/
```

Common files:

- `project/` — generated Django project (untrusted code)
- `result.json` — status, timing, tokens (no USD cost)
- `prompt.txt` — prompt copy when recorded
- `stream.ndjson` / `opencode-output.ndjson` — agent stream events
- `stderr.log` / `opencode-stderr.log` — captured stderr
- `session-export.json` — optional opencode session export
- `followup-*` — optional phase 2 artifacts

Generated projects may contain unsafe commands. Prefer harness scripts for verification.

## Runtime verification

Per-project artifacts:

```text
results/<run_id>/projects/<harness>-<slug>/project/_runtime_verification/
```

Aggregate summary:

```text
results/<run_id>/runtime_verification_summary.json
```

## Audit reports

Each `(auditor, target)` pair writes to:

```text
results/<run_id>/audit-reports/<auditor_slug>/<target_slug>/
```

Common files:

- `report.md` — markdown rubric report (sections A–I)
- `result.json` — audit run metadata
- `generation-metrics.json` — generation time, tokens, `estimated_cost_usd` from [`PRICING.md`](PRICING.md)
- `stream.ndjson`, `stderr.log` — raw auditor stream (excluded from published campaigns)

Auditor-level outputs:

```text
results/<run_id>/audit-reports/<auditor_slug>/comparison.md
results/<run_id>/meta-analysis.md
results/latest/meta-analysis.md   # symlink → current run dir
```

Comparison and meta-analysis files are generated — do not hand-edit.

## Legacy flat layout

Omitting `--run-id` keeps the older flat trees for one-off dev:

- `results/<harness>-<slug>/`
- `audit-reports/<auditor>/<target>/`

New full-pipeline runs require `--run-id`.

## Published campaigns

After `publish_campaign.py`, git tracks a curated subset documented in
`data/campaigns/<id>/manifest.json`. See [`data/README.md`](../data/README.md).

## Cleanup

Unpublished `results/` trees can be large (venv, stream logs).
Review before sharing outside the machine. Do not commit secrets or generated auth files.
