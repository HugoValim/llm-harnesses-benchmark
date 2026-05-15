# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 + Phase 2 (if variant enables follow-up).

Variants in this config: `claude_sonnet_4_6`, `claude_opus_4_7`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| claude_sonnet_4_6 | not_run | 0s | 0 | 0 | 0 |
| claude_opus_4_7 | completed | 796s | 44 | 90 | 0 |

## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### claude_opus_4_7

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| claude-opus-4-7 | 100 | 38,722 | 6,182,865 | 138,079 |

## Delegation Details
