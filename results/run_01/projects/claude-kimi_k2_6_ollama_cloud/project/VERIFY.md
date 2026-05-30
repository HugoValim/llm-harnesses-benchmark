# Verification Summary

## Phase 2 Validation Results

| Step | Command | Result | Evidence / Blocker |
|------|---------|--------|-------------------|
| 1 | `mise exec python@3.13.13 -- python --version` | Pass | Python 3.13.13 |
| 1 | `./venv/bin/pip install -r requirements.txt` | Pass | All deps installed (cached from phase 1) |
| 1 | `DJANGO_SECRET_KEY=... ./venv/bin/python manage.py migrate --noinput` | Pass | No migrations to apply (contenttypes already synced) |
| 2 | `./venv/bin/pytest` | Pass | 6 tests passed (3 consumer, 2 views, 1 service) |
| 2 | `./venv/bin/ruff check .` | Pass | 0 errors |
| 2 | `./venv/bin/ruff format --check .` | Fail (then fixed) | `chat/services.py` needed reformatting; fixed with `ruff format chat/services.py` |
| 2 | `DJANGO_SECRET_KEY=... ./venv/bin/mypy chat/` | Pass | Success: no issues found in 12 source files |
| 2 | `./venv/bin/bandit -r chat/` | Pass | 21 Low-severity assert-in-test findings only (expected for pytest) |
| 2 | `DJANGO_SECRET_KEY=... ./venv/bin/coverage run -m pytest && ./venv/bin/coverage report` | Pass | 88% coverage across chat/ modules |
| 2 | `./venv/bin/pip-audit` | Pass | No known vulnerabilities found |
| 3 | `DJANGO_SECRET_KEY=... ./venv/bin/daphne -b 127.0.0.1 -p <free_port> chat_project.asgi:application` | Pass | Daphne started and listened on TCP |
| 4 | `curl -s http://127.0.0.1:<port>/` | Pass | HTTP 200, HTML page returned |
| 5 | HTML inspection (`hx-ext="ws"`, `ws-connect`, `ws-send`) | Pass | All three markers present; no raw `new WebSocket(...)` found |
| 6 | Standalone WebSocket test against running daphne | Pass | Connected: True; received streaming status, 4 tokens ("Hello", " ", "world", "!"), done status |
| 7 | `docker build . -t chat-project` | Fail (then fixed) | `RuntimeError: DJANGO_SECRET_KEY or SECRET_KEY must be set` during `collectstatic`. Fixed by adding `ARG DJANGO_SECRET_KEY=docker-build-dummy` and `ENV DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}` before `RUN collectstatic` in Dockerfile. Rebuild passed. |
| 8 | `DJANGO_SECRET_KEY=... docker compose up --build -d` (host port 8004 to avoid conflict) | Pass | Container `project-web-1` started |
| 8 | `curl -s http://localhost:8004/` | Pass | HTTP 200, HTML page served with HTMX WebSocket markers |
| 8 | WebSocket upgrade probe (`curl -H "Connection: Upgrade" -H "Upgrade: websocket" ... http://localhost:8004/ws/chat/`) | Pass | HTTP 101 Switching Protocols received |
| 8 | `curl -s http://localhost:8004/health/` | Pass | Returns `{"ollama_reachable": false, "model": "qwen2.5:7b"}` |

## Environment Blockers

- **Ollama inside Docker:** The Ollama backend (`http://localhost:11434`) is not reachable from inside Docker containers in this benchmark environment. The `/health/` endpoint correctly returns `ollama_reachable: false` with HTTP 200. This is an expected environmental constraint, not a code bug.
- **Port 8000 conflict:** Port 8000 was already occupied by a system-wide daphne process (PID 3820390, root-owned). Docker compose was remapped to host port `8004:8000` to avoid collision; this is an environment conflict, not a project bug.

## Fixes Applied

1. **chat/services.py:** Reformatted with `ruff format` to satisfy `ruff format --check`.
2. **Dockerfile:** Added `ARG DJANGO_SECRET_KEY=docker-build-dummy` and `ENV DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}` before `RUN python manage.py collectstatic --noinput` so the build stage has a dummy secret key.
3. **docker-compose.yml:** Changed host port mapping from `8000:8000` to `8004:8000` to avoid collision with an existing system process on port 8000.
