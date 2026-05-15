# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `kimi_k2_6_ollama_cloud`, `qwen3_5_ollama_cloud`, `glm_5_1_ollama_cloud`, `minimax_m2_7_ollama_cloud`, `deepseek_v4_pro_ollama_cloud`, `deepseek_v4_flash_ollama_cloud`, `gemma4_ollama_cloud`, `nemotron_3_super_ollama_cloud`, `gemini_3_flash_preview_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_cloud | completed | 1510s | 38 | 137 | 0 |
| qwen3_5_ollama_cloud | completed | 1951s | 10637 | 123 | 0 |
| glm_5_1_ollama_cloud | completed | 565s | 44 | 99 | 0 |
| minimax_m2_7_ollama_cloud | completed | 1757s | 40 | 130 | 0 |
| deepseek_v4_pro_ollama_cloud | completed | 886s | 42 | 113 | 0 |
| deepseek_v4_flash_ollama_cloud | completed | 490s | 39 | 101 | 0 |
| gemma4_ollama_cloud | completed | 537s | 32 | 48 | 0 |
| nemotron_3_super_ollama_cloud | completed | 1470s | 36 | 182 | 0 |
| gemini_3_flash_preview_ollama_cloud | completed | 334s | 32 | 51 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 7,700,887 | 29,222 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 7,204,426 | 34,986 | 0 | 0 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| glm-5.1:cloud | 3,166,302 | 42,230 | 0 | 0 |

### minimax_m2_7_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| minimax-m2.7:cloud | 5,239,693 | 29,108 | 0 | 0 |

### deepseek_v4_pro_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-pro:cloud | 4,011,471 | 25,292 | 0 | 0 |

### deepseek_v4_flash_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| deepseek-v4-flash:cloud | 3,940,847 | 25,077 | 0 | 0 |

### gemma4_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| gemma4:31b-cloud | 1,647,474 | 10,137 | 0 | 0 |

### nemotron_3_super_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| nemotron-3-super:cloud | 15,441,655 | 47,569 | 0 | 0 |

### gemini_3_flash_preview_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| gemini-3-flash-preview:cloud | 2,722,762 | 14,027 | 0 | 0 |

## Delegation Details
