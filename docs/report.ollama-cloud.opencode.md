# Benchmark Report

Generated at: 2026-05-12T06:28:57+00:00
Prompt SHA256: `b5d9e80245fd8603224b59d6cdd6356a5c3907a002137532c27b390cd53de69d`

## Progress

- `completed`: 4
- `completed_with_errors`: 0
- `failed`: 1
- `timeout`: 0
- `not_run`: 0

## Runner

`opencode run --agent build --format json` (harness `opencode` — runs under `results/opencode-<slug>/`)

- Ollama Cloud models invoked via the `ollama launch opencode` shim.
- Uses `opencode run --agent build --format json` with full autonomy.
- Per-model `command_prefix` replaces the default `opencode` leader so the harness routes through Ollama Cloud.

## Model Selection

- `kimi_k2_6_ollama_cloud` -> `kimi-k2.6:cloud`: Best Kimi model on Ollama Cloud through OpenCode CLI — pairs with the Claude Code and Codex Ollama Cloud harnesses for cross-runner comparison.
- `qwen3_5_ollama_cloud` -> `qwen3.5:cloud`: Best Qwen model on Ollama Cloud via OpenCode — reasoning and agentic tool use.
- `glm_5_1_ollama_cloud` -> `glm-5.1:cloud`: Best GLM model on Ollama Cloud via OpenCode — long-horizon agentic engineering.
- `minimax_m2_7_ollama_cloud` -> `minimax-m2.7:cloud`: Best MiniMax model on Ollama Cloud via OpenCode.
- `deepseek_v4_pro_ollama_cloud` -> `deepseek-v4-pro:cloud`: Best DeepSeek model on Ollama Cloud via OpenCode.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Kimi K2.6 (Ollama Cloud) via OpenCode | ollama_cloud | - | failed | 2858.25 | 110198 | 145.92 | yes | 42 | Exit code -9. Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 5439.39 | 138470 | 32.27 | yes | 41 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 2356.70 | 80743 | 175.68 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 2592.29 | 154039 | 79.46 | yes | 41 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 4179.05 | 100111 | 72.71 | yes | 36 | Django + Channels app, tests, README, and container files detected. |

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

