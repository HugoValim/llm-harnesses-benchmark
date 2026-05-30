# Django Channels Chat with Ollama Streaming

ChatGPT-style single-page chat UI powered by Django, Django Channels, HTMX WebSocket extension, and LangChain Ollama for real-time token streaming.

## Prerequisites

- Python 3.13.13 (managed via `mise`)
- Node.js (for Tailwind CLI)
- [Ollama](https://ollama.ai) running locally with `qwen2.5:7b` pulled

```bash
ollama pull qwen2.5:7b
```

## Local Setup

```bash
mise install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.in
```

Set required environment variables:

```bash
export DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
export DJANGO_DEBUG=True
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
```

Or copy and fill `.env.example`:

```bash
cp .env.example .env
# Edit .env - set DJANGO_SECRET_KEY
```

## Tailwind CSS Build

Source CSS: `static/src/input.css`
Built CSS: `static/css/app.css`

```bash
npx @tailwindcss/cli@4 --input static/src/input.css --output static/css/app.css
```

For development with watch mode:

```bash
npx @tailwindcss/cli@4 --input static/src/input.css --output static/css/app.css --watch
```

## Running

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

Open http://localhost:8000

## Testing

```bash
source .venv/bin/activate
export DJANGO_SECRET_KEY=test-key-for-pytest
pytest chat/ -v
pytest chat/ --cov=chat --cov=config --cov-report=term-missing
```

## Linting & Type Checking

```bash
ruff check chat/ config/ conftest.py
ruff format --check chat/ config/ conftest.py
mypy chat/ config/
bandit -r chat/ config/ -x chat/tests
```

## Security Audit

```bash
pip-audit
```

## Docker

```bash
docker compose up --build
```

Set `DJANGO_SECRET_KEY` before starting:

```bash
export DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
docker compose up --build
```

## Architecture

- **Django + Channels**: ASGI app with `AsyncWebsocketConsumer` for WebSocket streaming
- **HTMX + ws extension**: Browser connects via `hx-ext="ws"` / `ws-connect` / `ws-send`
- **LangChain Ollama**: `ChatOllama` from `langchain_ollama` streams tokens via `.astream()`
- **Token flow**: Ollama → LangChain → WebSocket → HTMX → DOM

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | (required) | Django secret key. Generate with `django-admin startproject` or `get_random_secret_key()` |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API host |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |