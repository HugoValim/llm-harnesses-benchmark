# Audit Report: qwen3.5:cloud via Claude Code

## A. Quick summary

Submission meets most deliverables but breaks real-world Ollama streaming because the consumer treats pydantic `ChatResponse` chunks as dicts, and a hardcoded `DJANGO_SECRET_KEY` placeholder is baked into the production Dockerfile.

## B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|------------:|---------------|
| 1 | Deliverable completeness | 21 / 25 | Tailwind claimed (`django-tailwind` in requirements) but not wired—CSS is hand-written custom (no `tailwind.config.*`, no build). Unused deps (`langchain-ollama`, `channels-redis`, `gunicorn`, `uvicorn`) declared but never imported (U8). |
| 2 | LLM integration correctness | 14 / 20 | Uses correct `AsyncClient.chat(stream=True)` API, but `chat/consumers.py:80` calls `.get()` on `ChatResponse` pydantic objects; `isinstance(chunk, dict)` is `False`, so real chunks fall to `str(chunk)` and emit garbage tokens. No multi-turn history (single-shot messages list). |
| 3 | Test quality | 10 / 15 | Good coverage (consumer, view, template, chunk-by-chunk assertions), but mocks Ollama chunks as plain dicts rather than installed `ChatResponse` models, giving false-green against the real API. |
| 4 | Error handling | 7 / 10 | LLM call is wrapped in `try/except`. Missing Ollama preflight / env guard (U1): no check that host is reachable before streaming. `disconnect` handler is present and logs. |
| 5 | Persistence / multi-turn state | 3 / 10 | No history accumulation: `chat/consumers.py:58` rebuilds a single-turn `messages` list on every request. |
| 6 | Streaming & frontend wiring | 7 / 10 | Token-by-token UI updates work via native WebSocket JS. Tailwind not actually built (custom CSS only). HTMX `htmx.min.js` is referenced in template but missing from static files; app falls back to vanilla JS, which is acceptable per spec. |
| 7 | Architecture | 2 / 5 | Consumer creates `AsyncClient` and calls `chat()` inline with no service layer abstraction (U4). |
| 8 | Secrets & config hygiene | 0 / 3 | **Capped at 0** by CF#1: `Dockerfile:38` hardcodes `ENV DJANGO_SECRET_KEY=temp-for-collect static`. `DEBUG` default is env-driven; compose path sets `false`. `ALLOWED_HOSTS` is not `*`. |
| 9 | Production hardening | 1 / 2 | Dockerfile and compose both have `HEALTHCHECK`. No `LOGGING` config in `settings.py` (print-only / default logger). |

## C. Total score / 100

**65 / 100**

## D. Practical tier

**B (61–80)**: Architecture is sound, tests are present, and Docker is wired. 1–2 hours to ship: fix token extraction bug, remove hardcoded build-time secret, add a thin LLM service layer, and wire actual Tailwind build.

## E. Verification

`ollama` `AsyncClient.chat(stream=True)` yields `ChatResponse` pydantic models, not plain dicts.

```
$ grep -n 'class ChatResponse' /home/hugo/projects/python-benchmark/results/claude-qwen3_5_ollama_cloud/project/_venv/lib/python3.14/site-packages/ollama/_types.py
413:class ChatResponse(BaseGenerateResponse):

$ sed -n '780,790p' /home/hugo/projects/python-benchmark/results/claude-qwen3_5_ollama_cloud/project/_venv/lib/python3.14/site-packages/ollama/_client.py
          async for line in r.aiter_lines():
            part = json.loads(line)
            if err := part.get('error'):
              raise ResponseError(err)
            yield cls(**part)

$ python3 -c "from pydantic import BaseModel; print(hasattr(BaseModel, 'get'))"
False
```

`ChatResponse` inherits from `SubscriptableBaseModel` → `BaseModel`. It supports `__getitem__` but **not** `.get()`. Therefore `chunk.get("message", {})` in the consumer will raise `AttributeError` on a real chunk unless the `isinstance(chunk, dict)` guard diverts to `str(chunk)`, which streams the string representation of the pydantic model instead of token content.

## F. Critical Failures

- `Dockerfile:38` — `ENV DJANGO_SECRET_KEY=temp-for-collect static` is a hardcoded placeholder for a `*_KEY` secret-shaped variable baked into the production image. Maps to CF#1.
- `chat/tests.py:127-128` — mocks Ollama streaming chunks as plain dicts (`{"message": {"content": "Hello"}}`), but the installed `ollama` client yields `ChatResponse` pydantic objects (`_client.py:yield cls(**part)`). Tests pass against a hallucinated API surface. Maps to CF#9.

## G. Critical-failure ledger

| File:line | Mapped rubric trigger | Deduction |
|-----------|----------------------|-----------|
| `Dockerfile:38` | Any `SECRET_KEY` / `DJANGO_SECRET_KEY` literal or insecure string fallback in source, Dockerfile, compose, or README: cap this dimension at 0 (CF#1) | D8 capped at 0 |
| `chat/tests.py:127` | Tests mock the hallucinated API: -5 (CF#9) | -5 from D3 |

## H. Submission metadata & generation metrics

```
Model:              qwen3.5:cloud
Harness:            claude-code
Generation-Time:    1951.35 s
Input-Tokens:       7202762
Output-Tokens:      34623
Total-Tokens:       7237385
Estimated-Cost-USD: 1.93
Pricing-Source:     PRICING.md @ 2026-05-09
Date:               2026-05-15
Prompt-Version:     v2.1
Source:             results/claude-qwen3_5_ollama_cloud/
```

*Cost computation:* $(7{,}202{,}762 / 1{,}000{,}000) \times 0.26 + (34{,}623 / 1{,}000{,}000) \times 1.56 = 1.93$ USD.

## I. Killer strength + Killer weakness

**Killer strength:** Solid test coverage with chunk-by-chunk WebSocket streaming assertions and a clean vanilla-JS frontend that correctly handles token-by-token updates.

**Killer weakness:** The consumer assumes Ollama chunks are dicts and calls `.get()` on them, but the installed client returns pydantic `ChatResponse` models, so real streaming would emit garbage tokens while the test suite falsely passes.
