# Benchmark Report

Generated at: 2026-05-15T06:48:27+00:00
Prompt SHA256: `9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28`

## Progress

- `completed`: 1
- `completed_with_errors`: 0
- `failed`: 0
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 2

## Runner

`codex exec --json --ephemeral ...` (harness `codex` — runs under `results/codex-<slug>/`)

- ChatGPT-linked Codex: plain `codex` on PATH (no `ollama launch`). Authenticate with `codex login` (ChatGPT OAuth) or subscription-backed credentials.
- Model IDs must match strings your Codex CLI accepts on `codex exec -m` (override). Run `codex debug models --bundled` to inspect the bundled catalog.
- Uses `codex exec --json --ephemeral` with the harness autonomy flags.
- Run: python scripts/run_benchmark.py --harness codex --config config/codex_chatgpt_models.json

## Model Selection

- `codex_gpt_5_5` -> `gpt-5.5`: Codex exposes `gpt-5.5` for ChatGPT-linked auth; verify with `codex debug models`. May require subscription tier; fallback to `gpt-5.4` if unsupported.
- `codex_gpt_5_4` -> `gpt-5.4`: Codex CLI docs example for `-m`. Edit `id` if your catalog uses a different tag.
- `codex_gpt_5_3_codex` -> `gpt-5.3-codex`: Often listed as the Codex-tuned variant; confirm with `codex debug models`.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| GPT-5.5 (Codex / ChatGPT) | openai | - | completed | 1249.65 | 2375220 | 4472.10 | yes | 50 | Django + Channels app, tests, README, and container files detected. |
| GPT-5.4 (Codex / ChatGPT) | openai | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| GPT-5.3-Codex (Codex CLI) | openai | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |

## Per-Run Paths

Each run writes to `results/codex-<slug>/` with these files:

- `project/`: the generated project workspace
- `prompt.txt`: exact prompt used for the run
- `opencode-output.ndjson`: raw JSON event stream from opencode
- `opencode-stderr.log`: stderr from the opencode process
- `followup-prompt.txt`: second-phase validation prompt for continuations when enabled
- `followup-opencode-output.ndjson`: raw JSON event stream from the follow-up continuation
- `followup-opencode-stderr.log`: stderr from the follow-up continuation
- `session-export.json`: exported opencode session snapshot when available
- `result.json`: normalized metadata used for this report

