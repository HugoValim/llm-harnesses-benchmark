# Benchmark Report

Generated at: 2026-05-12T11:29:25+00:00
Prompt SHA256: `b5d9e80245fd8603224b59d6cdd6356a5c3907a002137532c27b390cd53de69d`

## Progress

- `completed`: 4
- `completed_with_errors`: 0
- `failed`: 0
- `timeout`: 1
- `not_run`: 0

## Runner

`codex exec --json --ephemeral ...` (harness `codex` — runs under `results/codex-<slug>/`)

- Ollama Cloud models invoked via the `ollama launch codex` shim.
- Uses `codex exec --json --ephemeral` with full autonomy flags.
- Per-model `command_prefix` replaces the default `codex` leader so the harness routes through Ollama Cloud.
- Codex context overflow on long agentic runs is a known issue for `:cloud` models through `ollama launch codex`: codex can't read context metadata from Ollama's `/v1` endpoint (openai/codex#14757), and pinning `model_context_window` triggers `fill_to_context_window` prompt-padding (openai/codex#16068). Setting `model_auto_compact_token_limit` alone has also been observed to make things worse. Prefer the claude or opencode harness for these models when long-horizon runs matter.

## Model Selection

- `kimi_k2_6_ollama_cloud` -> `kimi-k2.6:cloud`: Best Kimi model on Ollama Cloud through Codex CLI — pairs with the Claude Code Ollama Cloud harness for cross-runner comparison.
- `qwen3_5_ollama_cloud` -> `qwen3.5:cloud`: Best Qwen model on Ollama Cloud via Codex — reasoning and agentic tool use.
- `glm_5_1_ollama_cloud` -> `glm-5.1:cloud`: Best GLM model on Ollama Cloud via Codex — long-horizon agentic engineering.
- `minimax_m2_7_ollama_cloud` -> `minimax-m2.7:cloud`: Best MiniMax model on Ollama Cloud via Codex.
- `deepseek_v4_pro_ollama_cloud` -> `deepseek-v4-pro:cloud`: Best DeepSeek model on Ollama Cloud via Codex.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Kimi K2.6 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2250.22 | 2623984 | 2367.23 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2938.39 | 3958166 | 2705.72 | yes | 31 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2226.65 | 827571 | 1184.80 | yes | 40 | Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) via Codex | ollama_cloud | - | timeout | 7374.67 | 0 | - | yes | 38 | Timed out. Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) via Codex | ollama_cloud | - | completed | 3113.66 | 2492971 | 1444.51 | yes | 40 | Django + Channels app, tests, README, and container files detected. |

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

