# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `kimi_k2_6_ollama_cloud`, `qwen3_5_ollama_cloud`, `glm_5_1_ollama_cloud`, `minimax_m2_7_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`, `deepseek_v4_flash_ollama_cloud`, `gemma4_ollama_cloud`, `nemotron_3_super_ollama_cloud`, `gemini_3_flash_preview_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_cloud | completed | 1318s | 35 | 97 | 0 |
| qwen3_5_ollama_cloud | completed | 658s | 41 | 102 | 0 |
| glm_5_1_ollama_cloud | failed | 197s | 2 | 1 | 0 |
| minimax_m2_7_ollama_cloud | failed | 199s | 2 | 1 | 0 |
| deepseek_v4_pro_ollama_cloud | failed | 196s | 2 | 1 | 0 |
| deepseek_v4_flash_ollama_cloud | failed | 187s | 2 | 1 | 0 |
| gemma4_ollama_cloud | failed | 196s | 2 | 1 | 0 |
| nemotron_3_super_ollama_cloud | failed | 197s | 2 | 1 | 0 |
| gemini_3_flash_preview_ollama_cloud | failed | 192s | 2 | 1 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 3,213,938 | 18,494 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 3,705,192 | 14,391 | 0 | 0 |

## Delegation Details
