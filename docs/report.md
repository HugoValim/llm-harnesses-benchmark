# Benchmark Report

Generated at: 2026-05-20T11:17:08+00:00
Prompt SHA256: `9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28`

## Progress

- `completed`: 0
- `completed_with_errors`: 0
- `failed`: 0
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 2

## Runner

`opencode run --agent build --format json` (harness `opencode` — runs under `results/opencode-<slug>/`)

- Same opencode runner as the Rails profile - chosen for machine-readable JSON events with session IDs and token counts.
- Models with opencode_id in models.json are auto-included using that ID (typically an OpenRouter path).
- Verification is performed by scripts/analyze_results_runtime_python.py: discover Django app root, install deps in a venv, boot the ASGI server, headless browser probe, docker build, docker compose.

## Model Selection

- `claude_sonnet_4_6` -> `openrouter/anthropic/claude-sonnet-4.6`: Reference Claude Sonnet model for build, audit, and meta-analysis runs.
- `claude_opus_4_7` -> `openrouter/anthropic/claude-opus-4.7`: Tier-A Claude baseline for build, audit, and meta-analysis runs.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Claude Sonnet 4.6 | anthropic | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Claude Opus 4.7 | anthropic | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |

## Per-Run Paths

Each run writes to `results/opencode-<slug>/` with these files:

- `project/`: the generated project workspace
- `prompt.txt`: exact prompt used for the run
- `opencode-output.ndjson`: raw JSON event stream from opencode
- `opencode-stderr.log`: stderr from the opencode process
- `followup-prompt.txt`: second-phase validation prompt for continuations when enabled
- `followup-opencode-output.ndjson`: raw JSON event stream from the follow-up continuation
- `followup-opencode-stderr.log`: stderr from the follow-up continuation
- `session-export.json`: exported opencode session snapshot when available
- `result.json`: normalized metadata used for this report

