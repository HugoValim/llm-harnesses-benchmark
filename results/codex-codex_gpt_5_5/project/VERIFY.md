# Verification

| Command | Result | Evidence or blocker |
| --- | --- | --- |
| `mise exec -- python --version` | Pass | `Python 3.13.13`. |
| `test -x .venv/bin/python && .venv/bin/python --version || true` | Pass | Existing `.venv` uses `Python 3.13.13`. |
| `mise exec -- python -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e '.[dev]'` | Pass | Project and dev deps installed in local virtualenv. |
| `DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')" .venv/bin/python manage.py check` | Pass | `System check identified no issues (0 silenced).` |
| `DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')" .venv/bin/python manage.py migrate --noinput` | Pass | `No migrations to apply.` |
| `.venv/bin/pytest` | Pass | `7 passed in 1.01s`. |
| `.venv/bin/ruff check .` | Pass | `All checks passed!` |
| `.venv/bin/ruff format --check .` | Pass | `26 files already formatted`. |
| `.venv/bin/mypy` | Pass | `Success: no issues found in 12 source files`. |
| `.venv/bin/bandit -r .` | Pass | `No issues identified`; skipped test `B101` per `.bandit`. |
| `.venv/bin/coverage run -m pytest && .venv/bin/coverage report` | Pass | `7 passed in 2.11s`; `TOTAL 276 stmts, 81% coverage`. |
| `.venv/bin/pip-audit` | Pass | `No known vulnerabilities found`; local editable package skipped because it is not on PyPI. |
| `DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')" .venv/bin/daphne -b 127.0.0.1 -p 8000 chatstream.asgi:application` | Pass | Daphne logged `Listening on TCP address 127.0.0.1:8000`. |
| `curl -fsS http://127.0.0.1:8000/` | Pass | HTTP page returned 200 content. |
| `html="$(curl -fsS http://127.0.0.1:8000/)"; printf '%s\n' "$html" \| grep -F 'hx-ext="ws"'; printf '%s\n' "$html" \| grep -F 'ws-connect="/ws/chat/"'; printf '%s\n' "$html" \| grep -F 'ws-send'; printf '%s\n' "$html" \| grep -F 'htmx-ext-ws'` | Pass | All HTMX WebSocket extension markers present. |
| `if rg -n "new WebSocket" chat chatstream assets; then exit 1; else echo 'no app-owned raw WebSocket in source'; fi` | Pass | `no app-owned raw WebSocket in source`. |
| `curl -fsS -m 2 "${OLLAMA_HOST:-http://localhost:11434}"` | Pass | Local Ollama returned `Ollama is running`. |
| `curl -fsS http://127.0.0.1:8000/health/ollama/` | Pass | `{"status": "reachable", "ollama_status": 200, "model": "qwen2.5:7b"}`. |
| `.venv/bin/pytest tests/test_consumers.py::test_consumer_streams_multiple_chunks -q` | Pass | WebSocket route `/ws/chat/` accepted a mocked connection and streamed multiple chunks: `1 passed`. |
| `docker build -t ollama-django-chat:verify .` | Pass | Image built and tagged `ollama-django-chat:verify`. |
| `DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')" docker compose up --build` | Pass | Compose built `project-web`, started `web-1`, and logged `Listening on TCP address 0.0.0.0:8000`. |
| `curl -fsS http://127.0.0.1:8000/` against Compose | Pass | HTML reachable on published port; rendered page contains `hx-ext="ws"`, `ws-connect="/ws/chat/"`, and `ws-send`. |
| `.venv/bin/python - <<'PY'` WebSocket socket probe to `ws://localhost:8000/ws/chat/` | Pass | Compose route returned `HTTP/1.1 101 Switching Protocols`, then an app error frame for invalid JSON. |
| `curl -sS -m 3 -w '\nstatus=%{http_code}' http://127.0.0.1:8000/health/ollama/` against Compose | Expected blocker | Returned `status=503` with `{"status": "unreachable", "detail": "<urlopen error [Errno 111] Connection refused>"}`. This matches the benchmark constraint that Ollama is unavailable from inside Docker containers. |
| `docker compose ps --status running` | Blocked | Compose refused config interpolation because `DJANGO_SECRET_KEY` was unset for this command; rerun below with ephemeral env. |
| `DJANGO_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')" docker compose ps -a` | Pass | `project-web-1` is `Exited (0)` after shutdown; pre-existing orphan `chat-ollama` remains running and was not modified. |
