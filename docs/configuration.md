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
- `provider`: routing key.
- `id`: provider or CLI model id.
- `opencode_id`: optional opencode-specific id, commonly an OpenRouter path.
- `enable_followup`: whether phase 2 should run for that model.
- `selection_reason`: maintainer note shown in docs/reports.
- `known_issues`: optional warning for model-specific behavior.
- `skip_by_default`: optional flag used by preview-speed handling.

Provider routing:

- `anthropic` -> Claude harness.
- `openai` -> Codex harness.
- `cursor` -> Cursor harness.
- `ollama_cloud` -> Claude, Codex, or opencode via `ollama launch`.
- Any row with `opencode_id` can also run on opencode.

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

1. Add a row to `config/models.json` with a unique `slug`.
2. Set `provider` so the row routes to the intended harness.
3. Add `opencode_id` if the row should be runnable by opencode.
4. Run one selected benchmark:

```bash
python3 scripts/run_benchmark.py --harness <harness> --model <slug>
```

5. Validate the generated project:

```bash
python3 scripts/analyze_results_runtime.py --only <harness>-<slug>
```

6. Audit or manually inspect the generated app before assigning a tier.
