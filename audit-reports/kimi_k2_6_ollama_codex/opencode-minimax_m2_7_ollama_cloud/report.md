# Audit Report — minimax_m2_7_ollama_cloud

## A. Quick summary
Submission delivers a functional Django Channels + Ollama streaming SPA, but tests are shallow, the dependency manifest is incomplete (missing `pip-audit`), and default security middleware is stripped.

## B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 21 / 25 | `pip-audit` absent from deps & unconfigured (-2, CF#5/CF#6). Unused deps `httpx`/`safety` declared but never imported (-2, U8). Dockerfile, compose, README, pyproject.toml, `.env.example`, `ASGI_APPLICATION` all present. Tailwind CLI wired and compiled. Daphne in Dockerfile. |
| 2 | LLM integration correctness | 20 / 20 | Raw `ollama.AsyncClient` with `stream=True` yields `AsyncIterator[ChatResponse]`; env-driven `OLLAMA_HOST`/`OLLAMA_MODEL`; multi-turn history accumulates; tokens sent chunk-by-chunk over WS. |
| 3 | Test quality | 0 / 15 | No LLM-path tests at all (-10). No AsyncClient mocks or fake LLM (-3). No `WebsocketCommunicator` consumer tests (-3). `testpaths = ["chat/tests"]` points to a missing directory, so `make test` collects 0 items. |
| 4 | Error handling | 2 / 10 | `MIDDLEWARE` omits `CsrfViewMiddleware` (-2, CF#4). No Ollama reachability preflight guard (-3, U1). `disconnect` is bare `pass` (-3, U2). Error JSON does reach the UI, so no U3 deduction. |
| 5 | Persistence / multi-turn state | 5 / 10 | `history` is a class variable (`ChatConsumer.history = {}`), making it shared and race-prone across all consumer instances (-5). History does accumulate per session key. |
| 6 | Streaming & frontend wiring | 8 / 10 | HTMX ws extension wired (`hx-ws="connect:…"` / `hx-ws="send:…"`), vanilla JS handles `htmx:ws-message` for token-by-token `textContent` updates. No chunk-by-chunk streaming assertion in tests (-2). Consumer does not buffer before first send. |
| 7 | Architecture | 2 / 5 | Consumer instantiates `AsyncClient` inline with no service layer abstraction (-3, U4). View is clean (template only). Settings use `BASE_DIR`. |
| 8 | Secrets & config hygiene | 2 / 3 | `ALLOWED_HOSTS` defaults to `["*"]` on the Docker/compose production path (-1). `SECRET_KEY` reads from env with no fallback; no hardcoded secrets in operational files. |
| 9 | Production hardening | 0 / 2 | No Dockerfile `HEALTHCHECK` and no compose healthcheck (-1, U7). No structured JSON logging configuration in settings; only default `logging` usage in consumer (-1, U5). Non-root user present. |

## C. Total score
**60 / 100**

## D. Practical tier
**C (41–60)** — major rework needed. Core bugs or missing deliverables.

## E. Verification section
All API usage verified against installed package source (`/home/hugo/projects/python-benchmark/results/opencode-minimax_m2_7_ollama_cloud/project/.venv/lib/python3.13/site-packages/ollama/_client.py`):

- `AsyncClient.__init__(host: Optional[str] = None, **kwargs)` — line 724–725.
- `AsyncClient.chat(..., stream: bool = False) -> Union[ChatResponse, AsyncIterator[ChatResponse]]` — lines 941–972.
- `ChatResponse` inherits from `SubscriptableBaseModel` which defines `__getitem__`, confirming `chunk["message"]["content"]` is valid.

No hallucinated API calls found.

## F. Critical Failures

- `ollama_chat/settings.py:26` — `MIDDLEWARE` list is missing `django.middleware.csrf.CsrfViewMiddleware`, removing a framework-default security control.
- `pyproject.toml:15-25` — `pip-audit` is not declared in `project.optional-dependencies` dev list (`safety>=3.0` is present instead), so `make security` cannot be reproduced from the dependency manifest.
- `Makefile:14` — `pip-audit` is invoked in the `security` target but the tool is neither installed by the manifest nor configured in pyproject.toml.

## G. Critical-failure ledger

| File:line | Trigger | Deduction |
|-----------|---------|-----------|
| `ollama_chat/settings.py:26` | CF#4 — Missing framework-default security middleware (`CsrfViewMiddleware`) → D4 "CSRF disabled globally: -2" | -2 |
| `pyproject.toml:15-25` | CF#5 — Missing dependency declarations (`pip-audit` absent from deps) → D1 "Each missing tool config (ruff, mypy, bandit, coverage, pip-audit): -1" | -1 |
| `Makefile:14` | CF#6 — Tooling claimed but unconfigured (`pip-audit` called with no `[tool.pip-audit]` block and no installable dep) → D1 "Each missing tool config: -1" | -1 |

## H. Submission metadata & generation metrics

```
Model:               minimax-m2.7:cloud
Harness:             opencode
Generation-Time:     1597.09 s
Input-Tokens:        78615
Output-Tokens:       116
Total-Tokens:        78731
Estimated-Cost-USD:  ~0.0236
Pricing-Source:      PRICING.md @ 2026-05-09 (Ollama Cloud minimax-m2.7:cloud — $0.299/$1.200 per 1M tokens)
Date:                2026-05-15
Prompt-Version:      v2.1
Source:              results/opencode-minimax_m2_7_ollama_cloud
```

## I. Killer strength + Killer weakness

- **Killer strength:** Clean, working token-streaming loop over WebSocket with correct raw `ollama.AsyncClient` usage and per-session multi-turn history.
- **Killer weakness:** Test suite is entirely shallow (no mocked LLM, no WebSocket communicator, broken `testpaths` config) and the dependency manifest swaps required `pip-audit` for unused `safety`.
