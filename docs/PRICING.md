Last-Updated: 2026-06-01

Sources:
- https://openrouter.ai/ (model pages, snapshot 2026-05-25)
- https://openai.com/api/pricing (accessed 2026-05-25)
- https://api-docs.deepseek.com/quick_start/pricing (accessed 2026-05-25)
- https://cursor.com/changelog/composer-2-5 (accessed 2026-05-25)
- https://cursor.com/docs/account/teams/pricing (accessed 2026-05-25)
- https://ollama.com/pricing (accessed 2026-05-25)

# Benchmark pricing snapshot (USD per 1M tokens)

This file is the **source of truth** for `Estimated-Cost-USD` in audit reports. Costs are computed in Python during the audit step (`scripts/run_audit.py` → `generation-metrics.json`); auditors copy precomputed values into section H.

## Rules

- **Units**: all prices are **USD per 1M tokens**. Empty cache columns mean “use input rate for cache read tokens” when the harness reports cache usage.
- **Cost formula**:

  ```text
  cost_usd = (input_tokens       / 1_000_000) * input_price_per_million
           + (output_tokens      / 1_000_000) * output_price_per_million
           + (cache_read_tokens  / 1_000_000) * cache_read_price_per_million  # or input rate if blank
           + (cache_write_tokens / 1_000_000) * cache_write_price_per_million # or input rate if blank
  ```

- **Channel selection** (which row to use for a benchmark target):
  - `opencode` harness → `openrouter`
  - `claude` harness + `anthropic` provider → `native`
  - `codex` harness + `openai` provider → `native`
  - `cursor` harness → `cursor_list`
  - `ollama_cloud` provider (any harness) → `ollama_cloud`
- **Ollama Cloud proxy**: `*:cloud` models bill by GPU-time on subscription plans, not published $/token. Rows below use **proxy API rates** (OpenRouter / provider list) for cross-model comparison only.
- **DeepSeek V4 Pro promo** ends **2026-05-31 15:59 UTC** — table uses promo rates; after that date update `deepseek_v4_pro_ollama_cloud` to **1.74 / 3.48** (cache miss).
- **GPT-5.x long context**: OpenAI applies surcharges when input exceeds 272K tokens; default table uses standard (<272K) rates.
- **Cursor Composer**: Pro ($20/mo) includes a Composer usage pool — marginal wallet cost may be **$0** until included usage is consumed. Audit math uses **list API** $/M (team on-demand basis) for comparability.
- **Composer Fast tier** (IDE default): $3.00 in / $15.00 out — not used unless benchmark logs indicate fast tier.
- **Missing model row (blocking)**: add a row with source URL + snapshot date before publishing audit comparisons.

## Price table

| Slug | Provider | Model ID | Channel | Input $/1M | Output $/1M | Cache read $/1M | Cache write $/1M | Billable | Source | Snapshot |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| claude_sonnet_4_6 | anthropic | claude-sonnet-4-6 | native | 3.00 | 15.00 | | | yes | openrouter.ai/anthropic/claude-sonnet-4.6 | 2026-05-25 |
| claude_sonnet_4_6 | anthropic | openrouter/anthropic/claude-sonnet-4.6 | openrouter | 3.00 | 15.00 | | | yes | openrouter.ai/anthropic/claude-sonnet-4.6 | 2026-05-25 |
| claude_opus_4_7 | anthropic | claude-opus-4-7 | native | 5.00 | 25.00 | | | yes | openrouter.ai/anthropic/claude-opus-4.7 | 2026-05-25 |
| claude_opus_4_7 | anthropic | openrouter/anthropic/claude-opus-4.7 | openrouter | 5.00 | 25.00 | | | yes | openrouter.ai/anthropic/claude-opus-4.7 | 2026-05-25 |
| codex_gpt_5_5 | openai | gpt-5.5 | native | 5.00 | 30.00 | 0.50 | | yes | openai.com/api/pricing | 2026-05-25 |
| codex_gpt_5_4 | openai | gpt-5.4 | native | 2.50 | 15.00 | 0.25 | | yes | openai.com/api/pricing | 2026-05-25 |
| codex_gpt_5_3_codex | openai | gpt-5.3-codex | native | 1.75 | 14.00 | | | yes | openai.com/api/pricing | 2026-05-25 |
| composer_2_5 | cursor | composer-2.5 | cursor_list | 0.50 | 2.50 | 0.20 | | yes | cursor.com/changelog/composer-2-5 | 2026-05-25 |
| composer_2_0 | cursor | composer-2 | cursor_list | 0.50 | 2.50 | 0.20 | | yes | cursor.com/docs/account/teams/pricing | 2026-05-25 |
| kimi_k2_6 | ollama_cloud | kimi-k2.6:cloud | ollama_cloud | 0.73 | 3.49 | 0.25 | | yes | openrouter.ai/moonshotai/kimi-k2.6 (proxy) | 2026-05-25 |
| deepseek_v4_pro | ollama_cloud | deepseek-v4-pro:cloud | ollama_cloud | 0.435 | 0.87 | 0.003625 | | yes | api-docs.deepseek.com (promo until 2026-05-31) | 2026-05-25 |
| glm_5_1 | ollama_cloud | glm-5.1:cloud | ollama_cloud | 1.05 | 3.50 | | | yes | openrouter.ai/z-ai/glm-5.1 (proxy) | 2026-05-25 |
| qwen3_5 | ollama_cloud | qwen3.5:cloud | ollama_cloud | 0.26 | 1.56 | | | yes | openrouter.ai/qwen/qwen3.5-plus-02-15 (proxy) | 2026-05-25 |
| nemotron_3_super | ollama_cloud | nemotron-3-super:cloud | ollama_cloud | 0.09 | 0.45 | | | yes | pricepertoken.com/nemotron-3-super (proxy) | 2026-05-25 |
| gemma4 | ollama_cloud | gemma4:31b-cloud | ollama_cloud | 0.00 | 0.00 | | | yes | openrouter.ai free Gemma 4 31B tier (proxy) | 2026-05-25 |
| minimax_m3 | ollama_cloud | minimax-m3:cloud | ollama_cloud | 0.30 | 1.20 | | | yes | openrouter.ai/minimax/minimax-m3 (proxy) | 2026-06-01 |

## Subscription appendix (reference only)

| Plan | $/month | Notes |
| --- | ---: | --- |
| Cursor Pro | 20 | Includes agent usage credit; Composer list API still used for audit $/token |
| Cursor Pro+ | 60 | Higher included usage |
| Ollama Cloud Pro | 20 | GPU-time billing, not per-token |
| Ollama Cloud Max | 100 | 5× Pro usage |
| Claude Pro | 20 | Subscription auth for Claude Code harness |

## Maintenance

Before large audit batches:

```bash
python scripts/fetch_openrouter_pricing.py --check
python scripts/validate_pricing.py
```
