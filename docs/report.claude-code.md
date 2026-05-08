# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `kimi_k2_6_ollama_cloud`, `qwen3_5_ollama_cloud`, `glm_5_1_ollama_cloud`, `minimax_m2_7_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_cloud | completed | 2375s | 13847 | 100 | 0 |
| qwen3_5_ollama_cloud | completed | 851s | 14837 | 98 | 0 |
| glm_5_1_ollama_cloud | completed | 1680s | 16010 | 127 | 0 |
| minimax_m2_7_ollama_cloud | completed | 917s | 50 | 137 | 0 |
| deepseek_v4_pro_ollama_cloud | completed | 2356s | 84 | 86 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 4,075,415 | 24,672 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 5,075,605 | 23,709 | 0 | 0 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| glm-5.1:cloud | 5,863,711 | 21,222 | 0 | 0 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| minimax-m2.7:cloud | 4,609,430 | 30,410 | 0 | 0 |

### deepseek_v4_pro_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-pro:cloud | 3,181,889 | 26,574 | 0 | 0 |

## Delegation Details
