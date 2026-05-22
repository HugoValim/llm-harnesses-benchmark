# Benchmark Report

Generated at: 2026-05-22T10:39:54+00:00
Prompt SHA256: `824151405541142ace3f163e87515489e06dc71c22349197ae682fbc79ccc634`

## Progress

- `completed`: 4
- `completed_with_errors`: 0
- `failed`: 3
- `timeout`: 0
- `usage_limit_reached`: 0
- `not_run`: 3

## Runner

`opencode run --agent build --format json` (harness `opencode` — runs under `results/opencode-<slug>/`)

- Same opencode runner as the Rails profile - chosen for machine-readable JSON events with session IDs and token counts.
- Models with opencode_id in models.json are auto-included using that ID (typically an OpenRouter path).
- Verification is performed by scripts/analyze_results_runtime.py: discover Django app root, install deps in a venv, boot the ASGI server, headless browser probe, docker build, docker compose.

## Model Selection

- `claude_sonnet_4_6` -> `openrouter/anthropic/claude-sonnet-4.6`: Reference Claude Sonnet model for build, audit, and meta-analysis runs.
- `claude_opus_4_7` -> `openrouter/anthropic/claude-opus-4.7`: Tier-A Claude baseline for build, audit, and meta-analysis runs.
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
| Claude Sonnet 4.6 | anthropic | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Claude Opus 4.7 | anthropic | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Kimi K2.6 (Ollama Cloud) | ollama_cloud | - | completed | 2478.28 | 121514 | 153.85 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Pro (Ollama Cloud) | ollama_cloud | - | completed | 1967.34 | 113956 | 109.09 | yes | 39 | Django + Channels app, tests, README, and container files detected. |
| DeepSeek V4 Flash (Ollama Cloud) | ollama_cloud | - | failed | 2814.56 | 117157 | 82.72 | yes | 36 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| GLM 5.1 (Ollama Cloud) | ollama_cloud | - | completed | 2660.40 | 116264 | 72.86 | yes | 46 | Django + Channels app, tests, README, and container files detected. |
| Qwen 3.5 (Ollama Cloud) | ollama_cloud | - | completed | 2908.27 | 119003 | 79.70 | yes | 36 | Django + Channels app, tests, README, and container files detected. |
| Nemotron 3 Super (Ollama Cloud) | ollama_cloud | - | failed | 2953.86 | 122604 | 41.51 | yes | 35 | Exit code -15. Django + Channels app, tests, README, and container files detected. |
| Gemma 4 31B (Ollama Cloud) | ollama_cloud | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| MiniMax M2.7 (Ollama Cloud) | ollama_cloud | - | failed | 2608.25 | 66353 | 25.44 | partial | 34 | Exit code -15. Some expected benchmark artifacts exist, but the scaffold looks incomplete. |

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

