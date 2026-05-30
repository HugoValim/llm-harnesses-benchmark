# Chat — Django + Channels + Ollama LLM Streaming

A ChatGPT-style single-page web UI that streams tokens from a local Ollama model through Django Channels WebSockets, using HTMX's WebSocket extension for DOM updates.

## Requirements

- Python 3.13.13 (via mise)
- Node.js (for Tailwind CLI build)
- Ollama running locally with `qwen2.5:7b` pulled

## Setup

```bash
# Install Python via mise
mise install

# Create and activate venv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set required env var
export DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b

# Run migrations (if needed)
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput
```

## Tailwind CSS Build

Source CSS is at `static/src/styles.css`. Built output goes to `static/dist/styles.css`.

```bash
npx @tailwindcss/cli@latest --input static/src/styles.css --output static/dist/styles.css --minify
```

For development with watch mode:

```bash
npx @tailwindcss/cli@latest --input static/src/styles.css --output static/dist/styles.css --watch
```

## Running Locally

```bash
source .venv/bin/activate
export DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Open <http://localhost:8000/> in your browser.

## Ollama Setup

```bash
ollama pull qwen2.5:7b
```

Ensure Ollama is running on `http://localhost:11434` (or set `OLLAMA_HOST`).

## Testing

```bash
DJANGO_SECRET_KEY=test pytest tests/ -v
```

## Docker

```bash
# Build and run
export DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
docker compose up --build

# Or with custom Ollama host
OLLAMA_HOST=http://host.docker.internal:11434 docker compose up --build
```

## Project Structure

```
├── chat/
│   ├── consumers.py      # WebSocket consumer for streaming
│   ├── services/
│   │   └── llm.py        # ChatOllama wrapper
│   ├── views.py           # Index + health views
│   ├── urls.py            # URL routes
│   └── routing.py         # WebSocket routes
├── config/
│   ├── settings.py
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
├── templates/chat/
│   └── index.html          # SPA template
├── static/
│   ├── src/styles.css      # Tailwind source
│   ├── dist/styles.css     # Built CSS
│   └── vendor/             # HTMX + WS extension
├── tests/
│   ├── test_views.py
│   ├── test_consumer.py
│   ├── test_llm_service.py
│   └── test_templates.py
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | *(required)* | Django secret key. Generate: `python -c 'import secrets; print(secrets.token_urlsafe(50))'` |
| `DEBUG` | `false` | Django debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model identifier |

## Verification

See [VERIFY.md](VERIFY.md) for the full verification summary with toolchain results.
