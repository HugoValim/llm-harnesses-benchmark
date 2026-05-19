# Claude Code Benchmark Report — Python (Django + Channels + LangChain)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 + Phase 2 (if variant enables follow-up).

Variants in this config: `claude_sonnet_4_6`, `claude_opus_4_7`

Runner: `claude -p --output-format stream-json --dangerously-skip-permissions`

Each variant writes under `results/claude-<slug>/`.

## Summary

| Variant | Status | Time | Files | Turns | Delegations |
|---|---:|---:|---:|---:|---:|
| claude_sonnet_4_6 | not_run | 0s | 0 | 0 | 0 |
| claude_opus_4_7 | completed | 1721s | 47 | 155 | 0 |

## Phase Breakdown

### claude_opus_4_7

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1190s | 100 | 46 |
| phase2 | completed | 531s | 55 | 47 |


## Per-Model Token Usage

Extracted from Claude Code's `modelUsage` field.

### claude_opus_4_7

| Model | Input | Output | Cache Read | Cache Create |
|---|---:|---:|---:|---:|
| claude-opus-4-7 | 175 | 78,238 | 11,486,182 | 278,120 |

## Delegation Details
