# Published campaign data

Benchmark and audit outputs are written to `results/` and `audit-reports/` during
runs. By default those trees are **gitignored**. After a campaign completes, run
[`scripts/publish_campaign.py`](../scripts/publish_campaign.py) to strip ephemeral
artifacts, write a campaign manifest, and update `.gitignore` allowlists so curated
data can be committed.

## Layout

```text
data/
├── README.md                              # campaign index
└── campaigns/
    ├── 2026-05-ollama-cloud-v3.2/
    │   └── manifest.json                  # metadata + target list
    └── latest -> 2026-05-ollama-cloud-v3.2

audit-reports/
├── latest -> codex_gpt_5_5                # stable README link target
└── codex_gpt_5_5/
    ├── meta-analysis.md
    ├── comparison.md
    └── <harness>-<model>/
        ├── report.md
        ├── generation-metrics.json
        └── result.json

results/
└── <harness>-<model>/
    ├── result.json
    ├── prompt.txt
    └── project/                           # trimmed source only
```

Harness scripts keep writing to `results/` and `audit-reports/` — no path changes
required. Campaign manifests document which paths are published.

## What is committed

### Audit tree (`audit-reports/<auditor>/`)

| Included | Excluded |
|----------|----------|
| `meta-analysis.md`, `comparison.md` | `_meta-analysis-runs/` |
| Per target: `report.md`, `generation-metrics.json`, `result.json` | `stream.ndjson`, `stderr.log`, `prompt.txt`, `AGENTS.md`, `CLAUDE.md` |

### Benchmark tree (`results/<target>/`)

| Included | Excluded |
|----------|----------|
| `result.json`, `prompt.txt`, `followup-prompt.txt` | `*.ndjson`, `stderr.log`, `session-export.json` |
| `project/**` application source | `.venv`, `venv`, `.venv*`, `node_modules`, `twcli`, `tailwindcss`, `staticfiles`, `.git`, tool caches, `_runtime_verification/` |

Typical published footprint: **~25 MB audits + ~120 MB trimmed source** per full grid campaign (plain git, no LFS).

## Manifest schema

Each campaign has `data/campaigns/<id>/manifest.json`:

```json
{
  "id": "2026-05-ollama-cloud-v3.2",
  "label": "Ollama Cloud grid — benchmark v3.2",
  "date": "2026-05-29",
  "prompt_versions": {
    "benchmark": "benchmark-v3.2",
    "benchmark_followup": "benchmark-followup-v3.2",
    "audit": "audit-v3.8",
    "meta": "meta-v3.11"
  },
  "auditor_slug": "codex_gpt_5_5",
  "meta_analysis": "audit-reports/codex_gpt_5_5/meta-analysis.md",
  "audit_root": "audit-reports/codex_gpt_5_5",
  "benchmark_results_root": "results",
  "targets": ["codex-deepseek_v4_pro_ollama_cloud", "..."],
  "harnesses": ["claude", "codex", "cursor", "opencode"],
  "models_config_sha256": "...",
  "harnesses_config_sha256": "..."
}
```

## Publishing workflow

```bash
python3 scripts/publish_campaign.py \
  --campaign-id <YYYY-MM-short-label> \
  --label "<human-readable label>" \
  --auditor <auditor_slug> \
  --auto-discover-targets \
  --campaign-date <YYYY-MM-DD>
```

The script:

1. Discovers targets from `audit-reports/<auditor>/*/report.md`
2. Strips ephemeral directories from each `results/<target>/project/`
3. Writes `data/campaigns/<id>/manifest.json`
4. Regenerates the `# BEGIN published-campaigns` block in `.gitignore`
5. Updates symlinks `data/campaigns/latest` and `audit-reports/latest`
6. Scans publishable text files for obvious secret patterns (warnings only unless `--fail-on-secrets`)

Then commit the manifest, symlinks, `.gitignore` block, audit tree, and listed result dirs.

## Multiple campaigns

Older campaigns remain in git under their auditor directories. Update
[`data/README.md`](../data/README.md) when adding a new row to the campaign table.
Running `publish_campaign.py` retargets `latest` symlinks; the README link
[`audit-reports/latest/meta-analysis.md`](../audit-reports/latest/meta-analysis.md)
stays stable across campaigns.

## Safety

Published trees contain **model-generated code**. Treat it as untrusted. Do not run
generated migrations, shell scripts, or installers against shared services without
review. Never commit real API keys — rotate any secret that appears in logs or output.
