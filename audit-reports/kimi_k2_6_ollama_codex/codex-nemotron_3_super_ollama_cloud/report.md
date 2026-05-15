# Audit Report — codex-nemotron_3_super_ollama_cloud

## A. Quick summary line
Submission meets most deliverables but has missing tool configs, no chat history, a bare-pass disconnect, and a production-hardening gap (DEBUG=True default in compose).

## B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 18 / 25 | No tool config files for ruff, mypy, bandit, coverage, pip-audit (-5). Unused deps in requirements.txt (fastapi, nicegui, starlette, htmx, etc.) not imported in source (-2). |
| 2 | LLM integration correctness | 17 / 20 | Uses real `ollama.AsyncClient.chat(model=..., messages=..., stream=True)` (verified). OLLAMA_HOST/MODEL wired via env. No multi-turn history (-3). |
| 3 | Test quality | 13 / 15 | Consumer tests mock AsyncClient and assert chunk-by-chunk streaming. `test_home_view_status_code` is empty `pass` — no real view/template test (-2). |
| 4 | Error handling | 4 / 10 | No env check / unreachable-Ollama preflight guard (U1) (-3). `disconnect` is bare `pass` (U2) (-3). Error UI is visible (no U3 deduction). |
| 5 | Persistence / multi-turn state | 3 / 10 | No message history; each message sent independently to Ollama (-7). |
| 6 | Streaming & frontend wiring | 10 / 10 | Vanilla JS streams tokens token-by-token. Tailwind CSS compiled. Consumer yields chunks immediately without buffering. |
| 7 | Architecture | 2 / 5 | Consumer instantiates `AsyncClient` inline with no service layer (U4) (-3). View is clean. |
| 8 | Secrets & config hygiene | 1 / 3 | No SECRET_KEY literal in source. docker-compose hardcodes `DJANGO_DEBUG=${DJANGO_DEBUG:-True}` as default (-1). `ALLOWED_HOSTS = []` misconfigured for container path (-1). |
| 9 | Production hardening | 0 / 2 | No Dockerfile HEALTHCHECK and no compose healthcheck (-1). No structured logging configured (-1). |

## C. Total score
**68 / 100**

## D. Practical tier
**B (61–80)**: 1–2 hours to ship. Core streaming works; gaps are tooling configs, history, and hardening.

## E. Verification section

**`ollama.AsyncClient.chat` signature**
```
$ grep -n 'class AsyncClient' venv/lib/python3.12/site-packages/ollama/_client.py
723:class AsyncClient(BaseClient):
$ sed -n '972,980p' venv/lib/python3.12/site-packages/ollama/_client.py
  async def chat(
    self,
    model: str = '',
    messages: Optional[Sequence[Union[Mapping[str, Any], Message]]] = None,
    *,
    stream: bool = False,
```
`part.get('message', {}).get('content', '')` is valid because `ChatResponse` extends `SubscriptableBaseModel` which defines `.get()` and supports dict-style access.

**`from ollama import AsyncClient`**
```
$ grep -n 'AsyncClient' venv/lib/python3.12/site-packages/ollama/__init__.py
1:from ollama._client import AsyncClient, Client
```

**`channels` classes**
```
$ grep -n 'class AsyncWebsocketConsumer' ~/.local/lib/python3.12/site-packages/channels/generic/websocket.py
156:class AsyncWebsocketConsumer(AsyncConsumer):
$ grep -n 'ProtocolTypeRouter\\|URLRouter' ~/.local/lib/python3.12/site-packages/channels/routing.py
36:class ProtocolTypeRouter:
55:class URLRouter:
```

Package-source verification for `langchain_ollama` was **unverified** because the project venv is empty (only pip); no `langchain_ollama` installation was available to grep.

## F. Critical Failures

- **CF#6** `README.md:35-44` — README claims ruff, mypy, bandit, coverage, and pip-audit are configured, but no `[tool.ruff]`, `[tool.mypy]`, `.bandit`, `[tool.coverage]`, or pip-audit invocation exists anywhere in the repo.
- **CF#10** `docker-compose.yml:9` — `DJANGO_DEBUG=${DJANGO_DEBUG:-True}` hardcodes `DEBUG=True` as the default for the Docker/production path.

## G. Critical-failure ledger

| File:line | Mapped trigger | Deduction |
|-----------|----------------|-----------|
| `README.md:35-44` → tooling claimed by README/spec but unconfigured (no `[tool.ruff]`, no `[tool.mypy]`, no `.bandit` / `[tool.bandit]`, no `[tool.coverage]`, no pip-audit invocation) | D1 Deliverable completeness: "Each missing tool config (ruff, mypy, bandit, coverage, pip-audit): -1" | −5 |
| `docker-compose.yml:9` → `DEBUG = True` hardcoded for the production stack | D8 Secrets & config hygiene: "`DEBUG=True` hardcoded as the default for the production/Docker path, or compose hardcodes debug on: -1" | −1 |

## H. Submission metadata & generation metrics

- **Model**: nemotron-3-super:cloud
- **Harness**: codex
- **Generation-Time**: 1448.27 s
- **Input-Tokens**: 6517355
- **Output-Tokens**: 28525
- **Total-Tokens**: 6545880
- **Estimated-Cost-USD**: n/a (model not present in PRICING.md)
- **Pricing-Source**: n/a
- **Date**: 2026-05-15
- **Prompt-Version**: v2.1
- **Source**: /home/hugo/projects/python-benchmark/results/codex-nemotron_3_super_ollama_cloud

## I. Killer strength + Killer weakness

**Killer strength**: Token streaming is correctly implemented end-to-end with real chunk-by-chunk WebSocket delivery and matching tests.

**Killer weakness**: No chat history means the app is single-turn only, breaking the ChatGPT-style SPA expectation.
