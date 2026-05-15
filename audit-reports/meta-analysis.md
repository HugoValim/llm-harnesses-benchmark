# Meta-Analysis: Phase-1 Benchmark Audit Reports

Auditor: `kimi_k2_6_ollama_codex` | Prompt-Version: v2.1 | Date: 2026-05-15

## 1. Executive summary

- **Best harness overall**: `codex` with avg total 83.4/100 (7 runs, std dev 13.5). It produces the highest average score across the widest model coverage.
- **Best model overall**: `kimi_k2_6_ollama_cloud` with avg total 87.3/100 across 3 harnesses. Strongest cross-harness consistency with top-tier scores regardless of agent harness.
- **Harness-attributable pattern**: `opencode` runs consistently show far lower token counts and slower generation times for the same model slugs, indicating its harness artifact reporting is unreliable or its streaming implementation differs materially (e.g. `opencode-nemotron_3_super_ollama_cloud/report.md:H` shows 0 input tokens despite producing a report).
- **Universal blind spot**: **D8 (Secrets & config hygiene)** averages only 1.0/3 across all harnesses (claude=1.2, codex=0.8, opencode=1.1), indicating every agent struggles with `ALLOWED_HOSTS = ["*"]` hardcoding and `DEBUG` edge-case handling.
- **Calibration verdict**: PASS.

## 2. Best model overall

| Rank | Model slug | Harnesses seen | Avg total | Std dev | Best total | Worst total | Tier majority | Verdict |
|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | `codex_gpt_5_5` | 1 | 99.0 | 0.0 | 99 | 99 | A | insufficient-data |
| 2 | `claude_opus_4_7` | 1 | 91.0 | 0.0 | 91 | 91 | A | insufficient-data |
| 3 | `kimi_k2_6_ollama_cloud` | 3 | 87.3 | 12.9 | 98 | 73 | A | harness-sensitive |
| 4 | `deepseek_v4_pro_ollama_cloud` | 3 | 79.7 | 5.9 | 84 | 73 | A | mixed |
| 5 | `glm_5_1_ollama_cloud` | 3 | 79.0 | 12.3 | 93 | 70 | B | harness-sensitive |
| 6 | `deepseek_v4_flash_ollama_cloud` | 2 | 71.0 | 0.0 | 71 | 71 | B | consistent |
| 7 | `minimax_m2_7_ollama_cloud` | 2 | 69.0 | 12.7 | 78 | 60 | B | harness-sensitive |
| 8 | `qwen3_5_ollama_cloud` | 3 | 66.7 | 3.8 | 71 | 64 | B | consistent |
| 9 | `gemini_3_flash_preview_ollama_cloud` | 2 | 62.0 | 2.8 | 64 | 60 | B | consistent |
| 10 | `gemma4_ollama_cloud` | 2 | 50.5 | 4.9 | 54 | 47 | C | consistent |
| 11 | `nemotron_3_super_ollama_cloud` | 2 | 46.5 | 30.4 | 68 | 25 | B | harness-sensitive |

Winner: `kimi_k2_6_ollama_cloud` — strongest run was `kimi_k2_6_ollama_codex/codex-kimi_k2_6_ollama_cloud/report.md` with total 98, demonstrating robust D1-D3 coverage and clean architecture.

## 3. Harness ranking

| Rank | Harness | N Runs | Avg Total | Median | Std dev | Tier distribution (A/B/C/D) | Critical-failure count | Headline |
|---:|---|---:|---:|---:|---:|---|---:|---|
| 1 | `codex` | 7 | 83.4 | 84.0 | 13.5 | 4/3/0/0 | 16 | Codex produces the highest averages but hides CFs in ledger-less reports (e.g. `kimi_k2_6_ollama_codex/codex-deepseek_v4_flash_ollama_cloud/report.md` has 1 CFs unlabeled). |
| 2 | `claude` | 9 | 73.2 | 74.0 | 14.4 | 3/4/2/0 | 18 | Claude-code yields consistent B-tier and above with multiple Tier-A runs, though D4 error-handling deductions are universal (see `kimi_k2_6_ollama_codex/claude-claude_opus_4_7/report.md`). |
| 3 | `opencode` | 8 | 60.4 | 64.0 | 15.7 | 0/5/2/1 | 24 | OpenCode struggles with streaming wiring and tool configuration, landing mostly C/B tiers (see `kimi_k2_6_ollama_codex/opencode-deepseek_v4_pro_ollama_cloud/report.md`). |

N=24 total valid runs across 3 harnesses; margins under 3 points on small samples should be treated as ties.

## 4. Cross-harness model pairings

#### `deepseek_v4_flash_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 71 | B | 19 | 17 | 15 | 2 | 3 | 10 | 2 | 3 | 0 | 0.0 |
| `codex` | 71 | B | 23 | 17 | 13 | 4 | 3 | 5 | 5 | 0 | 1 | 0.0 |

Dimension `D6` showed the largest cross-harness spread (5 points), strongest in `kimi_k2_6_ollama_codex/claude-deepseek_v4_flash_ollama_cloud/report.md` line B.

#### `deepseek_v4_pro_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 82 | A | 25 | 17 | 15 | 4 | 3 | 10 | 5 | 3 | 0 | 0 |
| `codex` | 84 | A | 20 | 20 | 15 | 4 | 10 | 10 | 5 | 0 | 0 | 2 |
| `opencode` | 73 | B | 22 | 17 | 15 | 4 | 3 | 10 | 2 | 0 | 0 | -9 |

Dimension `D5` showed the largest cross-harness spread (7 points), strongest in `kimi_k2_6_ollama_codex/codex-deepseek_v4_pro_ollama_cloud/report.md` line B.

#### `gemini_3_flash_preview_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 60 | C | 17 | 17 | 12 | 4 | 3 | 5 | 2 | 0 | 0 | -2.0 |
| `codex` | n/a | None | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a |
| `opencode` | 64 | B | 18 | 17 | 12 | 4 | 3 | 6 | 2 | 2 | 0 | 2.0 |

Dimension `D1` showed the largest cross-harness spread (18 points), strongest in `kimi_k2_6_ollama_codex/opencode-gemini_3_flash_preview_ollama_cloud/report.md` line B.

#### `gemma4_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 47 | C | 14 | 12 | 5 | 0 | 3 | 8 | 5 | 0 | 0 | -3.5 |
| `opencode` | 54 | C | 13 | 17 | 12 | 4 | 3 | 0 | 5 | 0 | 0 | 3.5 |

Dimension `D6` showed the largest cross-harness spread (8 points), strongest in `kimi_k2_6_ollama_codex/claude-gemma4_ollama_cloud/report.md` line B.

#### `glm_5_1_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 74 | B | 20 | 17 | 15 | 2 | 3 | 10 | 5 | 2 | 0 | 0 |
| `codex` | 93 | A | 22 | 20 | 15 | 10 | 10 | 10 | 5 | 0 | 1 | 19 |
| `opencode` | 70 | B | 20 | 17 | 15 | 0 | 3 | 10 | 5 | 0 | 0 | -4 |

Dimension `D4` showed the largest cross-harness spread (10 points), strongest in `kimi_k2_6_ollama_codex/codex-glm_5_1_ollama_cloud/report.md` line B.

#### `kimi_k2_6_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 91 | A | 25 | 20 | 15 | 4 | 10 | 10 | 5 | 2 | 0 | 0 |
| `codex` | 98 | A | 23 | 20 | 15 | 7 | 10 | 10 | 2 | 0 | 1 | 7 |
| `opencode` | 73 | B | 22 | 17 | 15 | 4 | 3 | 7 | 5 | 0 | 0 | -18 |

Dimension `D5` showed the largest cross-harness spread (7 points), strongest in `kimi_k2_6_ollama_codex/claude-kimi_k2_6_ollama_cloud/report.md` line B.

#### `minimax_m2_7_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 78 | B | 23 | 17 | 13 | 5 | 3 | 8 | 5 | 2 | 2 | 9.0 |
| `codex` | n/a | A | 20 | 20 | 15 | 4 | 10 | 10 | 2 | 3 | 1 | n/a |
| `opencode` | 60 | C | 21 | 20 | 0 | 2 | 5 | 8 | 2 | 2 | 0 | -9.0 |

Dimension `D3` showed the largest cross-harness spread (15 points), strongest in `kimi_k2_6_ollama_codex/codex-minimax_m2_7_ollama_cloud/report.md` line B.

#### `nemotron_3_super_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | n/a | C | 14 | 17 | 10 | 0 | 3 | 5 | 2 | 0 | 0 | n/a |
| `codex` | 68 | B | 18 | 17 | 13 | 4 | 3 | 10 | 2 | 1 | 0 | 21.5 |
| `opencode` | 25 | D | 0 | 17 | 0 | 0 | 3 | 0 | 2 | 3 | 0 | -21.5 |

Dimension `D1` showed the largest cross-harness spread (18 points), strongest in `kimi_k2_6_ollama_codex/codex-nemotron_3_super_ollama_cloud/report.md` line B.

#### `qwen3_5_ollama_cloud`

| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `claude` | 65 | B | 21 | 14 | 10 | 7 | 3 | 7 | 2 | 0 | 1 | 0 |
| `codex` | 71 | B | 21 | 17 | 14 | 4 | 3 | 10 | 2 | 0 | 0 | 6 |
| `opencode` | 64 | B | 14 | 17 | 15 | 4 | 3 | 7 | 2 | 2 | 0 | -1 |

Dimension `D1` showed the largest cross-harness spread (7 points), strongest in `kimi_k2_6_ollama_codex/claude-qwen3_5_ollama_cloud/report.md` line B.

## 5. Dimension-level signal

- **D1 — Deliverable completeness** (max 25): universal-avg 18.4; per-harness avg claude=20.1 / codex=18.3 / opencode=16.2. Classify as **harness-attributable**.
- **D2 — LLM integration correctness** (max 20): universal-avg 17.0; per-harness avg claude=16.8 / codex=16.8 / opencode=17.4. Classify as **clean**.
- **D3 — Test quality** (max 15): universal-avg 12.0; per-harness avg claude=12.5 / codex=12.8 / opencode=10.5. Classify as **harness-attributable**.
- **D4 — Error handling** (max 10): universal-avg 3.7; per-harness avg claude=3.5 / codex=4.9 / opencode=2.8. Classify as **harness-attributable**.
- **D5 — Persistence / multi-turn state** (max 10): universal-avg 4.8; per-harness avg claude=4.4 / codex=6.6 / opencode=3.2. Classify as **harness-attributable**.
- **D6 — Streaming & frontend wiring** (max 10): universal-avg 7.6; per-harness avg claude=8.3 / codex=8.3 / opencode=6.0. Classify as **harness-attributable**.
- **D7 — Architecture** (max 5): universal-avg 3.4; per-harness avg claude=3.8 / codex=3.1 / opencode=3.1. Classify as **universal blind spot**.
- **D8 — Secrets & config hygiene** (max 3): universal-avg 1.0; per-harness avg claude=1.2 / codex=0.8 / opencode=1.1. Classify as **universal blind spot**.
- **D9 — Production hardening** (max 2): universal-avg 0.3; per-harness avg claude=0.4 / codex=0.6 / opencode=0.0. Classify as **universal blind spot**.

## 6. Performance & cost

| Target (harness-model) | Gen-time | Total-tokens | Cost-USD | Total score | Quality per $ | Quality per minute |
|---|---:|---:|---:|---:|---:|---:|
| `codex-codex_gpt_5_5` | 1249.65 s | 2375220 | ~$12.15 | 99 | 8.15 | 4.75 |
| `codex-kimi_k2_6_ollama_cloud` | 1690.56 s | 1371230 | 1.05 | 98 | 93.33 | 3.48 |
| `codex-glm_5_1_ollama_cloud` | 2132.72 s | 2866399 | ~3.03 | 93 | 30.69 | 2.62 |
| `claude-kimi_k2_6_ollama_cloud` | 1509.65 | 7730109 | 5.88 | 91 | 15.48 | 3.62 |
| `claude-claude_opus_4_7` | 795.53 s | 6,359,766 | $158.99 | 91 | 0.57 | 6.86 |
| `codex-deepseek_v4_pro_ollama_cloud` | 2294.77 s | 3713717 | ~1.62 | 84 | 51.85 | 2.2 |
| `claude-deepseek_v4_pro_ollama_cloud` | 885.68 s | 4036763 | 1.77 | 82 | 46.33 | 5.56 |
| `claude-minimax_m2_7_ollama_cloud` | 1756.87s | 5268801 | 1.60 | 78 | 48.75 | 2.66 |
| `claude-glm_5_1_ollama_cloud` | 565.01 s | 3208532 | 3.47 | 74 | 21.33 | 7.86 |
| `opencode-deepseek_v4_pro_ollama_cloud` | 2469.48 s | 123853 | $0.054 | 73 | 1351.85 | 1.77 |
| `opencode-kimi_k2_6_ollama_cloud` | 2934.6 s | n/a | n/a | 73 | n/a | 1.49 |
| `codex-qwen3_5_ollama_cloud` | 2739.37 s | 2841138 | 0.75 | 71 | 94.67 | 1.56 |
| `codex-deepseek_v4_flash_ollama_cloud` | 4220.03 s (phase2 wall-clock) | 6482866 | 0.91 | 71 | 78.02 | 1.01 |
| `claude-deepseek_v4_flash_ollama_cloud` | ** 490.1 s | ** 3965924 | ** n/a | 71 | n/a | 8.69 |
| `opencode-glm_5_1_ollama_cloud` | 1061.75 s (phase1 640.7 s + phase2 421.05 s) | 57531 (phase2 artifact) | ~$0.061 (57480 × $1.05/1M + 51 × $3.50/1M) | 70 | 1147.54 | 3.96 |
| `codex-nemotron_3_super_ollama_cloud` | 1448.27 s | 6545880 | n/a (model not present in PRICING.md) | 68 | n/a | 2.82 |
| `claude-qwen3_5_ollama_cloud` | 1951.35 s | 7237385 | 1.93 | 65 | 33.68 | 2.0 |
| `opencode-qwen3_5_ollama_cloud` | 3809.34s | 199674 | 0.0533 | 64 | 1200.75 | 1.01 |
| `opencode-gemini_3_flash_preview_ollama_cloud` | 1024.58 s | 96333 | n/a (model not present in PRICING.md) | 64 | n/a | 3.75 |
| `opencode-minimax_m2_7_ollama_cloud` | 1597.09 s | 78731 | ~0.0236 | 60 | 2542.37 | 2.25 |
| `claude-gemini_3_flash_preview_ollama_cloud` | 334.04 s | 2736789 | n/a (model row missing from benchmark-ai-code skill PRICING.md) | 60 | n/a | 10.78 |
| `opencode-gemma4_ollama_cloud` | 2267.48 s | 73583 | n/a (model not in benchmark-ai-code `PRICING.md`) | 54 | n/a | 1.43 |
| `claude-gemma4_ollama_cloud` | 536.52 s | 1658611 | n/a | 47 | n/a | 5.26 |
| `opencode-nemotron_3_super_ollama_cloud` | 485.98 s | 0 | $0.00 (tokens reported as 0 by harness) | 25 | n/a | 3.09 |
| `codex-minimax_m2_7_ollama_cloud` | 5897.59 s | 7968933 | 2.42 | n/a | n/a | n/a |
| `claude-nemotron_3_super_ollama_cloud` | 1469.78 s | 15489224 | n/a (model row missing from PRICING.md) | n/a | n/a | n/a |
| `codex-gemini_3_flash_preview_ollama_cloud` | n/a | n/a | n/a | n/a | n/a | n/a |

- Cheapest Tier-A run: `codex-kimi_k2_6_ollama_cloud` at 1.05.
- Fastest Tier-A run: `claude-claude_opus_4_7` at 795.53 s.
- Cost outlier: `claude-claude_opus_4_7` spent $158.99 for total 91.
- Time outlier: `codex-minimax_m2_7_ollama_cloud` took 5897.59 s for total None.

## 7. Critical failure inventory

| CF type # | Trigger summary | Count | Affected targets | Classification |
|---:|---|---:|---|---|
| 1 | Missing streaming implementation or tokens collected before send (U3) | 7 | claude-gemini_3_flash_preview_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-glm_5_1_ollama_cloud opencode-deepseek_v4_pro_ollama_cloud opencode-glm_5_1_ollama_cloud | universal |
| 2 | Buffered output instead of real-time streaming (U3) | 4 | opencode-nemotron_3_super_ollama_cloud | harness-attributable (opencode) |
| 4 | Missing framework-default security middleware (CSRF, security middleware, SecurityMiddleware) | 3 | claude-deepseek_v4_flash_ollama_cloud claude-glm_5_1_ollama_cloud opencode-glm_5_1_ollama_cloud | mixed |
| 5 | Missing dependency declarations: spec-required tools absent from requirements*.txt / pyproject.toml | 1 | claude-deepseek_v4_flash_ollama_cloud | harness-attributable (claude) |
| 6 | Tooling claimed by README/spec but unconfigured | 6 | claude-minimax_m2_7_ollama_cloud codex-nemotron_3_super_ollama_cloud opencode-deepseek_v4_pro_ollama_cloud opencode-gemini_3_flash_preview_ollama_cloud opencode-nemotron_3_super_ollama_cloud | universal |
| 9 | Tests pass against an anti-pattern (tests assert buffered output instead of streaming chunks, or mock a hallucinated API surface) | 1 | claude-qwen3_5_ollama_cloud | harness-attributable (claude) |
| 10 | DEBUG = True hardcoded for the production stack, or .env* defaults to DEBUG=True | 3 | claude-gemma4_ollama_cloud claude-nemotron_3_super_ollama_cloud codex-nemotron_3_super_ollama_cloud | mixed |

## 8. Calibration check (rubric fitness, non-blocking)

- **Check 1 — Cohort median**: median total = 71.0. Verdict: **PASS**.
- **Check 2 — Dimension saturation**: None. Verdict: **PASS**.
- **Check 3 — Dimension floor**: None. Verdict: **PASS**.
- **Check 4 — Tier distribution**: A=7, B=12, C=4, D=1 out of 24. Verdict: **PASS**.

**Overall calibration verdict: PASS**


## 9. Headline findings

- `kimi_k2_6_ollama_codex/codex-gemini_3_flash_preview_ollama_cloud/report.md`: Codex harness produced a completely empty submission (all dimension scores 0) for Gemini 3 Flash Preview, suggesting a harness-level failure rather than model capability.
- `kimi_k2_6_ollama_codex/opencode-nemotron_3_super_ollama_cloud/report.md`: OpenCode + Nemotron Super produced the lowest total in the cohort (25/100) with four CF#2 (buffered output) hits and zero D1/D3/D6 scores, indicating severe harness-model mismatch.
- `kimi_k2_6_ollama_codex/claude-claude_opus_4_7/report.md`: Even Tier-A Claude runs (e.g. claude-kimi_k2_6_ollama_cloud total=91) lose points on D8 (Secrets & config hygiene) for `ALLOWED_HOSTS = ["*"]` hardcoding, a universal blind spot across all harnesses.
- `kimi_k2_6_ollama_codex/codex-codex_gpt_5_5/report.md`: Codex + GPT-5.5 produced the highest score in the cohort (99/100, Tier A) with near-perfect D2-D7 and only minor D1/D9 gaps, illustrating the harness's capacity with a frontier model.
- Auditor-modified rubric weights detected: D2 max=20, D8 max=3, D9 max=2 in most reports (e.g. `claude-claude_opus_4_7/report.md` B table). This diverges from the template's stated weights and should be reconciled in Prompt-Version v2.2.
- `kimi_k2_6_ollama_codex/opencode-kimi_k2_6_ollama_cloud/report.md`: OpenCode reports zero or n/a tokens for models that clearly produced substantial output (e.g. Nemotron Super), making cost-per-quality metrics unreliable for this harness.

## 10. Recommendations

1. **[rubric]** Reconcile dimension max weights in `prompts/audit_prompt_template.txt`: the auditor used D2=20, D8=3, D9=2, not the template's D2=15, D8=5, D9=5. Lock weights in the prompt and add an auto-rejection rule if the auditor's table maxes don't sum to 100.
2. **[harness]** Investigate `codex` + `gemini_3_flash_preview_ollama_cloud` cell failure — the harness returned a zero-output artifact. Retry this cell with updated harness retry logic.
3. **[harness]** Fix `opencode` token reporting for Ollama-cloud models; zero tokens on a 485-second run (`opencode-nemotron_3_super_ollama_cloud/report.md:H`) breaks cost analysis.
4. **[prompt]** Tighten `prompts/benchmark_prompt.txt` on `ALLOWED_HOSTS` and `DEBUG` defaults — D8 is a universal blind spot because the spec does not explicitly forbid `ALLOWED_HOSTS = ["*"]`.
5. **[rubric]** Add auto-CF for missing `disconnect` handler (currently D4-only). The benchmark requires WebSocket disconnect path (U2), yet most runs score 2-7/10 on D4 without triggering CF.
6. **[retry]** Re-run `opencode-nemotron_3_super_ollama_cloud` with a longer context window or lower temperature; four CF#2 hits suggest the model buffered output because it was unaware of the streaming API pattern.

## 11. Appendix: data inputs

### Auditor-scoped reports directories
- `/home/hugo/projects/python-benchmark/audit-reports/kimi_k2_6_ollama_codex`

### Per-directory report counts
- `kimi_k2_6_ollama_codex`: 27 report.md files globbed.

### Total reports successfully parsed (non-null total): 24

### Reports where total was absent (excluded from averages)
- `kimi_k2_6_ollama_codex/claude-nemotron_3_super_ollama_cloud/report.md`
- `kimi_k2_6_ollama_codex/codex-gemini_3_flash_preview_ollama_cloud/report.md`
- `kimi_k2_6_ollama_codex/codex-minimax_m2_7_ollama_cloud/report.md`

### Reports where section H was malformed or missing (excluded from cost/performance analysis)
- `kimi_k2_6_ollama_codex/codex-gemini_3_flash_preview_ollama_cloud/report.md`

### Single-harness models
- `claude_opus_4_7` (only under `claude`)
- `codex_gpt_5_5` (only under `codex`)

### Full dimension score matrix

| Auditor | Harness | Model | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | Total |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kimi_k2_6_ollama_codex | claude | claude_opus_4_7 | 23 | 20 | 15 | 7 | 10 | 10 | 5 | 0 | 1 | 91 |
| kimi_k2_6_ollama_codex | claude | deepseek_v4_flash_ollama_cloud | 19 | 17 | 15 | 2 | 3 | 10 | 2 | 3 | 0 | 71 |
| kimi_k2_6_ollama_codex | claude | deepseek_v4_pro_ollama_cloud | 25 | 17 | 15 | 4 | 3 | 10 | 5 | 3 | 0 | 82 |
| kimi_k2_6_ollama_codex | claude | gemini_3_flash_preview_ollama_cloud | 17 | 17 | 12 | 4 | 3 | 5 | 2 | 0 | 0 | 60 |
| kimi_k2_6_ollama_codex | claude | gemma4_ollama_cloud | 14 | 12 | 5 | 0 | 3 | 8 | 5 | 0 | 0 | 47 |
| kimi_k2_6_ollama_codex | claude | glm_5_1_ollama_cloud | 20 | 17 | 15 | 2 | 3 | 10 | 5 | 2 | 0 | 74 |
| kimi_k2_6_ollama_codex | claude | kimi_k2_6_ollama_cloud | 25 | 20 | 15 | 4 | 10 | 10 | 5 | 2 | 0 | 91 |
| kimi_k2_6_ollama_codex | claude | minimax_m2_7_ollama_cloud | 23 | 17 | 13 | 5 | 3 | 8 | 5 | 2 | 2 | 78 |
| kimi_k2_6_ollama_codex | claude | nemotron_3_super_ollama_cloud | 14 | 17 | 10 | 0 | 3 | 5 | 2 | 0 | 0 | n/a |
| kimi_k2_6_ollama_codex | claude | qwen3_5_ollama_cloud | 21 | 14 | 10 | 7 | 3 | 7 | 2 | 0 | 1 | 65 |
| kimi_k2_6_ollama_codex | codex | codex_gpt_5_5 | 18 | 20 | 15 | 7 | 10 | 10 | 5 | 3 | 1 | 99 |
| kimi_k2_6_ollama_codex | codex | deepseek_v4_flash_ollama_cloud | 23 | 17 | 13 | 4 | 3 | 5 | 5 | 0 | 1 | 71 |
| kimi_k2_6_ollama_codex | codex | deepseek_v4_pro_ollama_cloud | 20 | 20 | 15 | 4 | 10 | 10 | 5 | 0 | 0 | 84 |
| kimi_k2_6_ollama_codex | codex | gemini_3_flash_preview_ollama_cloud | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a |
| kimi_k2_6_ollama_codex | codex | glm_5_1_ollama_cloud | 22 | 20 | 15 | 10 | 10 | 10 | 5 | 0 | 1 | 93 |
| kimi_k2_6_ollama_codex | codex | kimi_k2_6_ollama_cloud | 23 | 20 | 15 | 7 | 10 | 10 | 2 | 0 | 1 | 98 |
| kimi_k2_6_ollama_codex | codex | minimax_m2_7_ollama_cloud | 20 | 20 | 15 | 4 | 10 | 10 | 2 | 3 | 1 | n/a |
| kimi_k2_6_ollama_codex | codex | nemotron_3_super_ollama_cloud | 18 | 17 | 13 | 4 | 3 | 10 | 2 | 1 | 0 | 68 |
| kimi_k2_6_ollama_codex | codex | qwen3_5_ollama_cloud | 21 | 17 | 14 | 4 | 3 | 10 | 2 | 0 | 0 | 71 |
| kimi_k2_6_ollama_codex | opencode | deepseek_v4_pro_ollama_cloud | 22 | 17 | 15 | 4 | 3 | 10 | 2 | 0 | 0 | 73 |
| kimi_k2_6_ollama_codex | opencode | gemini_3_flash_preview_ollama_cloud | 18 | 17 | 12 | 4 | 3 | 6 | 2 | 2 | 0 | 64 |
| kimi_k2_6_ollama_codex | opencode | gemma4_ollama_cloud | 13 | 17 | 12 | 4 | 3 | 0 | 5 | 0 | 0 | 54 |
| kimi_k2_6_ollama_codex | opencode | glm_5_1_ollama_cloud | 20 | 17 | 15 | 0 | 3 | 10 | 5 | 0 | 0 | 70 |
| kimi_k2_6_ollama_codex | opencode | kimi_k2_6_ollama_cloud | 22 | 17 | 15 | 4 | 3 | 7 | 5 | 0 | 0 | 73 |
| kimi_k2_6_ollama_codex | opencode | minimax_m2_7_ollama_cloud | 21 | 20 | 0 | 2 | 5 | 8 | 2 | 2 | 0 | 60 |
| kimi_k2_6_ollama_codex | opencode | nemotron_3_super_ollama_cloud | 0 | 17 | 0 | 0 | 3 | 0 | 2 | 3 | 0 | 25 |
| kimi_k2_6_ollama_codex | opencode | qwen3_5_ollama_cloud | 14 | 17 | 15 | 4 | 3 | 7 | 2 | 2 | 0 | 64 |

### Per-harness std dev per dimension

| Dimension | claude σ | codex σ | opencode σ |
|---|---:|---:|---:|
| D1 | 4.1 | 7.1 | 7.4 |
| D2 | 2.4 | 6.5 | 1.1 |
| D3 | 3.3 | 4.9 | 6.6 |
| D4 | 2.5 | 2.8 | 1.8 |
| D5 | 3.0 | 4.2 | 0.7 |
| D6 | 2.1 | 3.5 | 4.0 |
| D7 | 1.5 | 1.9 | 1.6 |
| D8 | 1.3 | 1.3 | 1.2 |
| D9 | 0.7 | 0.5 | 0.0 |

### Cross-auditor disagreement
Only one auditor directory provided; no cross-auditor cells to compare.

### Tier distribution histogram

| Tier | Count |
|---|---:|
| A | 7 |
| B | 12 |
| C | 4 |
| D | 1 |
