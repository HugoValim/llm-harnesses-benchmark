# Benchmark Report

Generated at: 2026-05-09T05:11:51+00:00
Prompt SHA256: `b5d9e80245fd8603224b59d6cdd6356a5c3907a002137532c27b390cd53de69d`

## Progress

- `completed`: 0
- `completed_with_errors`: 0
- `failed`: 0
- `timeout`: 0
- `not_run`: 5

## Runner

`codex exec --json --ephemeral ...` (harness `codex` — runs under `results/codex-<slug>/`)

- Ollama Cloud models invoked via the `ollama launch codex` shim.
- Uses `codex exec --json --ephemeral` with full autonomy flags.
- Per-model `command_prefix` replaces the default `codex` leader so the harness routes through Ollama Cloud.

## Model Selection

- `kimi_k2_6_ollama_cloud` -> `kimi-k2.6:cloud`: Best Kimi model on Ollama Cloud through Codex CLI — pairs with the Claude Code Ollama Cloud harness for cross-runner comparison.
- `qwen3_5_ollama_cloud` -> `qwen3.5:cloud`: Best Qwen model on Ollama Cloud via Codex — reasoning and agentic tool use.
- `glm_5_1_ollama_cloud` -> `glm-5.1:cloud`: Best GLM model on Ollama Cloud via Codex — long-horizon agentic engineering.
- `minimax_m2_7_ollama_cloud` -> `minimax-m2.7:cloud`: Best MiniMax model on Ollama Cloud via Codex.
- `deepseek_v4_pro_ollama_cloud` -> `deepseek-v4-pro:cloud`: Best DeepSeek model on Ollama Cloud via Codex.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Kimi K2.6 (Ollama Cloud) via Codex | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Qwen 3.5 (Ollama Cloud) via Codex | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| GLM 5.1 (Ollama Cloud) via Codex | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| MiniMax M2.7 (Ollama Cloud) via Codex | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| DeepSeek V4 Pro (Ollama Cloud) via Codex | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |

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

