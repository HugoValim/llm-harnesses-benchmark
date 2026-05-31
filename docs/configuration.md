# Configuration

This repo uses two config files:

- `config/models.json`: shared model registry.
- `config/harnesses.json`: harness command metadata.

`scripts/run_benchmark.py`, `scripts/run_audit.py`, and
`scripts/run_meta_analysis.py` all default to `config/models.json` through the
`--models-config` flag.

## Model registry

Each row in `config/models.json` has a stable `slug`. The slug is used in CLI
selection, result directory names, audit report paths, and report rows.

Common fields:

- `slug`: filesystem-safe model key.
- `label`: display name used in reports.
- `provider`: billing/provider channel key (see `docs/PRICING.md`).
- `harness`: list of runners that execute this model (see below). The benchmark
  runs `num_runs` replicates for each harness in the list.
- `id`: provider or CLI model id.
- `opencode_id`: optional opencode-specific id when `harness` is `opencode`.
- `selection_reason`: maintainer note shown in audit comparison tables.
- `known_issues`: optional warning for model-specific behavior.
- `skip_by_default`: optional flag used by preview-speed handling.

Allowed `harness` list entries:

| Value | CLI / result prefix | Launch |
| --- | --- | --- |
| `claude` | `claude` | direct Claude Code CLI |
| `codex` | `codex` | direct Codex CLI |
| `opencode` | `opencode` | direct OpenCode CLI |
| `cursor` | `cursor` | Cursor Agent CLI |
| `ollama_claude` | `claude` | `ollama launch --yes claude` |
| `ollama_codex` | `codex` | `ollama launch --yes codex` |
| `ollama_opencode` | `opencode` | `ollama launch --yes opencode` |

Example — one Ollama Cloud model on all three contest harnesses:

```json
{
  "slug": "kimi_k2_6",
  "harness": ["ollama_claude", "ollama_codex", "ollama_opencode"],
  "num_runs": 3
}
```

That dispatches nine benchmark leaves: `claude-kimi_k2_6/run_01` …
`opencode-kimi_k2_6/run_03`.

## Harness registry

`config/harnesses.json` stores command-level metadata for each supported
harness:

- `opencode`: shells out to `opencode run --agent build --format json`.
- `codex`: shells out through `codex exec --json --ephemeral`.
- `claude`: shells out through `claude -p --output-format stream-json`.
- `cursor`: shells out through `agent -p --output-format stream-json`.

The harness config is not a secret store. Keep credentials in environment
variables or the relevant CLI's auth mechanism.

## CLI selection

Use `--harness` to select the runner and repeat `--model` to select slugs:

```bash
python3 scripts/run_benchmark.py --harness opencode --model claude_sonnet_4_6
python3 scripts/run_benchmark.py --harness codex --model codex_gpt_5_5
python3 scripts/run_benchmark.py --harness claude --model claude_opus_4_7
python3 scripts/run_benchmark.py --harness cursor --model composer_2_5
```

Use `--models-config` only when testing an alternate registry:

```bash
python3 scripts/run_benchmark.py --harness codex --models-config /path/to/models.json
```

## Adding a model

Before a cross-harness contest run, authenticate each CLI you plan to use (`codex login`, `claude` subscription or `ANTHROPIC_API_KEY`, `agent login` or `CURSOR_API_KEY`, OpenCode/OpenRouter as configured). Benchmark builds isolate per-replicate runtime dirs; staged subscription auth requires the corresponding dot-dir under your real `$HOME` unless you use API keys. See [running.md](running.md#full-pipeline) for build-parity details.

1. Add a row to `config/models.json` with a unique `slug` and a `harness` list.
2. For Ollama Cloud contest coverage, include
   `["ollama_claude", "ollama_codex", "ollama_opencode"]` on one base slug row.
3. Add pricing for the base slug in `docs/PRICING.md` when billable.
4. Run one selected benchmark:

```bash
python3 scripts/run_benchmark.py --harness <harness> --model <slug>
```

5. Validate the generated project:

```bash
python3 scripts/analyze_results_runtime.py --only <harness>-<slug>
```

6. Audit or manually inspect the generated app before assigning a tier.
