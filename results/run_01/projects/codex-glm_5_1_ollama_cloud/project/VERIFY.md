# Verification Summary

## Phase 2 — End-to-end runtime validation

| # | Step | Command | Result | Evidence |
|---|------|---------|--------|----------|
| 1 | Venv + deps + migrations | `source .venv/bin/activate && pip install -r requirements.txt && DJANGO_SECRET_KEY=test python manage.py migrate` | ✅ Pass | Python 3.13.13; all deps installed; 16 migrations applied |
| 2 | Tests | `DJANGO_SECRET_KEY=test-secret-key-12345 pytest tests/ -v` | ✅ Pass | 33 passed in 0.82s |
| 3 | Coverage | `DJANGO_SECRET_KEY=test-secret-key-12345 coverage run -m pytest tests/ && coverage report` | ✅ Pass | 94% overall (154 stmts, 10 miss) |
| 4 | Ruff lint | `ruff check chat/ config/ tests/` | ✅ Pass | All checks passed |
| 5 | Ruff format | `ruff format --check chat/ config/ tests/` | ✅ Pass | 22 files already formatted |
| 6 | mypy | `mypy chat/ config/ tests/` | ✅ Pass | Success: no issues in 21 files |
| 7 | bandit | `bandit -r chat/ config/` | ✅ Pass | No issues (0 H/M/L) |
| 8 | pip-audit | `pip-audit -r requirements.txt` | ✅ Pass | No known vulnerabilities |
| 9 | ASGI boot | `DJANGO_SECRET_KEY=test daphne -b 127.0.0.1 -p 8000 config.asgi:application` | ✅ Pass | Listening on TCP 127.0.0.1:8000 |
| 10 | HTTP page reachable | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/` | ✅ Pass | HTTP 200 |
| 11 | HTMX WS extension | `curl -s http://127.0.0.1:8000/ \| grep -oE 'hx-ext\|ws-connect\|ws-send'` | ✅ Pass | `hx-ext="ws"`, `ws-connect="/ws/chat/"`, `ws-send` |
| 12 | No raw WebSocket JS | `curl -s http://127.0.0.1:8000/ \| grep -c 'new WebSocket'` | ✅ Pass | 0 matches — uses HTMX ws extension only |
| 13 | WS connect + stream | `websockets.connect('ws://127.0.0.1:8000/ws/chat/')` → send `{"message":"Say hello in 3 words"}` | ✅ Pass | Connected; received start → token×3 ("Hi", " there", "!") → end |
| 14 | Health endpoint | `curl -s http://127.0.0.1:8000/health/` | ✅ Pass | `{"ollama_reachable": true, "host": "http://localhost:11434"}` |
| 15 | Docker build | `docker build -t chat-app .` | ✅ Pass | Image built (layers: python:3.13-slim + pip install + collectstatic) |
| 16 | Docker compose up | `DJANGO_SECRET_KEY=test docker compose up --build -d` | ✅ Pass | Container started; daphne listening on 0.0.0.0:8000 |
| 17 | Docker HTTP reachable | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/` | ✅ Pass | HTTP 200 from container |
| 18 | Docker WS extension | `curl -s http://127.0.0.1:8000/ \| grep -oE 'hx-ext\|ws-connect\|ws-send'` | ✅ Pass | Same attributes in container response |

## Fixes applied during validation

| File | Fix | Reason |
|------|-----|--------|
| `chat/consumers.py` | Extract `_drain_stream()` method; wrap with `asyncio.wait_for(timeout=120)`; add `TimeoutError` handler | Consumer hung indefinitely when Ollama unreachable — no timeout on `stream_response()` |
| `chat/services/llm.py` | Add `httpx.Timeout(connect=5, read=60, write=10, pool=5)` via `async_client_kwargs` | Underlying ollama client had no connect timeout; could hang >15s before raising |
| `.dockerignore` | Created with `.venv/`, `__pycache__/`, `.git/`, etc. | Docker context was 300+ MB due to `.venv` being sent; first build took 70s just for context transfer |

## Environment Blockers

- **Docker → Ollama unreachable**: Inside Docker, `localhost:11434` refers to the container, not the host. `/health/` returns 503 with `ollama_reachable: false` — expected environmental constraint, not a code bug. The `extra_hosts: host.docker.internal:host-gateway` in compose is present but Ollama is not bound to the Docker bridge interface. To fix, set `OLLAMA_HOST=http://host.docker.internal:11434` when running compose.

## Ollama status (host)

Ollama is reachable on the host at `http://localhost:11434`. Model `qwen2.5:7b` is available. Live WebSocket streaming was verified end-to-end with 3 tokens received.
