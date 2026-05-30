# Audit Report

## A. Quick Summary Line
Submission mostly meets benchmark-v3.2, but not ship-ready because README hardcodes a secret-shaped test key, production hardening is absent, and frontend partials/settings architecture are thin.

## B. Scores Per Dimension
| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 15 / 15 | Dockerfile, compose, README, pyproject, `.env.example`, ASGI, Tailwind CLI, tool configs all present: `Dockerfile:1`, `docker-compose.yml:1`, `pyproject.toml:25`, `.env.example:7`, `chat_project/settings.py:41`. |
| 2 | D2 LLM integration correctness | 10 / 10 | Correct `langchain_ollama` import, env-wired `ChatOllama`, `.astream()`, and WS token piping: `chat/llm_service.py:7`, `chat/llm_service.py:11`, `chat/llm_service.py:16`, `chat/llm_service.py:26`, `chat/consumers.py:52`. |
| 3 | D3 Test quality | 10 / 10 | Mocked LLM path, WebsocketCommunicator consumer tests, view/template tests: `chat/tests/test_consumer.py:11`, `chat/tests/test_consumer.py:45`, `chat/tests/test_consumer.py:91`, `chat/tests/test_views.py:11`. |
| 4 | D4 Error handling | 10 / 10 | LLM try/except, health check, real disconnect, CSRF middleware, UI error sends: `chat/llm_service.py:25`, `chat/llm_service.py:40`, `chat/consumers.py:21`, `chat/consumers.py:77`, `chat_project/settings.py:22`. |
| 5 | D5 Persistence / multi-turn | 5 / 5 | Per-consumer history accumulates user and assistant turns: `chat/consumers.py:14`, `chat/consumers.py:47`, `chat/consumers.py:63`. |
| 6 | D6 Streaming & frontend | 7 / 10 | HTMX ws is wired and chunks update text, but app is a single template dump with no partial include files: `chat/templates/chat/chat.html:20`, `chat/templates/chat/chat.html:30`, `chat/templates/chat/chat.html:62`, `chat/templates/chat/chat.html:75`. |
| 7 | D7 Architecture | 8 / 15 | Service module exists, but no settings split, no typed/protocol LLM interface, and consumer class spans `chat/consumers.py:11` to `chat/consumers.py:88`; concrete service construction at `chat/llm_service.py:15`. |
| 8 | D8 Secrets & config hygiene | 0 / 5 | CF#1 caps dimension: README hardcodes `DJANGO_SECRET_KEY=testkey`: `README.md:71`. |
| 9 | D9 Production hardening | 0 / 10 | No Docker/compose healthcheck, no restart policy, no non-root `USER`, no structured `LOGGING`, no SIGTERM stream shutdown: `Dockerfile:1`, `Dockerfile:16`, `docker-compose.yml:1`, `chat_project/settings.py:65`. |
| 10 | D10 Code quality | 9 / 10 | Only D10 trigger: >2 broad `except Exception` handlers: `chat/consumers.py:77`, `chat/llm_service.py:30`, `chat/llm_service.py:45`; files stay under 500 lines. |

## C. Total Score / 100
74 / 100.

## D. Practical Tier
B (61-80): 1-2 hours to ship if secret docs and prod hardening are fixed; architecture is workable but not polished.

## E. Verification Section
No hallucinated API calls claimed. Prescribed `.venv/lib/python3.*/site-packages` globs had no package matches; `.venv` contains only pip, so API proof used populated Python 3.13 env `.venv13`.

Grep proof: `.venv13/lib/python3.13/site-packages/langchain_ollama/chat_models.py:261` `class ChatOllama`, `:525` `model: str`, `:693` `base_url`, `:1366` `_astream`; `.venv13/lib/python3.13/site-packages/langchain_core/language_models/chat_models.py:461` `invoke`, `:488` `ainvoke`, `:713` `stream`, `:842` `astream`; `.venv13/lib/python3.13/site-packages/ollama/_client.py:723` `class AsyncClient`, `:941` async `chat`, `:978` `stream`; `.venv13/lib/python3.13/site-packages/channels/generic/websocket.py:156` `AsyncWebsocketConsumer`, `:186` `connect`, `:254` `disconnect`, `:274` `receive_json`, `:280` `send_json`; `.venv13/lib/python3.13/site-packages/channels/routing.py:36` `ProtocolTypeRouter`, `:55` `URLRouter`.

## F. Critical Failures
- CF#1 `README.md:71`: hardcoded `DJANGO_SECRET_KEY=testkey` is a secret-shaped placeholder in README.

## G. Critical-Failure Ledger
`README.md:71` -> CF#1 "Any hardcoded secret in source / Dockerfile / compose / README / .env, including fallback or dev placeholder values for secret-shaped variables" -> D8 cap 0, mandatory -5.

## H. Submission Metadata & Generation Metrics
Model: deepseek_v4_flash_ollama_cloud  
Harness: codex  
Generation-Time: 3206.34 seconds  
Input-Tokens / Output-Tokens / Total-Tokens: 3484748 / 16964 / 3501712  
Estimated-Cost-USD: 0.351868  
Pricing-Source: docs/PRICING.md @ 2026-05-25  
Date: 2026-05-29  
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2  
Source: results/codex-deepseek_v4_flash_ollama_cloud/project  
Primary-Prompt-SHA256: 14d18a37c91098a78ee7a8488f9386e25ab226178d7cd0020802256e9b4bbc5b  
Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5

## I. Killer Strength + Killer Weakness
Killer strength: core LangChain/Channels streaming path is real, async, env-configured, and tested chunk-by-chunk.

Killer weakness: prod-readiness collapses under D8/D9 because docs leak a secret placeholder and container hardening is almost entirely missing.
