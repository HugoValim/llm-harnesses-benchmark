# Benchmark Report

Generated at: 2026-05-20T12:23:08+00:00
Prompt SHA256: `9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28`

## Progress

- `completed`: 7
- `completed_with_errors`: 0
- `failed`: 2
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 2

## Runner

`codex exec --json --ephemeral ...` (harness `codex` — runs under `results/codex-<slug>/`)

- ChatGPT-linked Codex: plain `codex` on PATH. Authenticate with `codex login` (ChatGPT OAuth) or subscription-backed credentials.
- openai provider -> runner_type=ollama -> `ollama launch --yes codex` (non-interactive).
- Uses `codex exec --json --ephemeral` with the harness autonomy flags.

## Model Selection

- `codex_gpt_5_5` -> `gpt-5.5`: Codex GPT-5.5 with extra-high reasoning. Verify availability with `codex debug models`.
- `codex_gpt_5_4` -> `gpt-5.4`: Codex CLI baseline model. Edit the harness mapping if your catalog uses a different tag.
- `codex_gpt_5_3_codex` -> `gpt-5.3-codex`: Codex-tuned baseline model; confirm with `codex debug models`.
- `kimi_k2_6_ollama_cloud` -> `kimi-k2.6:cloud`: Kimi K2.6 served by Ollama Cloud for benchmark, audit, and meta-analysis dispatch.
- `deepseek_v4_pro_ollama_cloud` -> `deepseek-v4-pro:cloud`: DeepSeek V4 Pro served by Ollama Cloud for benchmark, audit, and meta-analysis dispatch.
- `deepseek_v4_flash_ollama_cloud` -> `deepseek-v4-flash:cloud`: DeepSeek V4 Flash served by Ollama Cloud as a fast mid-tier build comparison model.
- `glm_5_1_ollama_cloud` -> `glm-5.1:cloud`: GLM 5.1 served by Ollama Cloud for long-horizon agentic engineering comparison.
- `qwen3_5_ollama_cloud` -> `qwen3.5:cloud`: Qwen 3.5 served by Ollama Cloud for agentic Python-stack benchmark coverage.
- `nemotron_3_super_ollama_cloud` -> `nemotron-3-super:cloud`: NVIDIA Nemotron 3 Super served by Ollama Cloud for reasoning and coding benchmark coverage.
- `gemma4_ollama_cloud` -> `gemma4:31b-cloud`: Google Gemma 4 31B served by Ollama Cloud for agentic workflow and multimodal benchmark coverage.
- `minimax_m2_7_ollama_cloud` -> `minimax-m2.7:cloud`: MiniMax M2.7 served by Ollama Cloud as a mid-tier Python-stack benchmark model.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| GPT-5.5 xhigh (Codex / ChatGPT) | openai | - | completed | 2414.66 | 2640382 | 3041.46 | yes | 48 | Django + Channels app, tests, README, and container files detected. |
| GPT-5.4 (Codex / ChatGPT) | openai | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| GPT-5.3-Codex (Codex CLI) | openai | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Kimi K2.6 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 1690.56 | 1371230 | 2298.41 | yes | 37 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2294.77 | 3713717 | 3283.89 | yes | 44 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Flash (Ollama Cloud) via Codex | ollama_cloud | - | completed | 4220.03 | 6482866 | 2029.85 | yes | 43 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2132.72 | 2866399 | 2835.52 | yes | 50 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 2739.37 | 2841138 | 1842.17 | yes | 40 | Django + Channels app, tests, README, and container files detected. |
| Nemotron 3 Super (Ollama Cloud) via Codex | ollama_cloud | - | failed | 1448.27 | 0 | - | yes | 34 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| Gemma 4 31B (Ollama Cloud) via Codex | ollama_cloud | - | failed | 1958.75 | 0 | - | yes | 35 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) via Codex | ollama_cloud | - | completed | 5897.59 | 7968933 | 2378.68 | yes | 39 | Django + Channels app, tests, README, and container files detected. |

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

