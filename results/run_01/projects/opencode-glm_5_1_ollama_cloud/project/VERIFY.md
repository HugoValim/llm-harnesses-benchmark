# Verification Summary

| Command | Result | Evidence / Blocker |
|---|---|---|
| `mise exec python@3.13.13 -- python --version` | PASS | Python 3.13.13 |
| `pip install -r requirements.txt` + dev deps | PASS | All packages installed |
| `python manage.py migrate` | PASS | All migrations applied |
| `pytest chat/ -v` | PASS | 25/25 tests pass |
| `pytest chat/ --cov=chat --cov=config` | PASS | 94% coverage |
| `ruff check chat/ config/ conftest.py` | PASS | All checks passed |
| `ruff format --check chat/ config/ conftest.py` | PASS | 21 files formatted |
| `mypy chat/ config/` | PASS | Success: no issues in 20 files |
| `bandit -r chat/ config/ -x chat/tests` | PASS | 0 issues (0 high, 0 medium, 0 low) |
| `pip-audit` | PASS | No known vulnerabilities found |
| `uvicorn config.asgi:application --port 8767` | PASS | ASGI server boots, HTTP 200 on `/` |
| `curl http://127.0.0.1:8767/` | PASS | Returns HTML with Chat UI |
| `hx-ext="ws"` in rendered HTML | PASS | Present in `_input.html` partial |
| `ws-connect="/ws/chat/"` in rendered HTML | PASS | Present in `_input.html` partial |
| `ws-send` in rendered HTML | PASS | Present in form element |
| `ext/ws.js` loaded in HTML | PASS | Script tag present |
| `new WebSocket` in HTML | NOT FOUND (PASS) | No raw WebSocket JS for streaming path |
| WebsocketCommunicator streaming test | PASS | 5 token chunks + 1 done message received |
| `WebsocketCommunicator` connect/disconnect | PASS | Connect and clean disconnect verified |
| `/health/` endpoint | PASS | Returns `{"reachable": true/false, "host": "..."}` |
| Docker build | PASS | Image built successfully |
| `docker compose up` - HTTP on port 8000 | PASS | Returns 200, HTML with HTMX ws wiring |
| `docker compose up` - WebSocket connect | PASS | Connects, sends message, receives error about Ollama unreachable |
| Ollama reachability inside Docker | BLOCKED | Ollama unreachable from container; `/health/` returns 503-like error; expected environment constraint |

## Environment Notes

- Ollama is not reachable inside Docker containers; this is an expected environment blocker, not a code bug. The app correctly reports this via the `/health/` endpoint and WebSocket error messages.
- `DJANGO_SECRET_KEY` is required at runtime with no hardcoded fallback; Docker CMD validates this with `${DJANGO_SECRET_KEY:?...}`.
- `OLLAMA_HOST` inside Docker defaults to `http://host.docker.internal:11434` for host Ollama access; the app passes it through correctly from the environment.
- Port 11434 was already in use on the host (existing Ollama instance), so the `ollama` compose service could not bind; this did not affect the web container validation.