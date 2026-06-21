# Published campaign data

Benchmark and audit outputs are written to `results/<run_id>/` during runs.
By default those trees are **gitignored**. After a campaign completes, run
[`scripts/publish_campaign.py`](../scripts/publish_campaign.py) with `--run-id`
to strip ephemeral artifacts, write a campaign manifest, and update `.gitignore`
allowlists so curated data can be committed.

## Layout

```text
data/
├── README.md                              # campaign index
└── campaigns/
    ├── 2026-05-ollama-cloud-v3.2/
    │   └── manifest.json                  # metadata + target list
    └── latest -> 2026-05-ollama-cloud-v3.2

results/
├── latest -> run_01                       # stable README link target
└── run_01/
    ├── meta-analysis.md
    ├── audit-reports/
    │   └── codex_gpt_5_5/
    │       ├── comparison.md
    │       └── <harness>-<model>/
    │           └── run_XX/
    │               ├── report.md
    │               ├── generation-metrics.json
    │               └── result.json
    └── projects/
        └── <harness>-<model>/
            └── run_XX/
                ├── result.json
                ├── prompt.txt
                └── project/                   # trimmed source only
```

Replicate folders (`run_01`, `run_02`, …) are driven by `num_runs` in
`config/models.json`. Manifest `targets` list entries use the full slug
(e.g. `codex-deepseek_v4_pro_ollama_cloud/run_01`).

Harness scripts require `--run-id run_XX` for new full-pipeline runs. Campaign
manifests document which paths are published.

## What is committed

### Audit tree (`results/<run_id>/audit-reports/<auditor>/`)

| Included | Excluded |
|----------|----------|
| `comparison.md` | `_meta-analysis-runs/` |
| Per target replicate: `run_XX/report.md`, `generation-metrics.json`, `result.json` | `stream.ndjson`, `stderr.log`, `prompt.txt`, `AGENTS.md`, `CLAUDE.md` |

### Run root

| Included | Excluded |
|----------|----------|
| `meta-analysis.md` | — |

### Benchmark tree (`results/<run_id>/projects/<target>/`)

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
  "run_id": "run_01",
  "prompt_versions": {
    "benchmark": "benchmark-v3.3",
    "benchmark_followup": "benchmark-followup-v3.3",
    "audit": "audit-v3.10",
    "meta": "meta-v3.11"
  },
  "auditor_slug": "codex_gpt_5_5",
  "meta_analysis": "results/run_01/meta-analysis.md",
  "audit_root": "results/run_01/audit-reports/codex_gpt_5_5",
  "benchmark_results_root": "results/run_01/projects",
  "targets": ["codex-deepseek_v4_pro_ollama_cloud/run_01", "..."],
  "harnesses": ["claude", "codex", "cursor", "opencode"],
  "models_config_sha256": "...",
  "harnesses_config_sha256": "..."
}
```

## Publishing workflow

```bash
python3 scripts/publish_campaign.py \
  --run-id run_02 \
  --campaign-id <YYYY-MM-short-label> \
  --label "<human-readable label>" \
  --auditor <auditor_slug> \
  --auto-discover-targets \
  --campaign-date <YYYY-MM-DD>
```

The script:

1. Discovers targets from `results/<run_id>/audit-reports/<auditor>/*/run_XX/report.md` (or flat legacy `*/report.md`)
2. Strips ephemeral directories from each `results/<run_id>/projects/<target>/run_XX/project/` (or flat `project/`)
3. Writes `data/campaigns/<id>/manifest.json`
4. Regenerates the `# BEGIN published-campaigns` block in `.gitignore`
5. Updates symlinks `data/campaigns/latest` and `results/latest`
6. Scans publishable text files for obvious secret patterns (warnings only unless `--fail-on-secrets`)

Then commit the manifest, symlinks, `.gitignore` block, audit tree, and listed result dirs.

## Multiple campaigns

Older campaigns remain in git under their run directories. Update
[`data/README.md`](../data/README.md) when adding a new row to the campaign table.
Running `publish_campaign.py` retargets `latest` symlinks and copies
[`results/latest-meta-analysis.md`](../results/latest-meta-analysis.md) for
GitHub-compatible README links (GitHub does not resolve nested symlink paths).

## Safety

Published trees contain **model-generated code**. Treat it as untrusted. Do not run
generated migrations, shell scripts, or installers against shared services without
review. Never commit real API keys — rotate any secret that appears in logs or output.
