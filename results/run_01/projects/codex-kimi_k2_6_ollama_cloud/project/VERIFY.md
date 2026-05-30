# Verification Summary

## Setup

| Command | Result | Evidence / Notes |
|---|---|---|
| `python -m venv .venv --upgrade` | Pass | Python 3.13.13 active |
| `pip install -e ".[dev]"` | Fix applied | Added `[tool.setuptools] packages = ["chat", "config"]` to `pyproject.toml` to resolve flat-layout discovery error |
| `python manage.py migrate` | Pass | contenttypes migrations applied |

## Tests

| Command | Result | Evidence / Notes |
|---|---|---|
| `DJANGO_SECRET_KEY=test pytest -v` | Pass | 8 passed in ~1.85s |
| `ruff check .` | Pass | All checks passed |
| `ruff format --check .` | Pass | 18 files already formatted |
| `mypy chat tests` | Pass | Success: no issues found in 12 source files |
| `bandit -r . -c pyproject.toml` | Pass | No issues identified |
| `DJANGO_SECRET_KEY=test coverage run -m pytest && coverage report` | Pass | 94% total coverage |
| `pip-audit` | Pass | No known vulnerabilities found |

## Local ASGI server

| Command | Result | Evidence / Notes |
|---|---|---|
| `python manage.py collectstatic --noinput` | Pass | 1 static file copied to staticfiles |
| `daphne -b 127.0.0.1 -p 8000 config.asgi:application` | Pass | Boots on port 8000 |
| `curl http://127.0.0.1:8000/` | Pass | Returns HTML 200; contains `hx-ext="ws"`, `ws-connect="/ws/chat/"`, `ws-send=""` |
| `curl http://127.0.0.1:8000/health/` | Pass | `{"ollama_reachable": true}` (Ollama reachable from host) |
| WebSocket `ws://127.0.0.1:8000/ws/chat/` | Pass | Connected, sent `"Say hello"`, received 9 real tokens across `bot_start` ... `bot_end` |

## Docker

| Command | Result | Evidence / Notes |
|---|---|---|
| `docker build -t chatapp .` | Pass | Image `chatapp:latest` built (1.05GB) |
| `docker compose up -d` | Pass | Container `project-web-1` starts on port 8000 |
| `curl http://127.0.0.1:8000/` | Pass | Returns HTML 200; contains `hx-ext="ws"`, `ws-connect="/ws/chat/"`, `ws-send=""` |
| `curl http://127.0.0.1:8000/health/` | Expected blocker | `{"ollama_reachable": false}` — Ollama is **not reachable from inside Docker** in this benchmark environment. This is an expected environmental constraint, not a code bug. |
| WebSocket `ws://127.0.0.1:8000/ws/chat/` | Pass | Connected; returns error token because Ollama is unreachable inside Docker, proving the WebSocket route is wired end-to-end |

## Environment Blockers

- **Ollama inside Docker**: The Ollama host (`host.docker.internal:11434`) is not resolvable from within the container in this environment, so `/health/` returns `ollama_reachable: false` and chat streaming returns an error token. The container still serves HTML and accepts WebSocket connections correctly.

## Fixes Applied During Validation

- `pyproject.toml`: Added `[tool.setuptools] packages = ["chat", "config"]` to fix editable install failure caused by automatic package discovery picking up `static/` and `templates/`.
