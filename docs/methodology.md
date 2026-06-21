# Assessment methodology

Primary overview lives in [README.md](../README.md) (pipeline, rubric, artifact map,
and latest results). This file retains version-specific prompt references and
extended cross-links.

See [`CONTEXT.md`](../CONTEXT.md) for vocabulary (`harness`, `target`, `auditor`, etc.).

## Prompt versions (latest campaign)

| Phase | Version | Prompt file |
|-------|---------|-------------|
| Generation | `benchmark-v3.5` | [`prompts/benchmark_prompt.txt`](../prompts/benchmark_prompt.txt) |
| Generation follow-up | `benchmark-followup-v3.5` | [`prompts/benchmark_followup_prompt.txt`](../prompts/benchmark_followup_prompt.txt) |
| Role 1 audit | `audit-v3.13` | [`prompts/audit_prompt_template.txt`](../prompts/audit_prompt_template.txt) |
| Role 2 meta-analysis | `meta-v3.16` | [`prompts/audit_meta_analysis_prompt.txt`](../prompts/audit_meta_analysis_prompt.txt) |

Prompt versions for older campaigns are recorded in each
[`data/campaigns/<id>/manifest.json`](../data/campaigns/2026-05-ollama-cloud-v3.2/manifest.json).

## Published data layout

Benchmark and audit outputs are written to `results/<run_id>/` during runs
(`--run-id` on every pipeline command). After a campaign completes,
[`scripts/publish_campaign.py`](../scripts/publish_campaign.py) strips ephemeral
artifacts and updates git allowlists. Full artifact rules and manifest schema:
[`published-data.md`](published-data.md).

## Latest published results

See [README.md → Latest results](../README.md#latest-results) and
[README.md → Artifact map](../README.md#artifact-map) for campaign links and how
`projects/` connects to `audit-reports/` via target slugs within each run directory.

Campaign index: [`data/README.md`](../data/README.md)
