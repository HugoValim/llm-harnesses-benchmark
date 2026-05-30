## A. Quick summary line
Submission mostly meets the chat/streaming spec, but misses reproducible dev deps and production hardening.

## B. Scores per dimension
| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 7 / 15 | Core files exist, but dev tools are absent from `requirements.txt:1-4` (CF#5, -5) and Django auth is enabled despite "no auth" (`chat_project/settings.py:15`, `chat_project/settings.py:29`, -3). |
| 2 | D2 LLM integration correctness | 9 / 10 | Correct `ChatOllama` import/env/`.astream` path (`chat/llm_service.py:3`, `chat/llm_service.py:10`, `chat/consumers.py:71`); tests lack chunk-by-chunk assertion (`chat/tests.py:106`, -1). |
| 3 | D3 Test quality | 8 / 10 | View, consumer, LLM mock tests exist (`chat/tests.py:46`, `chat/tests.py:77`, `chat/tests.py:90`), but CF#9 caps score because buffered output would still pass (`chat/tests.py:106`). |
| 4 | D4 Error handling | 10 / 10 | LLM streaming errors are caught and surfaced (`chat/consumers.py:36`, `chat/consumers.py:59`, `chat/templates/chat/chat.html:66`); CSRF and real disconnect exist (`chat_project/settings.py:28`, `chat/consumers.py:20`). |
| 5 | D5 Persistence / multi-turn | 5 / 5 | Per-consumer history accumulates user/assistant turns (`chat/consumers.py:15`, `chat/consumers.py:34`, `chat/consumers.py:50`). |
| 6 | D6 Streaming & frontend | 8 / 10 | HTMX ws extension and token UI are wired (`chat/templates/chat/chat.html:20`, `chat/templates/chat/chat.html:26`, `chat/templates/chat/chat.html:53`); no chunk-by-chunk assertion (`chat/tests.py:106`, -2). |
| 7 | D7 Architecture | 8 / 15 | Service module exists (`chat/llm_service.py:9`), but no prod/settings split (`chat_project/settings.py:1`), consumer is >30 nonblank lines (`chat/consumers.py:12`), and LLM boundary lacks protocol/typed stream API (`chat/consumers.py:70`). |
| 8 | D8 Secrets & config hygiene | 5 / 5 | `SECRET_KEY` is required from env with no fallback (`chat_project/settings.py:6`); Docker/compose defaults keep debug false (`Dockerfile:17`, `docker-compose.yml:10`). |
| 9 | D9 Production hardening | 0 / 10 | No `HEALTHCHECK`/`USER` in `Dockerfile:1-21`, no compose `restart` in `docker-compose.yml:1-11`, no structured `LOGGING` or SIGTERM stream handling in `chat_project/settings.py:1-74`. |
| 10 | D10 Code quality | 8 / 10 | Type-safety gap only: declared mypy, but public views and LLM stream arg are untyped (`chat/views.py:11`, `chat/views.py:15`, `chat/consumers.py:70`, -2). |

## C. Total score / 100
68 / 100.

## D. Practical tier
B (61-80): 1-2 hours to ship core app, but dependency manifest and prod path need fixes.

## E. Verification section
No hallucinated API calls claimed. Installed-source checks: `langchain_ollama/chat_models.py:176` has `class ChatOllama`, `:330` has `model`, `:408` has `base_url`, `:748` has `async def _astream`; `langchain_core/language_models/chat_models.py:384/:408/:465/:556` confirms `invoke/ainvoke/stream/astream`; `ollama/_client.py:723` and `:941` confirm `AsyncClient.chat`; `channels/generic/websocket.py:156/:186/:254` confirms `AsyncWebsocketConsumer/connect/disconnect`; `channels/routing.py:36/:55` confirms `ProtocolTypeRouter/URLRouter`.

## F. Critical Failures
- `requirements.txt:1-4` lists only runtime deps; pytest, pytest-django, pytest-asyncio, ruff, mypy, bandit, coverage, and pip-audit are not declared, so the dev env is not reproducible.
- `chat/tests.py:106` asserts only `''.join(tokens) == 'Hello World'`; a buffered one-chunk stream would pass.

## G. Critical-failure ledger
| Evidence | Mapped trigger | Mandatory deduction |
|---|---|---|
| `requirements.txt:1-4` | CF#5: "Missing dependency declarations: spec-required tools ... absent" | No specific point trigger; -5 from D1. |
| `chat/tests.py:106` | CF#9: "Tests pass against an anti-pattern ... assert buffered output instead of streaming chunks" | D3 cap 8; also D2 -1 and D6 -2 for missing chunk-by-chunk assertion. |

## H. Submission metadata & generation metrics
Model: deepseek_v4_flash_ollama_cloud  
Harness: opencode  
Harness-CLI-Version: n/a  
Generation-Time: 1392.9 seconds  
Input-Tokens / Output-Tokens / Total-Tokens: 65020 / 453 / 65473  
Estimated-Cost-USD: 0.006593  
Pricing-Source: docs/PRICING.md @ 2026-05-25  
Cost-Source: computed  
Date: 2026-05-29  
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2  
Source: /home/hugo/projects/python-benchmark/results/opencode-deepseek_v4_flash_ollama_cloud/result.json  
Primary-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5  
Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5

## I. Killer strength + Killer weakness
Killer strength: real LangChain Ollama token streaming reaches the HTMX WebSocket UI.  
Killer weakness: reproducibility/prod hardening is thin enough that local green claims do not recreate cleanly.
