# Benchmark Report

Generated at: 2026-05-09T05:11:51+00:00
Prompt SHA256: `b5d9e80245fd8603224b59d6cdd6356a5c3907a002137532c27b390cd53de69d`

## Progress

- `completed`: 0
- `completed_with_errors`: 0
- `failed`: 0
- `timeout`: 0
- `not_run`: 7

## Runner

`opencode run --agent build --format json` (harness `opencode` — runs under `results/opencode-<slug>/`)

- Same opencode runner as the Rails profile — chosen for machine-readable JSON events with session IDs and token counts.
- The Python profile uses prompts/benchmark_prompt_python.txt and prompts/benchmark_followup_prompt_python.txt.
- Verification is performed by scripts/analyze_results_runtime_python.py: discover Django app root, install deps in a venv, boot the ASGI server, headless browser probe, docker build, docker compose.

## Model Selection

- `claude_sonnet_4_6` -> `openrouter/anthropic/claude-sonnet-4.6`: Anthropic Claude Sonnet 4.6 on OpenRouter. The reference model the Python brief asks the build to wire into LangChain — running it as a benchmark target tests whether Sonnet itself can produce a working Django + Channels + LangChain app that calls Sonnet via OpenRouter.
- `claude_opus_4_7` -> `openrouter/anthropic/claude-opus-4.7`: Anthropic Claude Opus 4.7 on OpenRouter. Tier-A baseline for the Python profile — measures whether Opus's stronger planning translates to fewer LangChain API hallucinations and a cleaner ASGI/Channels wiring than mid-tier models.
- `kimi_k2_6` -> `openrouter/moonshotai/kimi-k2.6`: Moonshot Kimi K2.6 via OpenRouter. In the Rails profile K2.6 hit Tier 3 by hallucinating RubyLLM's fluent API — the Python equivalent test is whether it hallucinates LangChain APIs (deprecated LLMChain, wrong import paths like langchain.chat_models vs langchain_anthropic, fabricated streaming hooks).
- `deepseek_v4_pro` -> `openrouter/deepseek/deepseek-v4-pro`: DeepSeek V4 Pro via OpenRouter. Phase 2 follow-up is disabled because opencode's ai-sdk strips reasoning_content but the DeepSeek API requires it echoed back, breaking multi-turn at turn 2. Phase 1 still runs end-to-end; the Python runtime analyzer (analyze_results_runtime_python.py) provides the boot/docker validation that phase 2 would otherwise do. reasoning=false tells opencode to treat it as a non-reasoning model so it does not extract/pass back reasoning_content.
- `minimax_m2_7` -> `openrouter/minimax/minimax-m2.7`: MiniMax M2.7 via OpenRouter. Mid-tier model whose Python-stack knowledge is largely unmeasured in this harness — establishes whether MiniMax can wire LangChain + Channels correctly or hits the same fluent-DSL hallucinations seen in Rails brief Tier 2/3 outcomes.
- `qwen3_5_35b` -> `openrouter/qwen/qwen3.5-35b-a3b`: Qwen 3.5 35B A3B via OpenRouter. Agentic reasoning model with strong coding benchmarks — tests whether Qwen's tool-use reasoning carries through to correct LangChain wiring (ChatAnthropic vs ChatOpenAI, anthropic-compat endpoint, streaming hooks) on the Django + Channels brief.
- `glm_5_1` -> `openrouter/z-ai/glm-5.1`: GLM 5.1 via OpenRouter. Long-horizon agentic engineering model — tests whether GLM's sustained multi-turn iteration produces a complete Django + Channels + LangChain app and whether it avoids LangChain API hallucinations.

## Results

| Model | Provider | Warmup ctx | Status | Elapsed (s) | Total tokens | Tok/s | Works? | Files | Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |
| Claude Sonnet 4.6 | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Claude Opus 4.7 | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Kimi K2.6 | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| DeepSeek V4 Pro | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| MiniMax M2.7 | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| Qwen 3.5 35B A3B | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |
| GLM 5.1 | openrouter | - | not_run | - | - | - | n/a | 0 | Run has not been executed yet. |

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

