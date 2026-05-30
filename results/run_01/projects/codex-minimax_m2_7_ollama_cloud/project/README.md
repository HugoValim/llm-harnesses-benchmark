# Chat Project — Django + Channels + Ollama Streaming

ChatGPT-style single-page chat UI powered by a real Ollama LLM with token-level streaming through Django Channels and HTMX WebSocket extension.

## Prerequisites

- Python 3.13 (managed by `mise`)
- Node.js (for Tailwind CLI — installed separately)
- Ollama running locally or reachable at `OLLAMA_HOST`

## Setup

### 1. Install Python dependencies

```bash
eval "$(mise hook-env -s bash)"
pip install -e ".[dev]"
```

### 2. Pull the Ollama model

```bash
ollama pull qwen2.5:7b
```

### 3. Set environment variables

```bash
cp .env.example .env
# edit .env and set DJANGO_SECRET_KEY
```

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. Build Tailwind CSS

```bash
npm install -g tailwindcss@3.4.17
tailwindcss -i static/css/src.css -o static/css/styles.css --minify
```

Re-run after editing `static/css/src.css` or `tailwind.config.js`.

### 5. Run the app locally

```bash
export DJANGO_SECRET_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
daphne -b 127.0.0.1 -p 8000 chat_project.asgi:application
```

Then open http://localhost:8000

## Tests

```bash
DJANGO_SECRET_KEY="test-secret-key-for-pytest-32chars-xx" \
OLLAMA_HOST="http://localhost:11434" \
OLLAMA_MODEL="qwen2.5:7b" \
pytest .
```

## Toolchain

```bash
# Lint + format
ruff check .
ruff format --check .

# Type check
mypy chat chat_project

# Security scan
bandit -r .

# Coverage
coverage run -m pytest .
coverage report

# Audit dependencies
pip-audit
```

## Docker

### Build and run

```bash
docker compose up --build
```

Open http://localhost:8000

### Without compose (manual)

```bash
docker build -t chat-web .
docker run -p 8000:8000 \
  -e DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=qwen2.5:7b \
  chat-web
```

> **Note:** If Ollama runs on the host machine, use `host.docker.internal` (Linux Docker) or `host-gateway` as the `OLLAMA_HOST`.

## Architecture

```
chat/
  consumers.py    — AsyncWebsocketConsumer, token streaming
  routing.py      — WS URL patterns
  services/
    llm.py       — ChatOllama wrapper, multi-turn history
  views.py        — home view, health check
  urls.py         — HTTP URL patterns
```

Streaming path: browser → HTMX ws extension → WebSocket → `ChatConsumer` → `ChatService` → LangChain `ChatOllama.astream()` → token chunks → WebSocket → browser.

## Configuration Reference

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | required | No fallback |
| `SECRET_KEY` | fallback for `DJANGO_SECRET_KEY` | For env compatibility |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `OLLAMA_HOST` | `http://localhost:11434` | Not a secret |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Not a secret |
