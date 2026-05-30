# Verification summary

Validated in two phases against the benchmark brief. All commands were run
locally with the project virtualenv (`.venv`, Python **3.13.13** from mise);
dev tooling from `requirements-dev.txt`.

## Phase 2 verification (2026-05-29)

End-to-end validation: dependency install, full test + static-check gate, live
ASGI boot, live WebSocket token streaming against a real Ollama server, and a
full Docker build + compose run. Each command, its result, and the one expected
environment blocker are recorded below.

| # | Command | Result | Evidence / notes |
|---|---------|--------|------------------|
| 1 | `.venv/bin/python --version` | **PASS** | `Python 3.13.13` (venv symlinks mise install; matches `mise.toml`). |
| 2 | `pip install -r requirements-dev.txt` && `pip check` | **PASS** | Deps already satisfied; `No broken requirements found`. |
| 3 | `python manage.py migrate --noinput` | **PASS** | `No migrations to apply` (framework tables already present; chat needs no DB). |
| 4 | `pytest -q` | **PASS** | `22 passed`. Service, consumer (WebsocketCommunicator, multi-chunk, error, disconnect), views/templates, ASGI routing. |
| 5 | `ruff check .` | **PASS** | `All checks passed!` |
| 6 | `ruff format --check .` | **PASS** | `19 files already formatted`. |
| 7 | `mypy` | **PASS** | `Success: no issues found in 12 source files`. |
| 8 | `bandit -c pyproject.toml -r .` | **PASS** | `High: 0, Medium: 0, Low: 0`. |
| 9 | `coverage run -m pytest && coverage report` | **PASS** | Total branch coverage **91.9%**. |
| 10 | `pip-audit -r requirements.txt` | **PASS** | `No known vulnerabilities found`. |
| 11 | `daphne -b 127.0.0.1 -p 8000 config.asgi:application` | **PASS** | `Listening on TCP address 127.0.0.1:8000`. |
| 12 | `curl http://127.0.0.1:8000/` | **PASS** | `HTTP 200`; SPA shell served. |
| 13 | HTMX ws-ext check in rendered HTML | **PASS** | Rendered page contains `hx-ext="ws"`, `ws-connect="/ws/chat/"`, `ws-send`; **0** app-owned `new WebSocket(...)` (only the HTMX `ws.js` extension drives the socket). |
| 14 | `curl http://127.0.0.1:8000/health/` (local) | **PASS** | `HTTP 200` `{"status":"ok","ollama_reachable":true,"model":"qwen2.5:7b"}` — Ollama reachable on the host. |
| 15 | Live WS stream via `ws://127.0.0.1:8000/ws/chat/` (single token) | **PASS** | Connection accepted; real reply reassembled to `'hi'`; `stream_end` partial received (caret cleared). |
| 16 | Live WS stream (multi-token prompt) | **PASS** | **5** OOB token partials streamed → reassembled reply `'Red, Blue, Green'`; `stream_end` received. Proves multi-chunk streaming through the real app path. |
| 17 | `docker build -t ollama-chat:phase2 .` | **PASS** | Image built on `python:3.13.13-slim`; `collectstatic` copied 131 files; runs as non-root `appuser`. |
| 18 | `docker compose up --build -d` | **PASS** | `project-web-1 … Up`, `0.0.0.0:8000->8000/tcp`; CMD `daphne -b 0.0.0.0 -p 8000 config.asgi:application`. `DJANGO_SECRET_KEY` supplied via `$(... token_urlsafe ...)` (never printed, never written to a file). |
| 19 | `curl http://127.0.0.1:8000/` (container) | **PASS** | `HTTP 200`, 2703 bytes; container-served HTML still carries `hx-ext="ws"` / `ws-connect` / `ws-send`. |
| 20 | `curl http://127.0.0.1:8000/health/` (container) | **EXPECTED 503** | `{"status":"degraded","ollama_reachable":false,...}` — Ollama unreachable from inside Docker (see blocker). App reports the dependency failure cleanly; not a code bug. |
| 21 | WS handshake through container (`ws://127.0.0.1:8000/ws/chat/`) | **PASS** | Handshake **accepted**; app emitted user + assistant-container partials → WebSocket route is wired. Token stream then stalls solely because Ollama is unreachable from the container (blocker below). |
| 22 | `docker compose down` | **PASS** | Container + network stopped and removed cleanly; port 8000 released. |

### Environment blocker (phase 2)

- **Ollama is not reachable from inside the Docker container.** `/health/`
  returns `503 degraded` in the container (row 20) and a streamed reply does not
  complete (row 21). This is the documented benchmark constraint, not a defect:
  the container starts, serves HTML on port 8000, and the WebSocket route
  accepts connections. `OLLAMA_HOST` / `OLLAMA_MODEL` remain env-driven in both
  the app (`chat/services.py`) and `docker-compose.yml`
  (`host.docker.internal` via `host-gateway`). Per the brief, the Docker run is
  treated as **passing**. Locally (rows 14–16) Ollama *is* reachable, so live
  multi-chunk streaming was proven against the real model.

## Phase 1 verification

| # | Command | Result | Evidence / notes |
|---|---------|--------|------------------|
| 1 | `mise exec -- python --version` | **PASS** | `Python 3.13.13` (pinned by `mise.toml`). |
| 2 | `pip install -r requirements.txt` | **PASS** | Runtime deps installed into `.venv` (Django 5.1.15, channels 4.2.2, daphne, langchain-ollama 0.3.10, whitenoise, httpx). |
| 3 | `pip install -r requirements-dev.txt` | **PASS** | Dev tooling installed (pytest, pytest-django, pytest-asyncio, ruff, mypy, django-stubs, bandit, coverage, pip-audit). |
| 4 | `npm install` | **PASS** | `@tailwindcss/cli` v4 + `tailwindcss` v4 installed into `node_modules`. |
| 5 | `npm run build:css` (`npx @tailwindcss/cli -i ./assets/css/input.css -o ./static/css/output.css --minify`) | **PASS** | `tailwindcss v4.3.0 … Done in 1s`; `static/css/output.css` regenerated (~12 KB minified). |
| 6 | `python manage.py migrate` | **PASS** | Django framework tables created (sqlite). Chat history itself needs no DB. |
| 7 | `python manage.py collectstatic --noinput` | **PASS** | `131 static files copied … 131 post-processed` (also runs in the Docker build). |
| 8 | `pytest` | **PASS** | `22 passed`. Covers service, consumer (`WebsocketCommunicator`, multi-chunk streaming, error path, multi-turn context, mid-stream disconnect cleanup), views/templates (SPA render, partials, HTMX ws wiring), ASGI routing. |
| 9 | `ruff check .` | **PASS** | `All checks passed!` (rules: E, F, I, UP, B, C90, S, ASYNC, DJ, RUF; max-complexity 12). |
| 10 | `ruff format --check .` | **PASS** | `19 files already formatted`. |
| 11 | `mypy` | **PASS** | `Success: no issues found in 12 source files` (chat + config, `disallow_untyped_defs`, django-stubs plugin). |
| 12 | `bandit -c pyproject.toml -r .` | **PASS** | `No issues identified.` — `High: 0`, Medium: 0, Low: 0. |
| 13 | `coverage run -m pytest && coverage report` | **PASS** | Total branch coverage **91.9%** (`chat/` 87–100% per module; `config/asgi.py` 100%). |
| 14 | `pip-audit -r requirements.txt` | **PASS** | `No known vulnerabilities found`. |
| 15 | `DJANGO_SECRET_KEY=… docker compose config` | **PASS** | Compose file validates; interpolates env, requires `DJANGO_SECRET_KEY` (shell-style `:?`), no literal secret. |
| 16 | `docker build .` | **NOT RUN** | Deferred to phase 2 per the brief (avoid full Docker runtime validation in phase 1). Dockerfile/compose are syntactically validated (rows 7 & 15) and use Python 3.13.13 + daphne. |
| 17 | `docker compose up --build` | **NOT RUN** | Deferred to phase 2. Requires a reachable Ollama server with `qwen2.5:7b` pulled. |
| 18 | End-to-end token stream against a live Ollama server | **NOT RUN** | Requires a running Ollama server (`ollama pull qwen2.5:7b`). The streaming path is covered by unit tests with a faked LLM boundary asserting multiple chunks. |

## Notes on the secret-key strategy

`DJANGO_SECRET_KEY` (or `SECRET_KEY`) is read from the environment. There is **no
hardcoded fallback and no placeholder literal** anywhere in source, `.env*`,
`Dockerfile`, `docker-compose.yml`, or this repo's docs. When no key is set, an
ephemeral key is generated at runtime (`secrets.token_urlsafe`) so tests, static
analysis, `collectstatic`, and local dev work; with `DEBUG=False` and no key a
`RuntimeWarning` is emitted to flag the production misconfiguration.

## Tooling commands of record

```bash
pytest
ruff check .
ruff format --check .
mypy
bandit -c pyproject.toml -r .
coverage run -m pytest && coverage report
pip-audit -r requirements.txt
```

`bandit` reads `[tool.bandit]` from `pyproject.toml` only when invoked with
`-c pyproject.toml`; that config excludes `.venv`, `node_modules`, and `tests`.
Bandit reports **zero** findings at every severity on the shipped code.
