# Django Channels Chat with Ollama

A ChatGPT-style single-page application using Django, Django Channels, and LangChain-Ollama for real-time LLM streaming.

## Requirements

- Python 3.13.13 (managed via mise)
- Ollama running locally with `qwen2.5:7b` pulled
- Node.js (for Tailwind CSS build)

## Setup

```bash
# Install Python via mise
mise install

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment file
cp .env.example .env
# Edit .env — at minimum set DJANGO_SECRET_KEY

# Pull the model
ollama pull qwen2.5:7b
```

## Running Locally

```bash
source .venv/bin/activate

# Run migrations
python manage.py migrate

# Start the ASGI server
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Open http://localhost:8000 in your browser.

## Build Tailwind CSS

```bash
npx --yes @tailwindcss/cli@latest build \
  -i chat/static/css/input.css \
  -o chat/static/css/output.css
```

Source CSS: `chat/static/css/input.css`
Built CSS: `chat/static/css/output.css`

## Running Tests

```bash
source .venv/bin/activate

# Run all tests
pytest

# Run with coverage
coverage run -m pytest
coverage report

# Lint
ruff check .
ruff format --check .

# Type check
mypy chat config

# Security
bandit -r chat config
pip-audit
```

## Docker

```bash
# Set required env vars
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")

# Build and run
docker compose up --build

# The app will be available at http://localhost:8000
```

Environment variables passed through to Docker:
- `DJANGO_SECRET_KEY` — **required**, no default
- `OLLAMA_HOST` — defaults to `http://host.docker.internal:11434`
- `OLLAMA_MODEL` — defaults to `qwen2.5:7b`
- `DJANGO_DEBUG` — defaults to `False`
- `DJANGO_ALLOWED_HOSTS` — defaults to `localhost,127.0.0.1`

## Project Structure

```
.
├── chat/                   # Main Django app
│   ├── consumers.py        # WebSocket consumer
│   ├── llm.py              # LangChain-Ollama service module
│   ├── routing.py           # WebSocket URL routing
│   ├── views.py             # Views + health check
│   ├── templates/chat/      # HTML templates
│   ├── static/css/          # Tailwind CSS (source + built)
│   ├── static/js/           # HTMX + WebSocket extension
│   └── tests/               # Test suite
├── config/                 # Django project settings
│   ├── settings.py
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── mise.toml               # Python version pinning
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | *none (required)* | Django secret key |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |

## Health Check

`GET /health/` returns JSON with Ollama reachability status (no secrets exposed).