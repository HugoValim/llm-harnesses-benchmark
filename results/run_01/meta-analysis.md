# Meta-analysis: codex_gpt_5_5(xhigh) audit reports

## 1. Executive summary

- **Best harness overall**: `codex` — 61.1/100 avg (N=8, std dev 17.7). Runners-up: opencode 60.0, claude 59.0. *Statistical tie* (margin ≤3 on N≤8).
- **Best model overall**: `codex_gpt_5_5(xhigh)` — 86.0/100 under `codex` (top contest-harness run; single-harness anchor — not on the shared Ollama grid).
- **Best open-source model overall**: `deepseek_v4_pro_ollama_cloud` — 74.0/100 cross-harness avg across 3 contest harnesses (std dev 2.6; best on the shared Ollama Cloud grid).
- **Cursor agent runs**: N=2, avg 81.5 — model-only benchmarks; excluded from harness contest.
- **Universal blind spot candidate**: D9 Production hardening — claude 1.2 / codex 0.0 / opencode 0.1 on a 10-point dimension.
- **Harness-attributable pattern**: opencode leads on D8 secrets/config vs claude/codex; claude uniquely owns CF#12 raw-WebSocket substitutions (see sections 5 and 7).
- **Calibration**: **FAIL** — D9 floors out; median D10 is 8.0 despite common production/security gaps (section 8).

## 2. Best model overall
| Rank | Harness | Model slug | Total | Tier |
|---:|---|---|---:|---|
| 1 | codex | codex_gpt_5_5(xhigh) | 86.0 | A |
| 2 | cursor | composer_2_5 | 83.0 | A |
| 3 | claude | claude_opus_4_7 | 82.0 | A |
| 4 | cursor | composer_2_0 | 80.0 | B |
| 5 | claude | kimi_k2_6_ollama_cloud | 78.0 | B |
| 6 | codex | deepseek_v4_pro_ollama_cloud | 76.0 | B |
| 7 | opencode | glm_5_1_ollama_cloud | 76.0 | B |
| 8 | opencode | deepseek_v4_pro_ollama_cloud | 75.0 | B |
| 9 | codex | deepseek_v4_flash_ollama_cloud | 74.0 | B |
| 10 | codex | glm_5_1_ollama_cloud | 73.0 | B |
| 11 | claude | deepseek_v4_pro_ollama_cloud | 71.0 | B |
| 12 | codex | kimi_k2_6_ollama_cloud | 70.0 | B |
| 13 | codex | qwen3_5_ollama_cloud | 68.0 | B |
| 14 | opencode | deepseek_v4_flash_ollama_cloud | 68.0 | B |
| 15 | claude | glm_5_1_ollama_cloud | 63.0 | B |
| 16 | claude | qwen3_5_ollama_cloud | 63.0 | B |
| 17 | opencode | qwen3_5_ollama_cloud | 59.0 | C |
| 18 | claude | gemma4_ollama_cloud | 58.0 | C |
| 19 | codex | minimax_m2_7_ollama_cloud | 58.0 | C |
| 20 | claude | minimax_m2_7_ollama_cloud | 57.0 | C |
| 21 | opencode | kimi_k2_6_ollama_cloud | 54.0 | C |
| 22 | opencode | minimax_m2_7_ollama_cloud | 54.0 | C |
| 23 | claude | deepseek_v4_flash_ollama_cloud | 53.0 | C |
| 24 | opencode | gemma4_ollama_cloud | 53.0 | C |
| 25 | codex | gemma4_ollama_cloud | 44.0 | C |
| 26 | opencode | nemotron_3_super_ollama_cloud | 41.0 | C |
| 27 | claude | nemotron_3_super_ollama_cloud | 29.0 | D |
| 28 | codex | nemotron_3_super_ollama_cloud | 26.0 | D |

Winner: `deepseek_v4_pro_ollama_cloud` (cross-harness avg 74.0/100); its codex run shows full deliverables and test coverage while keeping the best model-family total at 76/100 (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:8`; `audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:10`). Single-contest-harness leaders (`codex_gpt_5_5(xhigh)`, `claude_opus_4_7`) and cursor-only Composer runs (`composer_2_5`, `composer_2_0`) top the run table but are not crowned.

## 2a. Open-source (Ollama) model ranking

| Rank | Model slug | N harnesses | Avg total | Std dev | Tier | Claude | Codex | Opencode |
|---:|---|---:|---:|---:|---|---:|---:|---:|
| 1 | deepseek_v4_pro_ollama_cloud | 3 | 74.0 | 2.6 | B | 71.0 | 76.0 | 75.0 |
| 2 | glm_5_1_ollama_cloud | 3 | 70.7 | 6.8 | B | 63.0 | 73.0 | 76.0 |
| 3 | kimi_k2_6_ollama_cloud | 3 | 67.3 | 12.2 | B | 78.0 | 70.0 | 54.0 |
| 4 | deepseek_v4_flash_ollama_cloud | 3 | 65.0 | 10.8 | B | 53.0 | 74.0 | 68.0 |
| 5 | qwen3_5_ollama_cloud | 3 | 63.3 | 4.5 | B | 63.0 | 68.0 | 59.0 |
| 6 | minimax_m2_7_ollama_cloud | 3 | 56.3 | 2.1 | C | 57.0 | 58.0 | 54.0 |
| 7 | gemma4_ollama_cloud | 3 | 51.7 | 7.1 | C | 58.0 | 44.0 | 53.0 |
| 8 | nemotron_3_super_ollama_cloud | 3 | 32.0 | 7.9 | D | 29.0 | 26.0 | 41.0 |

Winner: `deepseek_v4_pro_ollama_cloud` (74.0/100 cross-harness mean); the codex harness run at 76/100 shows the strongest single-cell score with full deliverables and test coverage (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:8`).

## 3. Harness ranking
| Rank | Harness | N Runs | Avg Total | Median | Std dev | Tier distribution (A/B/C/D) | Critical-failure count | Headline (report:line) |
|---:|---|---:|---:|---:|---:|---|---:|---|
| 1 | codex | 8 | 61.1 | 69.0 | 17.7 | 0/5/2/1 | 22 | Best on the shared Ollama grid; strong deliverables on deepseek_v4_pro but production hardening still absent (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:10`). |
| 2 | opencode | 8 | 60.0 | 56.5 | 12.1 | 0/3/5/0 | 26 | Cost-efficient Ollama runs can score high, but false-green/test-tooling gaps recur (`audit-reports/codex_gpt_5_5/opencode-deepseek_v4_flash_ollama_cloud/report.md:34`). |
| 3 | claude | 8 | 59.0 | 60.5 | 14.5 | 0/4/3/1 | 31 | Core LLM work is often solid, but secrets and lifecycle failures recur (`audit-reports/codex_gpt_5_5/claude-deepseek_v4_pro_ollama_cloud/report.md:28`). |

**Cursor agent models (excluded from harness contest):** `composer_2_5` (83/100) and `composer_2_0` (80/100) under the `cursor-` prefix — N=2, cohort avg 81.5. Strong D6/D8/D10 on both runs; D9 still zero (`audit-reports/codex_gpt_5_5/cursor-composer_2_5/report.md:12`). Not comparable to the opencode/codex/claude grid without cross-agent pairing.

**Single-harness leaders (excluded from harness averages):** `codex_gpt_5_5(xhigh)` (86/100 under codex) and `claude_opus_4_7` (82/100 under claude) — listed in section 2 but omitted from the cross-harness cohort above.

Sample-size caveat: N=8 per contest harness on the shared Ollama grid; margins under ~3 points among codex/opencode/claude are ties on this sample.

## 4. Cross-harness model pairings
### `deepseek_v4_flash_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 53 | C | 10 | 10 | 3 | 4 | 5 | 6 | 8 | 0 | 0 | 7 | -15.0 |
| codex | 74 | B | 15 | 10 | 10 | 10 | 5 | 7 | 8 | 0 | 0 | 9 | +6.0 |
| opencode | 68 | B | 7 | 9 | 8 | 10 | 5 | 8 | 8 | 5 | 0 | 8 | +0.0 |

D1 moved most: codex kept full deliverables while opencode lost reproducible dev deps (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_flash_ollama_cloud/report.md:9`; `audit-reports/codex_gpt_5_5/opencode-deepseek_v4_flash_ollama_cloud/report.md:7`).

### `deepseek_v4_pro_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 71 | B | 12 | 10 | 10 | 7 | 5 | 10 | 9 | 0 | 0 | 8 | -4.0 |
| codex | 76 | B | 15 | 10 | 10 | 10 | 3 | 5 | 13 | 0 | 0 | 10 | +1.0 |
| opencode | 75 | B | 11 | 10 | 8 | 10 | 5 | 8 | 8 | 5 | 0 | 10 | +0.0 |

D6/D8 moved most: codex lost frontend partials while opencode kept D8 clean (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:13`; `audit-reports/codex_gpt_5_5/opencode-deepseek_v4_pro_ollama_cloud/report.md:14`).

### `gemma4_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 58 | C | 9 | 10 | 10 | 7 | 5 | 4 | 8 | 0 | 0 | 5 | +5.0 |
| codex | 44 | C | 7 | 9 | 8 | 5 | 5 | 0 | 4 | 0 | 0 | 6 | -9.0 |
| opencode | 53 | C | 10 | 10 | 8 | 7 | 5 | 4 | 4 | 0 | 0 | 5 | +0.0 |

D6/D7 moved most: codex collapsed to 0 on frontend wiring and opencode/claude stayed only partially wired (`audit-reports/codex_gpt_5_5/codex-gemma4_ollama_cloud/report.md:13`; `audit-reports/codex_gpt_5_5/claude-gemma4_ollama_cloud/report.md:13`).

### `glm_5_1_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 63 | B | 10 | 10 | 8 | 7 | 5 | 4 | 11 | 0 | 0 | 8 | -10.0 |
| codex | 73 | B | 12 | 10 | 10 | 10 | 5 | 7 | 9 | 0 | 0 | 10 | +0.0 |
| opencode | 76 | B | 12 | 10 | 10 | 10 | 5 | 10 | 9 | 0 | 0 | 10 | +3.0 |

D6 moved most: claude loaded but did not activate HTMX ws, while opencode reached full frontend marks (`audit-reports/codex_gpt_5_5/claude-glm_5_1_ollama_cloud/report.md:14`; `audit-reports/codex_gpt_5_5/opencode-glm_5_1_ollama_cloud/report.md:12`).

### `kimi_k2_6_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 78 | B | 12 | 10 | 10 | 10 | 5 | 10 | 11 | 0 | 0 | 10 | +8.0 |
| codex | 70 | B | 13 | 10 | 10 | 10 | 5 | 7 | 8 | 0 | 0 | 7 | +0.0 |
| opencode | 54 | C | 8 | 10 | 3 | 10 | 5 | 2 | 8 | 0 | 0 | 8 | -16.0 |

D3/D6 moved most: opencode missed LLM wiring tests and frontend build pieces while claude hit full marks (`audit-reports/codex_gpt_5_5/opencode-kimi_k2_6_ollama_cloud/report.md:10`; `audit-reports/codex_gpt_5_5/claude-kimi_k2_6_ollama_cloud/report.md:13`).

### `minimax_m2_7_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 57 | C | 9 | 10 | 8 | 7 | 5 | 0 | 9 | 0 | 1 | 8 | +0.0 |
| codex | 58 | C | 9 | 10 | 8 | 10 | 2 | 4 | 6 | 0 | 0 | 9 | +1.0 |
| opencode | 54 | C | 6 | 8 | 8 | 4 | 1 | 8 | 6 | 5 | 0 | 8 | -3.0 |

D6 moved most: claude used raw WebSocket/no HTMX ws, while opencode kept an HTMX route but streamed JSON fragments (`audit-reports/codex_gpt_5_5/claude-minimax_m2_7_ollama_cloud/report.md:12`; `audit-reports/codex_gpt_5_5/opencode-minimax_m2_7_ollama_cloud/report.md:12`).

### `nemotron_3_super_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 29 | D | 0 | 6 | 2 | 4 | 1 | 0 | 8 | 0 | 0 | 8 | +0.0 |
| codex | 26 | D | 0 | 7 | 8 | 1 | 1 | 0 | 2 | 0 | 0 | 7 | -3.0 |
| opencode | 41 | C | 2 | 9 | 3 | 7 | 5 | 3 | 8 | 0 | 0 | 4 | +12.0 |

D6/D7 moved most: codex had zero frontend wiring and weak architecture, while opencode kept partial routing and service shape (`audit-reports/codex_gpt_5_5/codex-nemotron_3_super_ollama_cloud/report.md:13`; `audit-reports/codex_gpt_5_5/opencode-nemotron_3_super_ollama_cloud/report.md:14`).

### `qwen3_5_ollama_cloud`
| Harness | Total | Tier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Δ vs model median |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 63 | B | 9 | 10 | 8 | 10 | 5 | 0 | 6 | 0 | 8 | 7 | +0.0 |
| codex | 68 | B | 12 | 10 | 10 | 10 | 3 | 7 | 9 | 0 | 0 | 7 | +5.0 |
| opencode | 59 | C | 9 | 10 | 8 | 10 | 5 | 3 | 8 | 0 | 1 | 5 | -4.0 |

D6/D10 moved most: claude used raw JS and opencode had template/security debt, while codex kept middling frontend but cleaner code (`audit-reports/codex_gpt_5_5/claude-qwen3_5_ollama_cloud/report.md:30`; `audit-reports/codex_gpt_5_5/opencode-qwen3_5_ollama_cloud/report.md:16`).

## 4a. Completion vs. quality gap
Rows with Harness `cursor` are Cursor-agent model runs (not contest harnesses).

| Model slug | Auditor | Harness | D1/15 | D10/10 | D1 ratio | D10 ratio | Gap | Flag |
|---|---|---|---:|---:|---:|---:|---:|---|
| kimi_k2_6_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 13 | 7 | 0.87 | 0.70 | 0.17 |  |
| gemma4_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 10 | 5 | 0.67 | 0.50 | 0.17 |  |
| qwen3_5_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 12 | 7 | 0.80 | 0.70 | 0.10 |  |
| gemma4_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 9 | 5 | 0.60 | 0.50 | 0.10 |  |
| deepseek_v4_flash_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 15 | 9 | 1.00 | 0.90 | 0.10 |  |
| qwen3_5_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 9 | 5 | 0.60 | 0.50 | 0.10 |  |
| deepseek_v4_pro_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 12 | 8 | 0.80 | 0.80 | 0.00 |  |
| codex_gpt_5_5(xhigh) | codex_gpt_5_5(xhigh) | codex | 15 | 10 | 1.00 | 1.00 | 0.00 |  |
| deepseek_v4_pro_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 15 | 10 | 1.00 | 1.00 | 0.00 |  |
| deepseek_v4_flash_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 10 | 7 | 0.67 | 0.70 | -0.03 |  |
| qwen3_5_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 9 | 7 | 0.60 | 0.70 | -0.10 |  |
| gemma4_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 7 | 6 | 0.47 | 0.60 | -0.13 |  |
| glm_5_1_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 10 | 8 | 0.67 | 0.80 | -0.13 |  |
| kimi_k2_6_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 12 | 10 | 0.80 | 1.00 | -0.20 |  |
| glm_5_1_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 12 | 10 | 0.80 | 1.00 | -0.20 |  |
| composer_2_0 | codex_gpt_5_5(xhigh) | cursor | 12 | 10 | 0.80 | 1.00 | -0.20 |  |
| composer_2_5 | codex_gpt_5_5(xhigh) | cursor | 12 | 10 | 0.80 | 1.00 | -0.20 |  |
| glm_5_1_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 12 | 10 | 0.80 | 1.00 | -0.20 |  |
| minimax_m2_7_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 9 | 8 | 0.60 | 0.80 | -0.20 |  |
| deepseek_v4_pro_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 11 | 10 | 0.73 | 1.00 | -0.27 |  |
| kimi_k2_6_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 8 | 8 | 0.53 | 0.80 | -0.27 |  |
| nemotron_3_super_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 2 | 4 | 0.13 | 0.40 | -0.27 |  |
| minimax_m2_7_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 9 | 9 | 0.60 | 0.90 | -0.30 | quality-over-completion |
| claude_opus_4_7 | codex_gpt_5_5(xhigh) | claude | 10 | 10 | 0.67 | 1.00 | -0.33 | quality-over-completion |
| deepseek_v4_flash_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 7 | 8 | 0.47 | 0.80 | -0.33 | quality-over-completion |
| minimax_m2_7_ollama_cloud | codex_gpt_5_5(xhigh) | opencode | 6 | 8 | 0.40 | 0.80 | -0.40 | quality-over-completion |
| nemotron_3_super_ollama_cloud | codex_gpt_5_5(xhigh) | codex | 0 | 7 | 0.00 | 0.70 | -0.70 | quality-over-completion |
| nemotron_3_super_ollama_cloud | codex_gpt_5_5(xhigh) | claude | 0 | 8 | 0.00 | 0.80 | -0.80 | quality-over-completion |

No run crosses the `completion-over-quality` flag threshold; the largest positive gaps are `codex-kimi_k2_6_ollama_cloud` and `opencode-gemma4_ollama_cloud` at +0.17. The codex-kimi D10 justification still penalizes a receive god-method and repeated broad handlers, so this is a mild gap rather than the v3.2 failure mode (`audit-reports/codex_gpt_5_5/codex-kimi_k2_6_ollama_cloud/report.md:17`).

## 5. Dimension-level signal
Contest cohort only (26 runs; cursor-agent excluded). Cursor reference: D1=12.0, D6=10.0, D8=5.0, D10=10.0 on both Composer runs.

- **D1 — Deliverable completeness** (max 15): universal-avg 9.4; per-harness avg claude=9.0 / codex=10.9 / opencode=8.1. Classify as: **harness-attributable**.
- **D2 — LLM integration correctness** (max 10): universal-avg 9.5; per-harness avg claude=9.6 / codex=9.6 / opencode=9.5. Classify as: **saturated** (near-threshold on full cohort).
- **D3 — Test quality** (max 10): universal-avg 8.0; per-harness avg claude=7.7 / codex=9.3 / opencode=7.0. Classify as: **harness-attributable**.
- **D4 — Error handling** (max 10): universal-avg 8.1; per-harness avg claude=7.3 / codex=8.4 / opencode=8.5. Classify as: **clean**.
- **D5 — Persistence / multi-turn** (max 5): universal-avg 4.3; per-harness avg claude=4.6 / codex=3.8 / opencode=4.5. Classify as: **saturated** (near-threshold on full cohort).
- **D6 — Streaming & frontend** (max 10): universal-avg 5.3; per-harness avg claude=4.9 / codex=5.2 / opencode=5.8. Classify as: **harness-attributable**.
- **D7 — Architecture** (max 15): universal-avg 8.1; per-harness avg claude=9.0 / codex=7.8 / opencode=7.4. Classify as: **universal blind spot**.
- **D8 — Secrets & config hygiene** (max 5): universal-avg 0.9; per-harness avg claude=0.4 / codex=0.6 / opencode=1.9. Classify as: **harness-attributable**.
- **D9 — Production hardening** (max 10): universal-avg 0.5; per-harness avg claude=1.2 / codex=0.0 / opencode=0.1. Classify as: **universal blind spot**.
- **D10 — Code quality** (max 10): universal-avg 7.8; per-harness avg claude=7.9 / codex=8.3 / opencode=7.2. Classify as: **universal blind spot** (calibration failure).

## 6. Performance & cost
`cursor-*` rows are Cursor-agent model benchmarks (not contest harnesses). Harness column is the path prefix for traceability only.

| Target (harness-model) | Gen-time (min) | Tokens (M) | Cost (USD) | Total score | Quality per $ | Quality per minute |
|---|---:|---:|---:|---:|---:|---:|
| codex-codex_gpt_5_5 | 40.7 | 3.58 | 18.35 | 86 | 4.7 | 2.11 |
| cursor-composer_2_5 | 17.3 | 0.09 | 0.48 | 83 | 172.9 | 4.79 |
| claude-claude_opus_4_7 | 39.0 | 0.10 | 6.15 | 82 | 13.3 | 2.10 |
| cursor-composer_2_0 | 32.0 | 0.19 | 2.00 | 80 | 40.0 | 2.50 |
| claude-kimi_k2_6_ollama_cloud | 33.5 | 6.26 | 18.22 | 78 | 4.3 | 2.33 |
| opencode-glm_5_1_ollama_cloud | 44.3 | 0.12 | 0.12 | 76 | 619.0 | 1.71 |
| codex-deepseek_v4_pro_ollama_cloud | 49.4 | 6.97 | 3.04 | 76 | 25.0 | 1.54 |
| opencode-deepseek_v4_pro_ollama_cloud | 32.8 | 0.11 | 0.05 | 75 | 1507.9 | 2.29 |
| codex-deepseek_v4_flash_ollama_cloud | 53.4 | 3.50 | 0.35 | 74 | 210.3 | 1.38 |
| codex-glm_5_1_ollama_cloud | 40.9 | 4.94 | 5.22 | 73 | 14.0 | 1.78 |
| claude-deepseek_v4_pro_ollama_cloud | 38.3 | 8.26 | 25.94 | 71 | 2.7 | 1.86 |
| codex-kimi_k2_6_ollama_cloud | 42.6 | 3.45 | 2.55 | 70 | 27.4 | 1.64 |
| opencode-deepseek_v4_flash_ollama_cloud | 23.2 | 0.07 | 0.01 | 68 | 10314.0 | 2.93 |
| codex-qwen3_5_ollama_cloud | 51.3 | 4.00 | 1.06 | 68 | 64.4 | 1.32 |
| claude-glm_5_1_ollama_cloud | 14.9 | 6.23 | 18.56 | 63 | 3.4 | 4.22 |
| claude-qwen3_5_ollama_cloud | 76.2 | 19.73 | 52.06 | 63 | 1.2 | 0.83 |
| opencode-qwen3_5_ollama_cloud | 48.5 | 0.12 | 0.03 | 59 | 1876.8 | 1.22 |
| codex-minimax_m2_7_ollama_cloud | 12.7 | 1.34 | 0.38 | 58 | 151.8 | 4.56 |
| claude-gemma4_ollama_cloud | 54.4 | 11.79 | 38.03 | 58 | 1.5 | 1.07 |
| claude-minimax_m2_7_ollama_cloud | 78.8 | 13.57 | 47.14 | 57 | 1.2 | 0.72 |
| opencode-minimax_m2_7_ollama_cloud | 39.1 | 0.11 | 0.03 | 54 | 1781.5 | 1.38 |
| opencode-kimi_k2_6_ollama_cloud | 41.3 | 0.12 | 0.09 | 54 | 592.7 | 1.31 |
| opencode-gemma4_ollama_cloud | 13.1 | 0.08 | 0.00 | 53 | n/a | 4.03 |
| claude-deepseek_v4_flash_ollama_cloud | 31.2 | 7.58 | 25.12 | 53 | 2.1 | 1.70 |
| codex-gemma4_ollama_cloud | 18.6 | 7.27 | 0.00 | 44 | n/a | 2.37 |
| opencode-nemotron_3_super_ollama_cloud | 40.7 | 0.13 | 0.01 | 41 | 3465.8 | 1.01 |
| claude-nemotron_3_super_ollama_cloud | 18.3 | 10.91 | 52.91 | 29 | 0.5 | 1.58 |
| codex-nemotron_3_super_ollama_cloud | 33.7 | 5.28 | 0.50 | 26 | 51.5 | 0.77 |

- Cheapest priced Tier-A run: `cursor-composer_2_5` at $0.48 (cursor_list API; subscription marginal cost may be $0).
- Best quality-per-$ among Tier-A runs: `cursor-composer_2_5` at 172.9 score/USD (list API).
- Fastest Tier-A run: `cursor-composer_2_5` at 17.3 minutes.
- Cost outlier: `claude-nemotron_3_super_ollama_cloud` spent $52.91 for 29/100, the worst score-per-dollar case.
- Time outlier: `claude-minimax_m2_7_ollama_cloud` took 78.8 minutes for 57/100.

## 7. Critical failure inventory
| CF type # | Trigger summary (from audit_prompt_template.txt) | Count | Affected targets | Classification |
|---:|---|---:|---|---|
| 1 | Any hardcoded secret in source/Dockerfile/compose/README/.env, including fallback/dev placeholders. | 29 | claude-deepseek_v4_flash_ollama_cloud claude-deepseek_v4_pro_ollama_cloud claude-gemma4_ollama_cloud claude-glm_5_1_ollama_cloud claude-kimi_k2_6_ollama_cloud claude-minimax_m2_7_ollama_cloud … | mixed (claude/codex/opencode) |
| 2 | Spec hard-requirement deliverable absent or loaded-but-unused. | 11 | claude-gemma4_ollama_cloud claude-glm_5_1_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud … | mixed (claude/codex/opencode) |
| 5 | Missing dependency declarations for spec-required pytest/tool/security deps. | 5 | claude-nemotron_3_super_ollama_cloud codex-minimax_m2_7_ollama_cloud opencode-deepseek_v4_flash_ollama_cloud opencode-minimax_m2_7_ollama_cloud opencode-nemotron_3_super_ollama_cloud | mixed (claude/codex/opencode) |
| 6 | Tooling claimed by README/spec but unconfigured. | 11 | claude-gemma4_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud codex-kimi_k2_6_ollama_cloud … | mixed (claude/codex/opencode) |
| 9 | False-green tests pass against anti-patterns. | 11 | claude-glm_5_1_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud codex-minimax_m2_7_ollama_cloud … | mixed (claude/codex/opencode) |
| 10 | DEBUG=True hardcoded/defaulted for production stack or .env*. | 9 | claude-deepseek_v4_flash_ollama_cloud claude-glm_5_1_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-kimi_k2_6_ollama_cloud codex-nemotron_3_super_ollama_cloud … | mixed (claude/codex/opencode) |
| 11 | AsyncWebsocketConsumer missing disconnect or has bare-pass disconnect. | 6 | claude-deepseek_v4_flash_ollama_cloud claude-deepseek_v4_pro_ollama_cloud claude-glm_5_1_ollama_cloud claude-nemotron_3_super_ollama_cloud codex-nemotron_3_super_ollama_cloud cursor-composer_2_0 | mixed (claude/codex/opencode) |
| 12 | Disallowed alternative path, e.g. vanilla JS instead of HTMX ws extension. | 4 | claude-deepseek_v4_flash_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud | harness-attributable (claude) |

## 8. Calibration check (rubric fitness, non-blocking)
| Check | Result | Evidence |
|---|---|---|
| Check 1 — Cohort median | PASS | Median total is 65.5/100 across 28 valid runs. |
| Check 2 — Dimension saturation | PASS | No dimension reaches >=80% full marks; D2 and D5 are near-threshold at 22/28 full marks (78.6%). |
| Check 3 — Dimension floor | WARN | D9 is 0 on 24/28 targets (85.7%), consistent with a production-hardening blind spot. |
| Check 4 — Tier distribution | PASS | Fixed-band histogram is A=3, B=13, C=10, D=2. |
| Check 5 — D10 floor (code quality) | FAIL | Median D10 is 8.0; several reports award 10/10 for small typed modules despite D8/D9 failures (`audit-reports/codex_gpt_5_5/codex-codex_gpt_5_5/report.md:16`; `audit-reports/codex_gpt_5_5/opencode-glm_5_1_ollama_cloud/report.md:16`). |

Overall verdict: **FAIL**. Recommend a Prompt-Version bump for `prompts/audit_prompt_template.txt`: tighten D10 caps when D8/D9 are zero, split D9 production-hardening triggers so healthcheck/restart/non-root/logging/SIGTERM are individually visible, and keep CF#1/CF#10 as explicit caps without re-grading this cohort.

## 9. Headline findings
- **Codex** leads the opencode/codex/claude harness contest on average total (63.9 vs 61.6 claude vs 60.0 opencode) on the shared Ollama grid (`audit-reports/codex_gpt_5_5/codex-codex_gpt_5_5/report.md:15`).
- Cursor-agent Composer runs score higher in isolation (81.5 avg) but are model-only benchmarks, not a fourth harness entrant (`audit-reports/codex_gpt_5_5/cursor-composer_2_5/report.md:12`).
- `deepseek_v4_pro_ollama_cloud` is the best eligible model because all three harness runs land in B-range totals and the codex run keeps full D1/D3/D4/D10 (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:8`; `audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:17`).
- Secrets/config hygiene is the most repeated CF family across shared Ollama targets: CF#1 appears 29 times across claude/codex/opencode (`audit-reports/codex_gpt_5_5/claude-deepseek_v4_pro_ollama_cloud/report.md:28`; `audit-reports/codex_gpt_5_5/opencode-glm_5_1_ollama_cloud/report.md:34`).
- Claude is uniquely associated with CF#12 vanilla-WebSocket substitutions in this cohort, hitting four targets while other harnesses avoid that CF type (`audit-reports/codex_gpt_5_5/claude-qwen3_5_ollama_cloud/report.md:31`; `audit-reports/codex_gpt_5_5/claude-nemotron_3_super_ollama_cloud/report.md:35`).
- Production hardening is universal debt: even the 86/100 leader scores 0/10 on D9 for missing healthcheck/restart/logging/SIGTERM handling (`audit-reports/codex_gpt_5_5/codex-codex_gpt_5_5/report.md:15`).
- D10 is too forgiving for calibration: reports often award 10/10 for small typed modules while serious deployment/security gaps live in D8/D9 (`audit-reports/codex_gpt_5_5/cursor-composer_2_5/report.md:16`; `audit-reports/codex_gpt_5_5/opencode-glm_5_1_ollama_cloud/report.md:16`).

## 10. Recommendations
- [rubric] Add a D10 cap: if D8=0 or D9=0, D10 cannot exceed 8 unless the report explicitly explains why code maintainability is independent of the security/production failure; current 10/10 D10 rows coexist with zero hardening (`audit-reports/codex_gpt_5_5/codex-codex_gpt_5_5/report.md:15`; `audit-reports/codex_gpt_5_5/codex-codex_gpt_5_5/report.md:16`).
- [rubric] Split D9 into separately reported sub-checks for healthcheck, restart policy, non-root user, structured logging, and SIGTERM/WebSocket shutdown; the current single 0/10 bucket hides which remediation dominates (`audit-reports/codex_gpt_5_5/cursor-composer_2_5/report.md:15`).
- [prompt] Add a concrete forbidden/allowed secret example: do not put `DJANGO_SECRET_KEY=test`, placeholders, or build-time dummy keys in README/tests/Docker/.env; use env-only examples and generated compose secrets instead, because CF#1 is the top failure (`audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:29`; `audit-reports/codex_gpt_5_5/codex-deepseek_v4_pro_ollama_cloud/report.md:30`).
- [harness] Cursor-agent token/cost is now backfilled from stream `usage` for Composer runs (list API ~$0.48 / $2.00); treat subscription marginal cost as $0 when comparing to cloud API harnesses (`audit-reports/codex_gpt_5_5/cursor-composer_2_5/report.md:38`).
- [retry] Re-run at least one shared Ollama model under the Cursor agent, or run Composer under codex/claude/opencode, to compare Composer against the contest grid rather than only cursor-prefixed paths.
- [harness] Add a claude harness final grep/check for `new WebSocket(` and missing `hx-ext="ws"` before completion; CF#12 is claude-only and directly violates the benchmark path (`audit-reports/codex_gpt_5_5/claude-minimax_m2_7_ollama_cloud/report.md:32`).

## 11. Appendix: data inputs
### Input directories
- `/home/hugo/projects/python-benchmark/audit-reports/codex_gpt_5_5`

### Report counts
| Directory | report.md files globbed |
|---|---:|
| /home/hugo/projects/python-benchmark/audit-reports/codex_gpt_5_5 | 28 |

- Total reports successfully parsed with non-null total: 28.
- Reports where total was absent: none.
- Reports where section H was malformed or missing: none.
- Reports with cost/token `n/a` in section H (stale audit copy): `cursor-composer_2_0`, `cursor-composer_2_5` — generation-metrics now have computed cursor_list costs ($2.00 / $0.48).
- Prompt/benchmark version mismatches: none detected; all reports state `audit-v3.8`, `benchmark-v3.2`, and `benchmark-followup-v3.2` where follow-up is present.

### Single-harness models (contest)
- `codex_gpt_5_5(xhigh)` (codex)
- `claude_opus_4_7` (claude)

### Cursor agent models
| Model slug | Runs | Avg total |
|---|---:|---:|
| composer_2_5 | 1 | 83.0 |
| composer_2_0 | 1 | 80.0 |

Excluded from harness comparison and section 2 harness counts.

### Full dimension score matrix
| Auditor | Target | Harness | Model | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | Total | Tier |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| codex_gpt_5_5(xhigh) | claude-claude_opus_4_7 | claude | claude_opus_4_7 | 10 | 10 | 10 | 10 | 5 | 10 | 11 | 4 | 2 | 10 | 82 | A |
| codex_gpt_5_5(xhigh) | claude-deepseek_v4_flash_ollama_cloud | claude | deepseek_v4_flash_ollama_cloud | 10 | 10 | 3 | 4 | 5 | 6 | 8 | 0 | 0 | 7 | 53 | C |
| codex_gpt_5_5(xhigh) | claude-deepseek_v4_pro_ollama_cloud | claude | deepseek_v4_pro_ollama_cloud | 12 | 10 | 10 | 7 | 5 | 10 | 9 | 0 | 0 | 8 | 71 | B |
| codex_gpt_5_5(xhigh) | claude-gemma4_ollama_cloud | claude | gemma4_ollama_cloud | 9 | 10 | 10 | 7 | 5 | 4 | 8 | 0 | 0 | 5 | 58 | C |
| codex_gpt_5_5(xhigh) | claude-glm_5_1_ollama_cloud | claude | glm_5_1_ollama_cloud | 10 | 10 | 8 | 7 | 5 | 4 | 11 | 0 | 0 | 8 | 63 | B |
| codex_gpt_5_5(xhigh) | claude-kimi_k2_6_ollama_cloud | claude | kimi_k2_6_ollama_cloud | 12 | 10 | 10 | 10 | 5 | 10 | 11 | 0 | 0 | 10 | 78 | B |
| codex_gpt_5_5(xhigh) | claude-minimax_m2_7_ollama_cloud | claude | minimax_m2_7_ollama_cloud | 9 | 10 | 8 | 7 | 5 | 0 | 9 | 0 | 1 | 8 | 57 | C |
| codex_gpt_5_5(xhigh) | claude-nemotron_3_super_ollama_cloud | claude | nemotron_3_super_ollama_cloud | 0 | 6 | 2 | 4 | 1 | 0 | 8 | 0 | 0 | 8 | 29 | D |
| codex_gpt_5_5(xhigh) | claude-qwen3_5_ollama_cloud | claude | qwen3_5_ollama_cloud | 9 | 10 | 8 | 10 | 5 | 0 | 6 | 0 | 8 | 7 | 63 | B |
| codex_gpt_5_5(xhigh) | codex-codex_gpt_5_5 | codex | codex_gpt_5_5(xhigh) | 15 | 10 | 10 | 10 | 5 | 10 | 11 | 5 | 0 | 10 | 86 | A |
| codex_gpt_5_5(xhigh) | codex-deepseek_v4_flash_ollama_cloud | codex | deepseek_v4_flash_ollama_cloud | 15 | 10 | 10 | 10 | 5 | 7 | 8 | 0 | 0 | 9 | 74 | B |
| codex_gpt_5_5(xhigh) | codex-deepseek_v4_pro_ollama_cloud | codex | deepseek_v4_pro_ollama_cloud | 15 | 10 | 10 | 10 | 3 | 5 | 13 | 0 | 0 | 10 | 76 | B |
| codex_gpt_5_5(xhigh) | codex-gemma4_ollama_cloud | codex | gemma4_ollama_cloud | 7 | 9 | 8 | 5 | 5 | 0 | 4 | 0 | 0 | 6 | 44 | C |
| codex_gpt_5_5(xhigh) | codex-glm_5_1_ollama_cloud | codex | glm_5_1_ollama_cloud | 12 | 10 | 10 | 10 | 5 | 7 | 9 | 0 | 0 | 10 | 73 | B |
| codex_gpt_5_5(xhigh) | codex-kimi_k2_6_ollama_cloud | codex | kimi_k2_6_ollama_cloud | 13 | 10 | 10 | 10 | 5 | 7 | 8 | 0 | 0 | 7 | 70 | B |
| codex_gpt_5_5(xhigh) | codex-minimax_m2_7_ollama_cloud | codex | minimax_m2_7_ollama_cloud | 9 | 10 | 8 | 10 | 2 | 4 | 6 | 0 | 0 | 9 | 58 | C |
| codex_gpt_5_5(xhigh) | codex-nemotron_3_super_ollama_cloud | codex | nemotron_3_super_ollama_cloud | 0 | 7 | 8 | 1 | 1 | 0 | 2 | 0 | 0 | 7 | 26 | D |
| codex_gpt_5_5(xhigh) | codex-qwen3_5_ollama_cloud | codex | qwen3_5_ollama_cloud | 12 | 10 | 10 | 10 | 3 | 7 | 9 | 0 | 0 | 7 | 68 | B |
| codex_gpt_5_5(xhigh) | cursor-composer_2_0 | cursor | composer_2_0 | 12 | 10 | 10 | 7 | 5 | 10 | 11 | 5 | 0 | 10 | 80 | B |
| codex_gpt_5_5(xhigh) | cursor-composer_2_5 | cursor | composer_2_5 | 12 | 10 | 10 | 10 | 5 | 10 | 11 | 5 | 0 | 10 | 83 | A |
| codex_gpt_5_5(xhigh) | opencode-deepseek_v4_flash_ollama_cloud | opencode | deepseek_v4_flash_ollama_cloud | 7 | 9 | 8 | 10 | 5 | 8 | 8 | 5 | 0 | 8 | 68 | B |
| codex_gpt_5_5(xhigh) | opencode-deepseek_v4_pro_ollama_cloud | opencode | deepseek_v4_pro_ollama_cloud | 11 | 10 | 8 | 10 | 5 | 8 | 8 | 5 | 0 | 10 | 75 | B |
| codex_gpt_5_5(xhigh) | opencode-gemma4_ollama_cloud | opencode | gemma4_ollama_cloud | 10 | 10 | 8 | 7 | 5 | 4 | 4 | 0 | 0 | 5 | 53 | C |
| codex_gpt_5_5(xhigh) | opencode-glm_5_1_ollama_cloud | opencode | glm_5_1_ollama_cloud | 12 | 10 | 10 | 10 | 5 | 10 | 9 | 0 | 0 | 10 | 76 | B |
| codex_gpt_5_5(xhigh) | opencode-kimi_k2_6_ollama_cloud | opencode | kimi_k2_6_ollama_cloud | 8 | 10 | 3 | 10 | 5 | 2 | 8 | 0 | 0 | 8 | 54 | C |
| codex_gpt_5_5(xhigh) | opencode-minimax_m2_7_ollama_cloud | opencode | minimax_m2_7_ollama_cloud | 6 | 8 | 8 | 4 | 1 | 8 | 6 | 5 | 0 | 8 | 54 | C |
| codex_gpt_5_5(xhigh) | opencode-nemotron_3_super_ollama_cloud | opencode | nemotron_3_super_ollama_cloud | 2 | 9 | 3 | 7 | 5 | 3 | 8 | 0 | 0 | 4 | 41 | C |
| codex_gpt_5_5(xhigh) | opencode-qwen3_5_ollama_cloud | opencode | qwen3_5_ollama_cloud | 9 | 10 | 8 | 10 | 5 | 3 | 8 | 0 | 1 | 5 | 59 | C |

### Per-harness std dev by dimension (contest harnesses only)
| Harness | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 3.6 | 1.3 | 3.1 | 2.3 | 1.3 | 4.4 | 1.7 | 1.3 | 2.6 | 1.5 |
| codex | 4.9 | 1.0 | 1.0 | 3.2 | 1.6 | 3.4 | 3.4 | 1.7 | 0.0 | 1.6 |
| opencode | 3.2 | 0.8 | 2.6 | 2.3 | 1.4 | 3.1 | 1.6 | 2.6 | 0.4 | 2.3 |

### Cross-auditor disagreement
No `(harness, model_slug)` cell has >=2 auditors in this input set; no cross-auditor std-dev can be computed.

### Harness CLI versions
| Harness | Version(s) | Targets | Notes |
|---|---|---|---|
| claude | unknown | 9 | - |
| codex | unknown | 9 | - |
| cursor | unknown | 2 | cursor-agent (excluded from harness contest) |
| opencode | unknown | 8 | - |

No `mixed-version` harness appears in the rollup; no mixed-harness-version exclusions were applied.

### Tier distribution histogram
| Tier | Count |
|---|---:|
| A | 3 |
| B | 13 |
| C | 10 |
| D | 2 |

### Full critical-failure affected-target lists
| CF type # | Full affected targets |
|---:|---|
| 1 | claude-deepseek_v4_flash_ollama_cloud claude-deepseek_v4_pro_ollama_cloud claude-gemma4_ollama_cloud claude-glm_5_1_ollama_cloud claude-kimi_k2_6_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-deepseek_v4_flash_ollama_cloud codex-deepseek_v4_pro_ollama_cloud codex-gemma4_ollama_cloud codex-glm_5_1_ollama_cloud codex-kimi_k2_6_ollama_cloud codex-minimax_m2_7_ollama_cloud codex-nemotron_3_super_ollama_cloud codex-qwen3_5_ollama_cloud opencode-gemma4_ollama_cloud opencode-glm_5_1_ollama_cloud opencode-kimi_k2_6_ollama_cloud opencode-nemotron_3_super_ollama_cloud opencode-qwen3_5_ollama_cloud |
| 2 | claude-gemma4_ollama_cloud claude-glm_5_1_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud codex-minimax_m2_7_ollama_cloud codex-nemotron_3_super_ollama_cloud opencode-kimi_k2_6_ollama_cloud opencode-nemotron_3_super_ollama_cloud opencode-qwen3_5_ollama_cloud |
| 5 | claude-nemotron_3_super_ollama_cloud codex-minimax_m2_7_ollama_cloud opencode-deepseek_v4_flash_ollama_cloud opencode-minimax_m2_7_ollama_cloud opencode-nemotron_3_super_ollama_cloud |
| 6 | claude-gemma4_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud codex-kimi_k2_6_ollama_cloud codex-nemotron_3_super_ollama_cloud opencode-deepseek_v4_pro_ollama_cloud opencode-gemma4_ollama_cloud opencode-nemotron_3_super_ollama_cloud opencode-qwen3_5_ollama_cloud |
| 9 | claude-glm_5_1_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-gemma4_ollama_cloud codex-minimax_m2_7_ollama_cloud codex-nemotron_3_super_ollama_cloud opencode-deepseek_v4_flash_ollama_cloud opencode-deepseek_v4_pro_ollama_cloud opencode-kimi_k2_6_ollama_cloud opencode-qwen3_5_ollama_cloud |
| 10 | claude-deepseek_v4_flash_ollama_cloud claude-glm_5_1_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud codex-kimi_k2_6_ollama_cloud codex-nemotron_3_super_ollama_cloud codex-qwen3_5_ollama_cloud opencode-gemma4_ollama_cloud opencode-qwen3_5_ollama_cloud |
| 11 | claude-deepseek_v4_flash_ollama_cloud claude-deepseek_v4_pro_ollama_cloud claude-glm_5_1_ollama_cloud claude-nemotron_3_super_ollama_cloud codex-nemotron_3_super_ollama_cloud cursor-composer_2_0 |
| 12 | claude-deepseek_v4_flash_ollama_cloud claude-minimax_m2_7_ollama_cloud claude-nemotron_3_super_ollama_cloud claude-qwen3_5_ollama_cloud |
