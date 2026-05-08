# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `kimi_k2_6_ollama_cloud`, `qwen3_5_ollama_cloud`, `glm_5_1_ollama_cloud`, `minimax_m2_7_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

## Summary

| Variant | Status | Time | Files | Turns | Delegations | Total Cost |
|---|---|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_cloud | completed | 1462s | 21792 | 167 | 0 | $51.8770 |
| qwen3_5_ollama_cloud | completed | 973s | 19557 | 105 | 0 | $31.4578 |
| glm_5_1_ollama_cloud | completed | 1216s | 19737 | 139 | 0 | $23.9576 |
| minimax_m2_7_ollama_cloud | completed | 1631s | 2454 | 135 | 0 | $27.7340 |
| deepseek_v4_pro_ollama_cloud | completed | 1514s | 19293 | 111 | 0 | $23.3644 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field. Cost is computed server-side by the SDK.

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create | Cost |
|---|---:|---:|---:|---:|---:|
| kimi-k2.6:cloud | 10,225,799 | 29,919 | 0 | 0 | $51.8770 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create | Cost |
|---|---:|---:|---:|---:|---:|
| qwen3.5:cloud | 6,165,971 | 25,119 | 0 | 0 | $31.4578 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create | Cost |
|---|---:|---:|---:|---:|---:|
| glm-5.1:cloud | 4,709,656 | 16,373 | 0 | 0 | $23.9576 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create | Cost |
|---|---:|---:|---:|---:|---:|
| minimax-m2.7:cloud | 5,422,209 | 24,920 | 0 | 0 | $27.7340 |

### deepseek_v4_pro_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create | Cost |
|---|---:|---:|---:|---:|---:|
| deepseek-v4-pro:cloud | 4,533,292 | 27,916 | 0 | 0 | $23.3644 |

## Delegation Details
