# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 only.

Variants in this config: `claude_sonnet_alone`, `kimi_k2_6_ollama_cloud`, `glm_5_1_ollama_cloud`, `qwen3_5_ollama_cloud`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| claude_sonnet_alone | completed | 476s | 20591 | 72 | 0 |
| kimi_k2_6_ollama_cloud | completed | 1462s | 21792 | 167 | 0 |
| glm_5_1_ollama_cloud | completed | 1216s | 19737 | 139 | 0 |
| qwen3_5_ollama_cloud | completed | 973s | 19557 | 105 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### claude_sonnet_alone

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| claude-haiku-4-5-20251001 | 1,167 | 20 | 0 | 0 |
| claude-sonnet-4-6 | 51 | 16,792 | 2,791,768 | 75,367 |

### kimi_k2_6_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| kimi-k2.6:cloud | 10,225,799 | 29,919 | 0 | 0 |

### glm_5_1_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| glm-5.1:cloud | 4,709,656 | 16,373 | 0 | 0 |

### qwen3_5_ollama_cloud

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 6,165,971 | 25,119 | 0 | 0 |

## Delegation Details
