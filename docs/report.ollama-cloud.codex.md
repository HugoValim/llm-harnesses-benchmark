# Benchmark Report

Generated at: 2026-05-19T07:30:07+00:00
Prompt SHA256: `9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28`

## Progress

- `completed`: 6
- `completed_with_errors`: 0
- `failed`: 2
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 0

## Runner

`codex exec --json --ephemeral ...` (harness `codex` — runs under `results/codex-<slug>/`)

- Ollama Cloud models invoked via the `ollama launch codex` shim.
- Uses `codex exec --json --ephemeral` with full autonomy flags.
- Per-model `command_prefix` replaces the default `codex` leader so the harness routes through Ollama Cloud.
- Codex context overflow on long agentic runs is a known issue for `:cloud` models through `ollama launch codex`: codex can't read context metadata from Ollama's `/v1` endpoint (openai/codex#14757), and pinning `model_context_window` triggers `fill_to_context_window` prompt-padding (openai/codex#16068). Setting `model_auto_compact_token_limit` alone has also been observed to make things worse. Prefer the claude or opencode harness for these models when long-horizon runs matter.

## Model Selection

- `kimi_k2_6_ollama_cloud` -> `kimi-k2.6:cloud`: Best Kimi model on Ollama Cloud. State-of-the-art coding + long-horizon execution + multimodal agent swarm.
- `qwen3_5_ollama_cloud` -> `qwen3.5:cloud`: Best Qwen model on Ollama Cloud. Reasoning, coding, and agentic tool use with vision.
- `glm_5_1_ollama_cloud` -> `glm-5.1:cloud`: Best GLM model on Ollama Cloud. Long-horizon agentic engineering with autonomous execution and sustained iteration.
- `minimax_m2_7_ollama_cloud` -> `minimax-m2.7:cloud`: Best MiniMax model on Ollama Cloud. Mid-tier model testing Python-stack knowledge and LangChain wiring capability.
- `deepseek_v4_pro_ollama_cloud` -> `deepseek-v4-pro:cloud`: Best DeepSeek model on Ollama Cloud. Tests whether Ollama Cloud serving avoids the reasoning_content multi-turn bug seen via OpenRouter/opencode.
- `deepseek_v4_flash_ollama_cloud` -> `deepseek-v4-flash:cloud`: Faster DeepSeek V4 tier on Ollama Cloud — latency/cost tradeoff vs V4 Pro on the same brief.
- `gemma4_ollama_cloud` -> `gemma4:31b-cloud`: Google Gemma 4 on Ollama Cloud (`gemma4:31b-cloud`; `gemma4:cloud` is not published on the registry) — cross-vendor baseline on the Django + Channels brief.
- `nemotron_3_super_ollama_cloud` -> `nemotron-3-super:cloud`: NVIDIA Nemotron 3 Super on Ollama Cloud — agentic coding baseline in the cloud registry.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Kimi K2.6 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 1690.56 | 1371230 | 2298.41 | yes | 37 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2739.37 | 2841138 | 1842.17 | yes | 40 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2132.72 | 2866399 | 2835.52 | yes | 50 | Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 5897.59 | 7968933 | 2378.68 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2294.77 | 3713717 | 3283.89 | yes | 44 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Flash (Ollama Cloud) via Codex | ollama_cloud | - | completed | 4220.03 | 6482866 | 2029.85 | yes | 43 | Django + Channels app, tests, README, and container files detected. |
| Gemma 4 31B (Ollama Cloud) via Codex | ollama_cloud | - | failed | 1958.75 | 0 | - | yes | 35 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| Nemotron 3 Super (Ollama Cloud) via Codex | ollama_cloud | - | failed | 1448.27 | 0 | - | yes | 34 | Exit code -15. Django + Channels app, tests, README, and container files detected. |

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

