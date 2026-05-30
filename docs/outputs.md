# Outputs

Runtime paths used during benchmark runs. For git-published campaign artifacts see
[`published-data.md`](published-data.md).

## Benchmark results

Each benchmark run writes to:

```text
results/<harness>-<slug>/
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
results/<harness>-<slug>/project/_runtime_verification/
```

Aggregate summary:

```text
results/runtime_verification_summary.json
```

## Audit reports

Each `(auditor, target)` pair writes to:

```text
audit-reports/<auditor_slug>/<target_slug>/
```

Common files:

- `report.md` — markdown rubric report (sections A–I)
- `result.json` — audit run metadata
- `generation-metrics.json` — generation time, tokens, `estimated_cost_usd` from [`PRICING.md`](PRICING.md)
- `stream.ndjson`, `stderr.log` — raw auditor stream (excluded from published campaigns)

Auditor-level outputs:

```text
audit-reports/<auditor_slug>/comparison.md
audit-reports/<auditor_slug>/meta-analysis.md
audit-reports/latest/meta-analysis.md   # symlink → current auditor dir
```

Comparison and meta-analysis files are generated — do not hand-edit.

## Published campaigns

After `publish_campaign.py`, git tracks a curated subset documented in
`data/campaigns/<id>/manifest.json`. See [`data/README.md`](../data/README.md).

## Cleanup

Unpublished `results/` and `audit-reports/` trees can be large (venv, stream logs).
Review before sharing outside the machine. Do not commit secrets or generated auth files.
