# Claude Code Benchmark Report — Python (Django + Channels)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`).

Variants: `claude_sonnet_4_6`, `claude_opus_4_7`, `kimi_k2_6_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`, `deepseek_v4_flash_ollama_cloud`, `glm_5_1_ollama_cloud`, `qwen3_5_ollama_cloud`, `nemotron_3_super_ollama_cloud`, `gemma4_ollama_cloud`, `minimax_m2_7_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|
| claude_sonnet_4_6 | not_run | 0s | 0 | 0 | 0 |
| claude_opus_4_7 | completed | 1721s | 47 | 155 | 0 |
| kimi_k2_6_ollama_cloud | completed | 853s | 38 | 130 | 0 |
| deepseek_v4_pro_ollama_cloud | completed | 2296s | 42 | 219 | 0 |
| deepseek_v4_flash_ollama_cloud | completed | 1872s | 44 | 196 | 0 |
| glm_5_1_ollama_cloud | completed | 896s | 47 | 157 | 0 |
| qwen3_5_ollama_cloud | completed | 4570s | 45 | 264 | 0 |
| nemotron_3_super_ollama_cloud | completed | 1098s | 36 | 170 | 0 |
| gemma4_ollama_cloud | completed | 875s | 33 | 102 | 0 |
| minimax_m2_7_ollama_cloud | completed | 4730s | 45 | 282 | 0 |

## Phase Breakdown

### claude_opus_4_7

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1190s | 100 | 46 |
| phase2 | completed | 531s | 55 | 47 |

### kimi_k2_6_ollama_cloud

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 853s | 0 | 38 |

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
| phase1 | completed | 875s | 0 | 33 |

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
| claude-opus-4-7 | 175 | 78,238 | 11,486,182 | 278,120 |

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 5,226,869 | 29,486 | 0 | 0 |

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
| gemma4:31b-cloud | 6,714,909 | 28,165 | 0 | 0 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| minimax-m2.7:cloud | 13,504,117 | 61,234 | 0 | 0 |

## Delegation Details
