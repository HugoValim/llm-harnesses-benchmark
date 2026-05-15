A. **Quick summary line**
Submission misses spec: hardcoded Django `SECRET_KEY`, broken Dockerfile (`collectstatic` fails without `STATIC_ROOT`), bare-pass disconnect, no multi-turn history, and `pytest` collects zero tests by default.

B. **Scores per dimension**

| # | Dimension | Score / Max | Justification (file:line) |
|---|-----------|-------------|---------------------------|
| 1 | Deliverable completeness | 14 / 25 | Dockerfile broken `Dockerfile:34` (`collectstatic` needs `STATIC_ROOT`); pip-audit unconfigured; auth middleware present `settings.py:35`; unused `channels_redis` `requirements.txt:3`. |
| 2 | LLM integration correctness | 17 / 20 | Streams via `ollama.AsyncClient.chat(..., stream=True)` `chat/consumers.py:35`; no multi-turn history `chat/consumers.py:30`. |
| 3 | Test quality | 10 / 15 | `chat/tests.py` passes when run directly but `pytest` collects 0 items (not `test_*.py`); no chunk-by-chunk WS assertion `chat/tests.py:42`. |
| 4 | Error handling | 0 / 10 | No try/except around LLM call `chat/consumers.py:30`; bare-pass disconnect `chat/consumers.py:14`; no degraded UI; no preflight guard. |
| 5 | Persistence / multi-turn state | 3 / 10 | Single-turn only `chat/consumers.py:30`. |
| 6 | Streaming & frontend wiring | 5 / 10 | No `{% include %}` partials; no chunk-by-chunk test assertion `chat/tests.py:42`. |
| 7 | Architecture | 2 / 5 | Consumer creates LLM client inline (no service layer) `chat/consumers.py:26`. |
| 8 | Secrets & config hygiene | 0 / 3 | Hardcoded `SECRET_KEY` literal `settings.py:23` (CF#1); `DEBUG=True` hardcoded `settings.py:26` (CF#10). |
| 9 | Production hardening | 0 / 2 | No Dockerfile/compose healthcheck; no structured logging (print-only). |

C. **Total score / 100**
51

D. **Practical tier**
**C (41–60)**: major rework needed.

E. **Verification section**
- `ollama.AsyncClient.chat` with `stream=True` yields `AsyncIterator[ChatResponse]`; `part['message']['content']` works because `ChatResponse` inherits `SubscriptableBaseModel` (`venv/lib/python3.13/site-packages/ollama/_types.py:413`, `_client.py:941`) — unverified because `.venv` path missing; used `venv` for reference only.
- `AsyncWebsocketConsumer.connect`, `.disconnect`, `.receive_json`, `.send_json` exist in `channels/generic/websocket.py` (`venv/lib/python3.13/site-packages/channels/generic/websocket.py:186,254,274,280`) — unverified.
- `ollama.AsyncClient(host=...)` signature confirmed in `_client.py:723` — unverified.
- `ChatOllama` not used; raw `ollama` client used. No hallucinated imports.

F. **Critical Failures**
- `chatproject/settings.py:23` — hardcoded `SECRET_KEY = 'django-insecure-l-25he42srlhf*^&8t3r$6uzqftz1=#z49x$+qdq+2-_r0iw4g'` (CF#1).
- `chatproject/settings.py:26` — `DEBUG = True` hardcoded for production/Docker path (CF#10).

G. **Critical-failure ledger**
- `chatproject/settings.py:23` → "Any hardcoded secret in source / Dockerfile / compose / README / `.env` (including 'fallback' or 'dev placeholder' values for secret-shaped variables)" (CF#1) → cap D8 at 0.
- `chatproject/settings.py:26` → "`DEBUG = True` hardcoded for the production stack (Dockerfile/compose path), or `.env*` defaults to `DEBUG=True`" (CF#10) → -1 from D8 (already 0).

H. **Submission metadata & generation metrics**
```
Model: nemotron-3-super:cloud
Harness: claude-code
Generation-Time: 1469.78 s
Input-Tokens: 15441655
Output-Tokens: 47569
Total-Tokens: 15489224
Estimated-Cost-USD: n/a (model row missing from PRICING.md)
Pricing-Source: n/a
Date: 2026-05-15
Prompt-Version: v2.1
Source: results/claude-nemotron_3_super_ollama_cloud
```

I. **Killer strength** + **Killer weakness**
- **Killer strength**: Streams tokens correctly over WebSocket using raw `ollama` async client.
- **Killer weakness**: Hardcoded `SECRET_KEY` and missing `STATIC_ROOT` make the Dockerfile unbuildable.
