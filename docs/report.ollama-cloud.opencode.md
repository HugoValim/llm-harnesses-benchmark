# Benchmark Report

Generated at: 2026-05-19T08:42:42+00:00
Prompt SHA256: `9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28`

## Progress

- `completed`: 5
- `completed_with_errors`: 0
- `failed`: 3
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 0

## Runner

`opencode run --agent build --format json` (harness `opencode` — runs under `results/opencode-<slug>/`)

- Ollama Cloud models invoked via the `ollama launch opencode` shim.
- Uses `opencode run --agent build --format json` with full autonomy.
- Per-model `command_prefix` replaces the default `opencode` leader so the harness routes through Ollama Cloud.

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
| Kimi K2.6 (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 2934.60 | 107126 | 106.61 | yes | 40 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 3809.34 | 130972 | 44.06 | yes | 38 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) via OpenCode | ollama_cloud | - | failed | 1061.75 | 57531 | 136.64 | yes | 41 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) via OpenCode | ollama_cloud | - | failed | 1597.09 | 78731 | 81.57 | yes | 36 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 2469.48 | 123853 | 84.17 | yes | 41 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Flash (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 6342.40 | 111789 | 64.98 | yes | 45 | Django + Channels app, tests, README, and container files detected. |
| Gemma 4 31B (Ollama Cloud) via OpenCode | ollama_cloud | - | completed | 2267.48 | 73583 | 75.60 | yes | 29 | Django + Channels app, tests, README, and container files detected. |
| Nemotron 3 Super (Ollama Cloud) via OpenCode | ollama_cloud | - | failed | 1648.38 | 101962 | 97.93 | yes | 35 | Exit code -15. Django + Channels app, tests, README, and container files detected. |

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

