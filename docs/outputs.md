# Outputs

## Benchmark Results

Each benchmark run writes to:

```text
results/<harness>-<slug>/
```

Common files:

- `project/`: generated Django project.
- `result.json`: status, timing, tokens, and summary metadata (no USD cost — see audit `generation-metrics.json`).
- `prompt.txt`: prompt copy when the harness records it.
- `stream.ndjson`: stream events for Claude-style runs.
- `stderr.log`: captured stderr for Claude-style runs.
- `opencode-output.ndjson`: opencode/codex stream events.
- `opencode-stderr.log`: opencode/codex stderr.
- `session-export.json`: optional opencode session export.
- `followup-*`: optional phase 2 artifacts.

Generated projects are untrusted code. Prefer harness scripts for verification
and avoid running generated commands against shared services.

## Runtime Verification

Runtime verification writes per-project artifacts under:

```text
results/<harness>-<slug>/project/_runtime_verification/
```

The aggregate runtime summary is:

```text
results/runtime_verification_summary.json
```

## Audit Reports

Each audit pair writes to:

```text
audit-reports/<auditor_slug>/<target_slug>/
```

Common files:

- `report.md`: markdown rubric report.
- `result.json`: audit run metadata.
- `generation-metrics.json`: precomputed generation time, tokens, and `estimated_cost_usd` from `docs/PRICING.md` + benchmark `result.json`.
- `stream.ndjson`: raw auditor stream.
- `stderr.log`: auditor stderr.

Comparison outputs are generated from existing audit reports and should not be
hand-edited.

## Cleanup

`results/` and `audit-reports/` can be large and may contain generated code,
logs, and environment-derived paths. Review before sharing outside the machine.
Do not commit secrets or generated auth files.
