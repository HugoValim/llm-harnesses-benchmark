# Verification Summary

## Environment

- OS: Linux (Ubuntu-based)
- Python: 3.13.13 via mise
- mise version: 2026.5.2 linux-x64
- Docker version: 29.4.2
- Docker Compose version: v5.1.3

## Phase 2 Commands Run & Results

| # | Command | Result | Evidence |
|---|---|---|---|
| 1 | `mise use python@3.13.13` | **PASS** | `Python 3.13.13` output |
| 2 | `python -m venv .venv` | **PASS** (reused) | `.venv` present, python 3.13.13 symlinked |
| 3 | `pip install django channels[daphne] langchain-ollama pytest ...` | **PASS** | All deps installed |
| 4 | `DJANGO_SECRET_KEY=test python manage.py migrate` | **PASS** | 18 migrations applied |
| 5 | `DJANGO_SECRET_KEY=test pytest -v --tb=short` | **PASS** | 7 passed |
| 6 | `ruff check .` | **PASS** | "All checks passed!" |
| 7 | `ruff format --check .` | **PASS** | "21 files already formatted" |
| 8 | `mypy chat_app --ignore-missing-imports --no-error-summary` | **PASS** | No errors |
| 9 | `bandit -r chat_app chat_project -ll -ii` | **PASS** | "No issues identified" |
| 10 | `DJANGO_SECRET_KEY=test coverage run -m pytest -q` | **PASS** | 7 passed |
| 11 | `coverage report` | **PASS** | 82.41% total coverage |
| 12 | `pip-audit --local --format=json` | **PASS** | "No known vulnerabilities found" |
| 13 | `DJANGO_SECRET_KEY=test daphne -b 0.0.0.0 -p 8000 chat_project.asgi:application` | **PASS** | Booted PID 3464640 |
| 14 | `curl -s -o /tmp/index.html -w '%{http_code}' http://localhost:8000/` | **PASS** | HTTP 200, HTML returned |
| 15 | `grep 'hx-ext="ws"' /tmp/index.html` | **PASS** | Found |
| 16 | `grep 'ws-connect="/ws/chat/"' /tmp/index.html` | **PASS** | Found |
| 17 | `grep 'ws-send' /tmp/index.html` | **PASS** | Found |
| 18 | `grep 'ws.js' /tmp/index.html` | **PASS** | Found |
| 19 | WebSocket script `/tmp/verify_ws.py` to `ws://localhost:8000/ws/chat/` | **PASS** | Connection accepted, tokens streamed, `data-done="true"` received |
| 20 | `docker build -t chat-app:latest .` | **PASS** | Image built successfully |
| 21 | `DJANGO_SECRET_KEY=... docker compose up -d --build` | **PASS** | Container started on port 8000 |
| 22 | `curl -s -o /tmp/docker_index.html -w '%{http_code}' http://localhost:8000/` | **PASS** | HTTP 200 from Docker container |
| 23 | `docker ps` | **PASS** | `project-web-1 Up ... 0.0.0.0:8000->8000/tcp` |
| 24 | WebSocket to Docker-hosted app | **PASS** | `WebSocket streaming verified successfully.` |

## Environment Blockers / Notes

- **Ollama inside Docker**: The local Ollama server is reachable on the host (`localhost:11434`) but not from inside the Docker container. The `/health/` endpoint inside Docker returns `{"ollama_reachable": false, "model": "qwen2.5:7b"}` — this is an expected environmental constraint, not a code bug. The application boots and serves HTML/WebSocket correctly.
- **Django SECRET_KEY**: Required via environment variable (`DJANGO_SECRET_KEY` or `SECRET_KEY`) with no hardcoded fallback. Build-time `collectstatic` uses a temporary build key that is not baked into the final image runtime.
