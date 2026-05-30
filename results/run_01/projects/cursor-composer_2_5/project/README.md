# Ollama Chat (Django + Channels)

ChatGPT-style single-page chat that streams tokens from a local [Ollama](https://ollama.com/) server through LangChain `ChatOllama`, Django Channels, and HTMX WebSocket partial updates.

## Prerequisites

- [mise](https://mise.jdx.dev/) with Python **3.13.13** (see `mise.toml`)
- [Ollama](https://ollama.com/) running locally
- Node.js (for the Tailwind CLI build only)

Pull the default model once:

```bash
ollama pull qwen2.5:7b
```

## Configuration

Copy `.env.example` to `.env` and set non-secret values. Generate a Django secret (never commit it):

```bash
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DEBUG=true
```

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Model tag for `ChatOllama` |
| `DJANGO_SECRET_KEY` / `SECRET_KEY` | *(required)* | Django signing secret |
| `DEBUG` | `false` | Set `true` for local dev |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |

## Local setup

```bash
mise install
mise exec -- python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate
```

### Tailwind CSS (official CLI)

Install frontend tooling and build static CSS:

```bash
npm install
npx @tailwindcss/cli -i static/src/input.css -o static/css/app.css --minify
```

Re-run the same `npx` command after template or source CSS changes.

### Run the dev server

```bash
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DEBUG=true
python manage.py runserver
```

Open http://127.0.0.1:8000/ and chat. Health check: http://127.0.0.1:8000/health/ollama/

## Tests and quality tools

```bash
pytest
ruff check .
ruff format --check .
mypy
bandit -r . -c pyproject.toml
coverage run -m pytest && coverage report
pip-audit
```

## Docker

Build static CSS on the host first (the image copies `static/css/app.css`).

```bash
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
docker compose up --build
```

The app listens on port **8000** via **daphne** (ASGI). `OLLAMA_HOST` defaults to `http://host.docker.internal:11434` in Compose so the container can reach Ollama on the host.

## Architecture

- `chat/views.py` — SPA shell and `/health/ollama/`
- `chat/consumers.py` — `AsyncWebsocketConsumer` streaming HTMX HTML fragments
- `chat/services/llm.py` — `ChatOllama` client, `.astream()`, reachability probe
- `templates/chat/` — page + partials (`ws-connect`, `ws-send`, OOB swaps)
- `static/` — Tailwind source (`static/src/input.css`) and built `static/css/app.css`

Streaming path: **Ollama → LangChain `ChatOllama.astream` → WebSocket consumer → HTMX `hx-ext="ws"` DOM updates** (no app-owned `WebSocket` JavaScript).

## Verification

See [VERIFY.md](VERIFY.md) for commands run during implementation and pass/fail results.
