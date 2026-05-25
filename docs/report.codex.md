# Benchmark Report

Generated at: 2026-05-25T13:03:46+00:00
Prompt SHA256: `824151405541142ace3f163e87515489e06dc71c22349197ae682fbc79ccc634`

## Progress

- `completed`: 9
- `completed_with_errors`: 0
- `failed`: 0
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
| Kimi K2.6 (Ollama Cloud) | ollama_cloud | - | completed | 2554.92 | 3453514 | 2214.42 | yes | 45 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) | ollama_cloud | - | completed | 2966.99 | 6970760 | 3964.67 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Flash (Ollama Cloud) | ollama_cloud | - | completed | 3206.34 | 3501712 | 2623.67 | yes | 9883 | Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) | ollama_cloud | - | completed | 2455.57 | 4936401 | 4113.50 | yes | 42 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) | ollama_cloud | - | completed | 3079.75 | 4000424 | 2193.54 | yes | 42 | Django + Channels app, tests, README, and container files detected. |
| Nemotron 3 Super (Ollama Cloud) | ollama_cloud | - | completed | 2021.98 | 5277114 | 7158.71 | yes | 38 | Django + Channels app, tests, README, and container files detected. |
| Gemma 4 31B (Ollama Cloud) | ollama_cloud | - | completed | 1114.27 | 7268667 | 8469.67 | yes | 36 | Django + Channels app, tests, README, and container files detected. |
| MiniMax M2.7 (Ollama Cloud) | ollama_cloud | - | completed | 762.42 | 1340693 | 2583.72 | yes | 48 | Django + Channels app, tests, README, and container files detected. |

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

