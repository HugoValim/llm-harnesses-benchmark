# Published benchmark campaigns

This directory indexes benchmark campaigns whose audit reports and trimmed
generated projects are tracked in git. Runtime outputs under `results/` and
`audit-reports/` remain gitignored by default except for paths listed in each
campaign manifest and the generated `.gitignore` block.

## Latest campaign

See [README.md → Artifact map](../README.md#artifact-map) for how `results/` and
`audit-reports/` connect via target slugs.

- **ID:** [`2026-05-ollama-cloud-v3.2`](campaigns/2026-05-ollama-cloud-v3.2/manifest.json)
- **Label:** Ollama Cloud grid — benchmark v3.2
- **Meta-analysis:** [`audit-reports/latest/meta-analysis.md`](../audit-reports/latest/meta-analysis.md)
- **Auditor:** `codex_gpt_5_5`
- **Targets:** 28 `(harness, model)` runs across opencode, codex, claude, and cursor

Symlink [`campaigns/latest`](campaigns/latest) always points at the current campaign directory.

## All campaigns

| Campaign | Date | Prompts | Meta-analysis |
|----------|------|---------|---------------|
| [`2026-05-ollama-cloud-v3.2`](campaigns/2026-05-ollama-cloud-v3.2/manifest.json) | 2026-05-29 | benchmark-v3.2 / audit-v3.8 / meta-v3.11 | [`meta-analysis.md`](../audit-reports/codex_gpt_5_5/meta-analysis.md) |

## Publishing a new campaign

After benchmark, audit, and meta-analysis complete:

```bash
python3 scripts/publish_campaign.py \
  --campaign-id <YYYY-MM-short-label> \
  --label "<human label>" \
  --auditor <auditor_slug> \
  --auto-discover-targets \
  --campaign-date <YYYY-MM-DD>
```

See [`docs/published-data.md`](../docs/published-data.md) for artifact rules and git layout.
