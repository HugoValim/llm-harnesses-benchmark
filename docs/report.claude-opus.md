# Claude Code Benchmark Report — Python (Django + Channels)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`).

Variants: `claude_sonnet_4_6`, `claude_opus_4_7`, `kimi_k2_6_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`, `deepseek_v4_flash_ollama_cloud`, `glm_5_1_ollama_cloud`, `qwen3_5_ollama_cloud`, `nemotron_3_super_ollama_cloud`, `gemma4_ollama_cloud`, `minimax_m2_7_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|
| claude_sonnet_4_6 | not_run | 0s | 0 | 0 | 0 |
| claude_opus_4_7 | completed | 2340s | 50 | 160 | 0 |
| kimi_k2_6_ollama_cloud | completed | 2012s | 36 | 194 | 0 |
| deepseek_v4_pro_ollama_cloud | completed | 2296s | 42 | 219 | 0 |
| deepseek_v4_flash_ollama_cloud | completed | 1872s | 44 | 196 | 0 |
| glm_5_1_ollama_cloud | completed | 896s | 47 | 157 | 0 |
| qwen3_5_ollama_cloud | completed | 4570s | 45 | 264 | 0 |
| nemotron_3_super_ollama_cloud | completed | 1098s | 36 | 170 | 0 |
| gemma4_ollama_cloud | completed | 3265s | 38 | 174 | 0 |
| minimax_m2_7_ollama_cloud | completed | 4730s | 45 | 282 | 0 |

## Phase Breakdown

### claude_opus_4_7

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1593s | 95 | 49 |
| phase2 | completed | 747s | 65 | 50 |

### kimi_k2_6_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1066s | 108 | 36 |
| phase2 | completed | 946s | 86 | 36 |

### deepseek_v4_pro_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1568s | 120 | 41 |
| phase2 | completed | 728s | 99 | 42 |

### deepseek_v4_flash_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 871s | 117 | 44 |
| phase2 | completed | 1000s | 79 | 44 |

### glm_5_1_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 391s | 82 | 47 |
| phase2 | completed | 505s | 75 | 47 |

### qwen3_5_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1554s | 126 | 42 |
| phase2 | completed | 3015s | 138 | 45 |

### nemotron_3_super_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1065s | 159 | 36 |
| phase2 | completed | 33s | 11 | 36 |

### gemma4_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1537s | 113 | 35 |
| phase2 | completed | 1728s | 61 | 38 |

### minimax_m2_7_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1639s | 166 | 44 |
| phase2 | completed | 3091s | 116 | 45 |


## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### claude_opus_4_7

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| claude-haiku-4-5-20251001 | 3,522 | 40 | 0 | 0 |
| claude-opus-4-7 | 241 | 99,684 | 9,084,496 | 246,681 |

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 6,227,463 | 36,596 | 0 | 0 |

### deepseek_v4_pro_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-pro:cloud | 8,210,384 | 51,867 | 0 | 0 |

### deepseek_v4_flash_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-flash:cloud | 7,532,586 | 45,584 | 0 | 0 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| glm-5.1:cloud | 6,205,652 | 27,078 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 19,672,304 | 60,221 | 0 | 0 |

### nemotron_3_super_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| nemotron-3-super:cloud | 10,877,348 | 28,689 | 0 | 0 |

### gemma4_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| gemma4:31b-cloud | 11,739,274 | 51,081 | 0 | 0 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| minimax-m2.7:cloud | 13,504,117 | 61,234 | 0 | 0 |

## Delegation Details
