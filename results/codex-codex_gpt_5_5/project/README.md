# Ollama Django Chat

Django + Django Channels single-page chat UI. Tokens stream from Ollama through
`langchain_ollama.ChatOllama`, then through a Channels `AsyncWebsocketConsumer`
to HTMX WebSocket out-of-band swaps in the browser.

## Stack

- Python `3.13.13` via `mise.toml`
- Django `6.0.5`
- Django Channels with Daphne ASGI
- `langchain-ollama` `ChatOllama`
- HTMX `hx-ext="ws"` with `ws-connect` and `ws-send`
- Tailwind CSS from the official Tailwind CLI

## Environment

Non-secret defaults are documented in `.env.example`:

- `OLLAMA_HOST=http://localhost:11434`
- `OLLAMA_MODEL=qwen2.5:7b`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]`

`DJANGO_SECRET_KEY` or `SECRET_KEY` must be set at runtime. Generate it locally:

```sh
export DJANGO_SECRET_KEY="$(mise exec -- python -c 'import secrets; print(secrets.token_urlsafe(64))')"
```

## Setup

```sh
mise install
mise exec -- python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
npm install
npm run build:css
ollama pull qwen2.5:7b
```

## Local Run

```sh
export DJANGO_SECRET_KEY="$(mise exec -- python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_DEBUG=True
.venv/bin/python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

ASGI direct run:

```sh
export DJANGO_SECRET_KEY="$(mise exec -- python -c 'import secrets; print(secrets.token_urlsafe(64))')"
.venv/bin/daphne -b 127.0.0.1 -p 8000 chatstream.asgi:application
```

## Tailwind

Source CSS: `assets/css/app.css`

Built CSS: `chat/static/chat/css/app.css`

Build command:

```sh
npm run build:css
```

## Tests And Checks

```sh
.venv/bin/pytest
.venv/bin/coverage run -m pytest
.venv/bin/coverage report
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/bandit -r .
.venv/bin/pip-audit
```

## Docker

```sh
export DJANGO_SECRET_KEY="$(mise exec -- python -c 'import secrets; print(secrets.token_urlsafe(64))')"
docker compose up --build
```

Compose passes through `OLLAMA_HOST` and `OLLAMA_MODEL` with the same defaults as
the app. The image uses `python:3.13.13-slim` and runs Daphne.

## Key Files

- `chat/llm.py`: only production LLM client path, `ChatOllama(...).astream(...)`
- `chat/consumers.py`: `AsyncWebsocketConsumer` streaming tokens to HTML partials
- `chat/templates/chat/index.html`: SPA with HTMX `hx-ext="ws"`, `ws-connect`, and `ws-send`
- `chat/templates/chat/partials/append_token.html`: streamed token DOM append
- `chat/views.py`: chat page and Ollama health path
- `VERIFY.md`: commands run and phase 1 evidence
