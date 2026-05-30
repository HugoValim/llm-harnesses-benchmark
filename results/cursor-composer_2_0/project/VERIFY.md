# Verification log

Commands were executed from the repository root on this machine unless noted.

## Environment

- `mise` Python: `3.13.13` (see `mise.toml`)
- First-time `mise` note: this repo’s `mise.toml` must be trusted (`mise trust mise.toml`) before `mise install` works.
- Project venv: `.venv/` created via `python -m venv .venv` + `pip install -e ".[dev]"`

---

## Phase 1 (initial implementation)

| Command | Result |
| --- | --- |
| `mise install` | PASS (after `mise trust mise.toml`) |
| `.venv/bin/pip install -e ".[dev]"` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/python manage.py check` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/python manage.py migrate --noinput` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/pytest` | PASS (**7** tests) |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/ruff check .` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/ruff format --check .` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/mypy chat chat_project` | PASS |
| `bandit -q -r chat --exclude '*/tests/*' && bandit -q -r chat_project` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/coverage run -m pytest` then `.venv/bin/coverage report -m` | PASS (≈80% stmts on `chat/` modules) |
| `.venv/bin/pip-audit` | PASS (no known vulnerabilities reported for this venv at audit time) |
| `docker build -t django-channels-chat:local .` | PASS |
| `DJANGO_SECRET_KEY=dev-only-for-compose-config-check docker compose config` | PASS |

---

## Phase 2 (`benchmark-followup-v3.1` — end-to-end validation)

### 1) Virtualenv + deps + migrations

| Command | Result |
| --- | --- |
| `mise install` | PASS |
| `.venv/bin/pip install -e ".[dev]"` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/python manage.py migrate --noinput` | PASS (`No migrations to apply.`) |

### 2) Automated tests + static checks

| Command | Result |
| --- | --- |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/pytest` | PASS (**7** tests) |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/ruff check .` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/ruff format --check .` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/mypy chat chat_project` | PASS |
| `bandit -q -r chat --exclude '*/tests/*' && bandit -q -r chat_project` | PASS |
| `SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" .venv/bin/coverage run -m pytest` then `.venv/bin/coverage report -m` | PASS |
| `.venv/bin/pip-audit` | PASS |

### 3–5) Local ASGI boot + HTTP + WebSocket streaming

| Step | Command / action | Result |
| --- | --- | --- |
| ASGI boot | `SECRET_KEY=… DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost .venv/bin/daphne -b 127.0.0.1 -p 8011 chat_project.asgi:application` (background) | PASS (process started) |
| HTTP | `curl -sS -o /tmp/chat_page.html -w "%{http_code}" http://127.0.0.1:8011/` | PASS (`http_code=200`) |
| Ollama reachability (host) | `curl -sS -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:11434/api/tags` | PASS (`200`) |
| WS probe deps | `.venv/bin/pip install websocket-client` | PASS (installed into `.venv` for this validation only; **not** declared in `pyproject.toml`) |
| WS streaming | `websocket-client` script: connect to `ws://127.0.0.1:8011/ws/chat/` with `origin="http://127.0.0.1:8011"`, send JSON `{"message": ...}`, count frames | PASS (**4** frames received, `>= 3`) |
| WS note | `recv()` ended with `WebSocketTimeoutException` after idle | Expected (server finished sending; client used 2s recv timeout) |

### 6) Docker image build

| Command | Result |
| --- | --- |
| `docker build -t django-channels-chat:phase2 .` | PASS |

### 7) Docker Compose (runtime wiring)

Prerequisite: `export DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"` (value not logged here).

| Command | Result |
| --- | --- |
| `docker compose up --build -d` | PASS |
| `curl -sS -o /tmp/docker_index.html -w "%{http_code}" http://127.0.0.1:8000/` | PASS (`200`) |
| `curl -sS --max-time 10 http://127.0.0.1:8000/health/` | PASS (`HTTP 200`, JSON `status=degraded`, `ollama.ok=false`, `error=http_error:ConnectTimeout`) |
| WS streaming (through published port) | same `websocket-client` probe against `ws://127.0.0.1:8000/ws/chat/` with `origin="http://127.0.0.1:8000"` | PASS (**4** frames, `>= 3`) |
| `docker compose down --remove-orphans` | PASS |

---

## Notes / blockers

- Django requires `DJANGO_SECRET_KEY` or `SECRET_KEY` at process start; there is intentionally **no** default in `chat_project/settings.py`.
- Local convenience: create a `.env` (not committed) from `.env.example` and set `DJANGO_SECRET_KEY` there; `manage.py` / ASGI / WSGI load `.env` via `python-dotenv` when present.
- `docker compose config` / `docker compose up` require `DJANGO_SECRET_KEY` to be set in your environment (Compose uses `${DJANGO_SECRET_KEY:?...}`).
- **Docker Ollama constraint (expected):** the container cannot reach the host’s Ollama at `http://host.docker.internal:11434` in this environment (`ConnectTimeout`). `/health/` reports `degraded` — **not treated as a product failure** per benchmark-followup rules. HTML + WebSocket wiring still verified on port `8000`.
- Pull the default model before first chat on the host: `ollama pull qwen2.5:7b`.
