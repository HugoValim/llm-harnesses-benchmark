# Audit Report — claude-claude_opus_4_7

## A. Quick summary line

The submission meets the spec with a clean Django+Channels SPA, real token streaming via `langchain-ollama`, HTMX WebSocket extension, and comprehensive tests, but hardcoded `SECRET_KEY` placeholders in tests and README trigger critical failures.

## B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 23 / 25 | `python-dotenv` declared but never imported in source (U8): `requirements.txt:4`, `pyproject.toml:7`. All other deliverables present and wired. |
| 2 | LLM integration correctness | 20 / 20 | Correct `from langchain_ollama import ChatOllama`, `.astream()` streaming, env-driven `OLLAMA_HOST`/`OLLAMA_MODEL` with defaults. No hallucinations. |
| 3 | Test quality | 15 / 15 | 18 passing tests; consumer test asserts individual token frames (`tests/test_consumers.py:37-41`); LLM path mocked via `patch` and fake `ChatOllama` (`tests/test_llm.py:49`). |
| 4 | Error handling | 7 / 10 | Try/except wraps streaming loop (`chat/consumers.py:72-78`); user-visible error sent on failure. No Ollama-reachability preflight guard (U1): `-3`. |
| 5 | Persistence / multi-turn state | 10 / 10 | Per-consumer `self.history` accumulates user + assistant turns (`chat/consumers.py:66,83`). |
| 6 | Streaming & frontend wiring | 10 / 10 | HTMX ws-ext loaded, `ws-send`/`hx-swap-oob` for token-by-token DOM updates; pre-built Tailwind exists; chunk-by-chunk consumer test verifies streaming. |
| 7 | Architecture | 5 / 5 | Service-layer split via `TokenStreamer` protocol + `chat/llm.py`; consumer is thin; view only renders shell. |
| 8 | Secrets & config hygiene | 0 / 3 | Hardcoded `DJANGO_SECRET_KEY` literals in `tests/conftest.py:8` and `README.md:106,113` trigger CF#1, capping this dimension at 0. No production fallback. |
| 9 | Production hardening | 1 / 2 | Compose-level healthcheck present (`docker-compose.yml:27-32`); no explicit `LOGGING` dict in settings (U5): `-1`. Non-root user in Dockerfile: best-practice only. |

## C. Total score / 100

**91 / 100**

## D. Practical tier

**A (81–100)**: ship as-is or with trivial (<30 min) patches.

## E. Verification section

- `ChatOllama` exists in `langchain_ollama.chat_models`:
  ```
  261:class ChatOllama(BaseChatModel):
  ```
- `astream` exists on `BaseChatModel` (inherited by `ChatOllama`):
  ```
  842:    async def astream(
  ```
- `base_url` is a declared field on `ChatOllama`:
  ```
  693:    base_url: str | None = None
  ```
- `AsyncWebsocketConsumer`, `receive`, `disconnect` in `channels.generic.websocket`:
  ```
  156:class AsyncWebsocketConsumer(AsyncConsumer):
  186:    async def connect(self):
  208:    async def receive(self, text_data=None, bytes_data=None):
  254:    async def disconnect(self, code):
  ```
- `ProtocolTypeRouter` and `URLRouter` in `channels.routing`:
  ```
  36:class ProtocolTypeRouter:
  55:class URLRouter:
  ```
- No hallucinated APIs found.

## F. Critical Failures

- `tests/conftest.py:8` — hardcoded `DJANGO_SECRET_KEY = "test-secret-not-used-outside-tests"` literal in source.
- `README.md:106` — example shell command hardcodes `DJANGO_SECRET_KEY=test-secret`.
- `README.md:113` — example shell command hardcodes `DJANGO_SECRET_KEY=test-secret`.

## G. Critical-failure ledger

| File:line | Trigger | Deduction |
|-----------|---------|-----------|
| `tests/conftest.py:8` | CF#1 — Any hardcoded secret in source / Dockerfile / compose / README / .env (Django `SECRET_KEY` literals count) | D8 capped at 0 |
| `README.md:106` | CF#1 — Any hardcoded secret in source / Dockerfile / compose / README / .env (Django `SECRET_KEY` literals count) | D8 capped at 0 |
| `README.md:113` | CF#1 — Any hardcoded secret in source / Dockerfile / compose / README / .env (Django `SECRET_KEY` literals count) | D8 capped at 0 |

## H. Submission metadata & generation metrics

- **Model**: claude-opus-4-7
- **Harness**: claude (Claude Code)
- **Generation-Time**: 795.53 s
- **Input-Tokens**: 6,321,044 (100 regular + 138,079 cache-creation + 6,182,865 cache-read)
- **Output-Tokens**: 38,722
- **Total-Tokens**: 6,359,766
- **Estimated-Cost-USD**: $158.99
- **Pricing-Source**: PRICING.md @ 2026-05-09 (Anthropic claude-opus-4-7 row: $5.00 input / $25.00 output per 1M)
- **Date**: 2026-05-15
- **Prompt-Version**: v2.1
- **Source**: /home/hugo/projects/python-benchmark/results/claude-claude_opus_4_7

## I. Killer strength + Killer weakness

- **Killer strength**: Rigorous test suite covers chunk-by-chunk streaming, HTML escaping, backend failure, and template partials with real `WebsocketCommunicator` integration tests.
- **Killer weakness**: Hardcoded `SECRET_KEY` placeholders in `tests/conftest.py` and README example commands, which should use a fixture-generated or env-only value to avoid critical-failure triggers.
