# Audit Report — deepseek_v4_flash_ollama_cloud

## A. Quick summary line

Submission builds a working Django+Channels SPA with real-time Ollama streaming, but misses CSRF middleware and omits pytest/ruff/mypy/bandit/coverage/pip-audit from the dependency manifest.

## B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 19 / 25 | pyproject.toml lacks pytest, pytest-django, pytest-asyncio, ruff, mypy, bandit, coverage, pip-audit deps (CF#5); no [tool.pip-audit] block (-1). |
| 2 | LLM integration correctness | 17 / 20 | Single-turn only; no conversation history in chat/consumers.py:52 (-3). |
| 3 | Test quality | 15 / 15 | Token-by-token streaming asserted via WebsocketCommunicator; mocks use real ollama.AsyncClient. |
| 4 | Error handling | 2 / 10 | Missing CsrfViewMiddleware in config/settings.py:12 (-2, CF#4); bare pass disconnect in chat/consumers.py:17 (-3, U2); no Ollama reachability preflight (-3, U1). |
| 5 | Persistence / multi-turn state | 3 / 10 | No history; consumer sends one-shot messages in chat/consumers.py:52 (-7). |
| 6 | Streaming & frontend wiring | 10 / 10 | Vanilla JS appends tokens to DOM in real time; consumer yields chunks immediately; partials used. |
| 7 | Architecture | 2 / 5 | LLM client wired inline in consumer with no service layer (chat/consumers.py:40-52, U4) (-3). |
| 8 | Secrets & config hygiene | 3 / 3 | SECRET_KEY loaded from env with no fallback; DEBUG defaults to false in compose; ALLOWED_HOSTS narrow. |
| 9 | Production hardening | 0 / 2 | No HEALTHCHECK in Dockerfile or compose (U7, -1); no structured logging config in config/settings.py (U5, -1). |

## C. Total score / 100

**71 / 100**

## D. Practical tier

**B (61-80)** — 1-2 hours to ship. Architecture is sound, minor gaps.

## E. Verification section

- ollama.AsyncClient.chat(model=..., messages=..., stream=True) exists and yields AsyncIterator[ChatResponse] (ollama/_client.py:972).
- ChatResponse supports .get() via SubscriptableBaseModel (ollama/_types.py:19), so part.get("message", {}).get("content", "") in chat/consumers.py:49 is valid.
- channels.generic.websocket.AsyncWebsocketConsumer exposes receive(self, text_data=None, bytes_data=None) and receive_json(self, content, **kwargs) (channels/generic/websocket.py:208,274).
- channels.routing.ProtocolTypeRouter and URLRouter exist (channels/routing.py:36,55).
- No hallucinated API calls identified.

## F. Critical Failures

- config/settings.py:12 — MIDDLEWARE omits django.middleware.csrf.CsrfViewMiddleware (CF#4).
- requirements.txt:1 / pyproject.toml:8 — pytest, pytest-django, pytest-asyncio, ruff, mypy, bandit, coverage, pip-audit absent from dependency manifest (CF#5).

## G. Critical-failure ledger

- config/settings.py:12 → Missing framework-default security middleware that the specs stack assumes (CSRF, security middleware, SecurityMiddleware) (CF#4) → mapped to D4 CSRF disabled globally (e.g. CsrfViewMiddleware removed or bypassed): -2.
- requirements.txt:1 → Missing dependency declarations: spec-required tools absent from requirements*.txt / pyproject.toml (CF#5) → no exact D1 trigger; -5 from D1 Deliverable completeness.

## H. Submission metadata & generation metrics

- **Model:** deepseek-v4-flash:cloud
- **Harness:** claude-code (via Ollama Cloud shim)
- **Generation-Time:** 490.1 s
- **Input-Tokens:** 3940847
- **Output-Tokens:** 25077
- **Total-Tokens:** 3965924
- **Estimated-Cost-USD:** n/a
- **Pricing-Source:** n/a — model row absent from benchmark-ai-code PRICING.md
- **Date:** 2026-05-15
- **Prompt-Version:** v2.1
- **Source:** /home/hugo/projects/python-benchmark/results/claude-deepseek_v4_flash_ollama_cloud/

## I. Killer strength + Killer weakness

- **Killer strength:** Token streaming works end-to-end with clean vanilla-JS DOM appending and solid per-chunk WebSocket tests.
- **Killer weakness:** Consumer has zero conversation history, turning a chat app into a stateless Q&A widget.
