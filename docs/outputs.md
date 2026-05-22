# Outputs

## Benchmark Results

Each benchmark run writes to:

```text
results/<harness>-<slug>/
```

Common files:

- `project/`: generated Django project.
- `result.json`: status, timing, token, cost, and summary metadata.
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
- `static-analysis.json`: optional local quality probe output.
- `stream.ndjson`: raw auditor stream.
- `stderr.log`: auditor stderr.

Comparison outputs are generated from existing audit reports and should not be
hand-edited.

## Aggregate Reports

Generated benchmark reports live under `docs/`:

- `docs/report.md`
- `docs/report.opencode.md`
- `docs/report.codex.md`
- `docs/report.claude-code.md`
- `docs/report.claude-opus.md`
- `docs/report.cursor.md`

These files summarize harness-level run metadata. They do not prove generated
apps are correct; use runtime verification and audit reports for behavioral
evidence.

## Cleanup

`results/` and `audit-reports/` can be large and may contain generated code,
logs, and environment-derived paths. Review before sharing outside the machine.
Do not commit secrets or generated auth files.
