# Verification summary (phase 1 + phase 2)

| Command | Result | Evidence / blocker |
|---------|--------|-------------------|
| `mise exec -- python --version` | **pass** | Python 3.13.13 |
| `pip install -e ".[dev]"` | **pass** | Editable install with dev extras |
| `python manage.py migrate --noinput` | **pass** | SQLite migrations applied (host + Docker entrypoint) |
| `npx @tailwindcss/cli -i static/src/input.css -o static/css/app.css --minify` | **pass** (phase 1) | Built `static/css/app.css` |
| `pytest` | **pass** | 10 passed |
| `ruff check .` | **pass** | All checks passed |
| `ruff format --check .` | **pass** | 23 files formatted |
| `mypy` | **pass** | No issues in 17 source files |
| `bandit -r . -c pyproject.toml` | **pass** | No issues identified |
| `coverage run -m pytest && coverage report` | **pass** | Total coverage **80%** |
| `pip-audit` | **pass** | No known vulnerabilities (`ollama-chat` local pkg skipped) |
| `daphne -b 127.0.0.1 -p 8765 config.asgi:application` | **pass** | Server listening; logs show TCP :8765 |
| `curl http://127.0.0.1:8765/` | **pass** | HTTP 200; page contains `hx-ext="ws"`, `ws-connect="/ws/chat/"`, `ws-send` |
| HTMX vs raw `WebSocket` JS | **pass** | No `new WebSocket` / `WebSocket(` in `static/`; streaming via HTMX ws extension |
| `curl http://127.0.0.1:8765/health/ollama/` | **pass** | HTTP 200, `"reachable": true` (host Ollama up) |
| `python scripts/ws_probe.py` | **pass** | Mocked stream: 3 token frames (`alpha`, `beta`, `gamma`) |
| Live WS → daphne + Ollama | **pass** | `ws://127.0.0.1:8765/ws/chat/` returned user + assistant start + token frame (`Hello`) |
| `docker build -t ollama-chat:phase2 .` | **pass** | Image built successfully |
| `docker compose up --build -d` | **pass** | Container `project-web-1` up, daphne on `0.0.0.0:8000` |
| `curl http://127.0.0.1:8000/` | **pass** | HTTP 200; HTMX ws wiring present in HTML |
| `curl http://127.0.0.1:8000/health/ollama/` | **pass (env)** | HTTP **503**, `"reachable": false` — Ollama not reachable from container at `host.docker.internal:11434` (expected benchmark constraint, not app bug) |
| Docker WS `ws://127.0.0.1:8000/ws/chat/` | **pass** | Handshake accepted; user-message HTML frame received; full multi-token stream not awaited (Ollama unreachable in container) |
| Browser manual E2E | **not run** | Automated curl/WS probes used instead |

## Phase 2 notes

- **Host Ollama:** reachable at `http://localhost:11434` during validation (`/api/tags` → 200).
- **Docker Ollama:** health endpoint correctly reports failure with 503 and a clear `detail` string; compose still serves the SPA on port 8000.
- **WebSocket proof:** mocked path via `scripts/ws_probe.py` and pytest `WebsocketCommunicator`; live token frame observed against local daphne when Ollama is available.

## Commands to reproduce

```bash
mise exec -- python --version
source .venv/bin/activate
pip install -e ".[dev]"
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python manage.py migrate --noinput
pytest && ruff check . && ruff format --check . && mypy && bandit -r . -c pyproject.toml
coverage run -m pytest && coverage report
pip-audit

# ASGI (terminal 1)
export DEBUG=true
daphne -b 127.0.0.1 -p 8765 config.asgi:application

# Probes (terminal 2)
curl -i http://127.0.0.1:8765/
python scripts/ws_probe.py

# Docker
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
docker compose up --build -d
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/health/ollama/
```
