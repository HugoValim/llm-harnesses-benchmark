# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `kimi_k2_6_ollama_cloud`, `qwen3_5_ollama_cloud`, `glm_5_1_ollama_cloud`, `minimax_m2_7_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_cloud | completed | 835s | 16097 | 140 | 0 |
| qwen3_5_ollama_cloud | completed | 1287s | 10553 | 152 | 0 |
| glm_5_1_ollama_cloud | completed | 1165s | 14803 | 121 | 0 |
| minimax_m2_7_ollama_cloud | completed | 538s | 0 | 90 | 0 |
| deepseek_v4_pro_ollama_cloud | completed | 1426s | 13969 | 82 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 5,438,168 | 25,682 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 6,070,328 | 33,182 | 0 | 0 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| glm-5.1:cloud | 5,475,933 | 38,065 | 0 | 0 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| minimax-m2.7:cloud | 3,078,751 | 19,632 | 0 | 0 |

### deepseek_v4_pro_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-pro:cloud | 2,256,261 | 18,528 | 0 | 0 |

## Delegation Details
