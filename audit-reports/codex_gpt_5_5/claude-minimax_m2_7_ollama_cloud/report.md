A. **Quick summary line**
Submission partially meets spec, but fails required HTMX WebSocket wiring and secret hygiene.

B. **Scores per dimension**
| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 9 / 15 | Core files exist, but auth enabled (`ollama_chat/settings.py:25-28`), unused deps (`requirements.txt:4-7`; no imports found), no Bandit config though declared (`requirements.txt:13`). |
| 2 | D2 LLM integration correctness | 10 / 10 | Correct `langchain_ollama.ChatOllama` + `astream` + env override path (`chat/llm_service.py:9,16-23,30`). |
| 3 | D3 Test quality | 8 / 10 | Consumer/service/view tests exist, but frontend test blesses wrong JS path (`chat/tests.py:200-206`), CF#9 cap. |
| 4 | D4 Error handling | 7 / 10 | Consumer catches stream errors (`chat/consumers.py:47-56`), but no startup/preflight guard; `/health/` only reports after request (`chat/views.py:14-17`). |
| 5 | D5 Persistence / multi-turn | 5 / 5 | Per-consumer history accumulates human/AI turns (`chat/consumers.py:20,44,52`). |
| 6 | D6 Streaming & frontend | 0 / 10 | HTMX ws extension absent (`templates/chat/index.html:9-10`), raw WebSocket used (`static/js/ws.js:86`), later chunks ignored (`static/js/ws.js:95-104`). |
| 7 | D7 Architecture | 9 / 15 | Service module exists, but no settings split, consumer is 40 nonblank class lines (`chat/consumers.py:11-65`), LLM service imported in views (`chat/views.py:6`). |
| 8 | D8 Secrets & config hygiene | 0 / 5 | Hardcoded secret literals cap dimension (`docker-compose.yml:7`, `Dockerfile:18`, `ollama_chat/test_settings.py:8`). |
| 9 | D9 Production hardening | 1 / 10 | Compose healthcheck exists, but no logging/restart/USER/shutdown handling (`docker-compose.yml:1-17`, `Dockerfile:1-27`, no `LOGGING` grep hits). |
| 10 | D10 Code quality | 8 / 10 | Type-safety gap: public views untyped and `dict` unparameterized (`chat/views.py:9,14`, `chat/llm_service.py:34`). |

C. **Total score / 100**
57 / 100.

D. **Practical tier**
C (41-60): major rework needed. Core server streaming is present, but frontend contract and secret hygiene fail hard requirements.

E. **Verification section**
No hallucinated API claims found. Installed source verifies used APIs: `langchain_ollama/chat_models.py:261` `class ChatOllama`, `:525` `model`, `:693` `base_url`; `langchain_core/language_models/chat_models.py:461` `invoke`, `:488` `ainvoke`, `:713` `stream`, `:842` `astream`; `ollama/_client.py:723` `class AsyncClient`, `:941` async `chat`; `channels/generic/websocket.py:156` `AsyncWebsocketConsumer`, `:186` `connect`, `:254` `disconnect`, `:274` `receive_json`, `:280` `send_json`; `channels/routing.py:36` `ProtocolTypeRouter`, `:55` `URLRouter`.

F. **Critical Failures**
- CF#1: hardcoded Django secret fallback/literals in source/container/docs (`docker-compose.yml:7`, `Dockerfile:18`, `ollama_chat/test_settings.py:8`, `README.md:67`, `VERIFY.md:14`).
- CF#2: required HTMX WebSocket extension not wired; template loads HTMX and custom JS only (`templates/chat/index.html:9-10`).
- CF#6: Bandit declared but unconfigured; no `.bandit`/`[tool.bandit]`/`[bandit]` file or block (`requirements.txt:13`, `setup.cfg:1-13`).
- CF#9: tests false-green wrong frontend path by asserting `ws.js`, not ws extension/hx wiring (`chat/tests.py:200-206`).
- CF#12: disallowed app-owned raw WebSocket path (`static/js/ws.js:86`).

G. **Critical-failure ledger**
| Evidence | Mapping | Mandatory deduction |
|---|---|---:|
| `docker-compose.yml:7`; `Dockerfile:18`; `ollama_chat/test_settings.py:8`; `README.md:67`; `VERIFY.md:14` | CF#1 hardcoded secret -> D8 cap | D8 = 0 |
| `templates/chat/index.html:9-10` | CF#2 required deliverable absent/unused -> D6 “No HTMX WebSocket extension wired” | -4 |
| `requirements.txt:13`, `setup.cfg:1-13` | CF#6 tooling claimed but unconfigured -> D1 missing tool config | -1 |
| `chat/tests.py:200-206` | CF#9 tests pass against anti-pattern -> D3 cap | cap 8 |
| `static/js/ws.js:86` | CF#12 disallowed vanilla JS alternative -> D6 same trigger | -4 |

H. **Submission metadata & generation metrics**
Model: minimax_m2_7_ollama_cloud
Harness: claude
Harness-CLI-Version: n/a
Generation-Time: 4729.91 seconds
Input-Tokens: 13504117
Output-Tokens: 61234
Total-Tokens: 13565351
Estimated-Cost-USD: 47.140645
Pricing-Source: docs/PRICING.md @ 2026-05-25
Cost-Source: harness_reported
Benchmark-Result: /home/hugo/projects/python-benchmark/results/claude-minimax_m2_7_ollama_cloud/result.json
Date: 2026-05-29
Prompt-Version: audit-v3.8; benchmark-v3.2; benchmark-followup-v3.2
Source: /home/hugo/projects/python-benchmark/results/claude-minimax_m2_7_ollama_cloud/project
Primary-Prompt-SHA256: 9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28
Followup-Prompt-SHA256: bf86cbe9f5cf245ba911e3a1c9cffbe3e4ac1aed08da7c973a9c73c3a62eeae3

I. **Killer strength** + **Killer weakness**
Killer strength: server-side LangChain/Ollama streaming path is real and chunk-tested.
Killer weakness: browser streaming ignores benchmark-mandated HTMX ws extension and drops chunks after first token.
