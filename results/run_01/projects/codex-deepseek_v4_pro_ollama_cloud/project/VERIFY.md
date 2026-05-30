# Verification summary

Environment: Python 3.13.13 via mise, Linux x64, Docker 28+.

| # | Command | Result | Evidence / Blocker |
|---|---------|--------|---------------------|
| 1 | `mise exec -- python3 --version` | PASS | Python 3.13.13 |
| 2 | `.venv/bin/pip install -r requirements.txt` | PASS | All deps installed |
| 3 | `.venv/bin/pip install pytest pytest-django pytest-asyncio ruff mypy bandit coverage pip-audit django-stubs` | PASS | Dev deps installed |
| 4 | `DJANGO_SECRET_KEY=test-key .venv/bin/pytest tests/ -v` | PASS | 12 passed in ~2s |
| 5 | `.venv/bin/ruff check .` | PASS | All checks passed |
| 6 | `.venv/bin/ruff format --check .` | PASS | 21 files already formatted |
| 7 | `.venv/bin/mypy chat/ config/` | PASS | Success: no issues in 15 source files |
| 8 | `.venv/bin/bandit -r chat/ config/ manage.py` | PASS | No issues identified (0 High/Medium/Low) |
| 9 | `DJANGO_SECRET_KEY=test-key .venv/bin/coverage run -m pytest tests/ -q && .venv/bin/coverage report` | PASS | 76% coverage (>70% threshold) |
| 10 | `.venv/bin/pip-audit` | PASS | No known vulnerabilities found |
| 11 | `DJANGO_SECRET_KEY=test-key .venv/bin/daphne -b 127.0.0.1 -p 8765 config.asgi:application` → `curl http://127.0.0.1:8765/` | PASS | HTTP 200, page served |
| 12 | `curl http://127.0.0.1:8765/ \| grep 'hx-ext="ws"'` | PASS | HTMX WebSocket extension present in rendered HTML |
| 13 | `curl http://127.0.0.1:8765/ \| grep 'ws-connect="/ws/chat/"'` | PASS | ws-connect attribute present |
| 14 | `curl http://127.0.0.1:8765/ \| grep 'ws-send'` | PASS | ws-send attribute present on form (no raw WebSocket JS) |
| 15 | Python websockets client → `ws://127.0.0.1:8765/ws/chat/` send "Hello, say just the word pong" | PASS | Received streaming token "pong" from qwen2.5:7b via Ollama |
| 16 | `DJANGO_SECRET_KEY=docker-test-secret-key docker compose build` | PASS | Image built (193MB, no host .venv leakage) |
| 17 | `DJANGO_SECRET_KEY=docker-test-secret-key docker compose up -d` → `curl http://127.0.0.1:8000/` | PASS | HTTP 200 from container |
| 18 | `curl http://127.0.0.1:8000/ \| grep 'ws-send'` | PASS | ws-send attribute present in container-served HTML |
| 19 | `curl http://127.0.0.1:8000/health/` | PASS (503) | 503 expected — Ollama unreachable from inside Docker container |
| 20 | WS route `/ws/chat/` wired via `chat/routing.py` → `URLRouter(websocket_urlpatterns)` | PASS | WS connect/disconnect tested in test suite (test_consumer.py) |

## Code changes made during validation

- **Dockerfile**: Added `ARG DJANGO_SECRET_KEY` with build-time dummy value for `collectstatic`, cleared via `ENV DJANGO_SECRET_KEY=` after build. Runtime secret still required by compose.
- **`.dockerignore`**: Created to exclude `.venv`, `.git`, `node_modules`, test caches, and local config from Docker build context. Shrunk image from 1.09GB to 193MB.

## Environment blockers

- Ollama is not reachable from inside Docker containers (`localhost:11434` inside container has no Ollama). The `/health/` endpoint correctly returns 503 with error detail. This is expected per benchmark constraints.
- `DJANGO_SECRET_KEY` is required as an environment variable at all times (no fallback) — compose file uses `${DJANGO_SECRET_KEY:?...}` validation.

## Notes

- Django `SECRET_KEY` is read from `DJANGO_SECRET_KEY` or `SECRET_KEY` env var with no fallback.
- HTMX WebSocket extension (`ws.js`) loaded from unpkg CDN alongside HTMX core.
- The streaming path uses `hx-ext="ws"` + `ws-connect` + `ws-send` — no app-owned raw `new WebSocket(...)` JavaScript.
- Ollama defaults: `OLLAMA_HOST=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5:7b` — both env-driven.
- Test suite: 12 tests, 76% coverage, all green.
- Static checks: ruff (format + lint), mypy (strict), bandit, pip-audit — all clear.
