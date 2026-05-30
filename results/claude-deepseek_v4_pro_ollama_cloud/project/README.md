# LLM Chat

Django + Django Channels chat application with Ollama LLM streaming.

Single-page chat UI using HTMX + WebSocket extension, Tailwind CSS v4, and LangChain Ollama integration. Real-time token streaming from Ollama through WebSocket to browser.

## Prerequisites

- Python 3.13.13 (mise configured: `mise install`)
- [Ollama](https://ollama.com/) running locally or at a reachable host

Pull the default model:

```bash
ollama pull qwen2.5:7b
```

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for tests and tooling

# Set required environment variable
export DJANGO_SECRET_KEY=your-random-secret-key

# Build Tailwind CSS
./tailwindcss -i chat/static/src/input.css -o chat/static/css/output.css --minify

# Run migrations (Django defaults)
python manage.py migrate

# Start development server
python manage.py runserver
```

Open http://localhost:8000 in your browser.

## Tailwind CSS

Source: `chat/static/src/input.css`
Built: `chat/static/css/output.css`

Build command:

```bash
./tailwindcss -i chat/static/src/input.css -o chat/static/css/output.css --minify
```

Watch mode for development:

```bash
./tailwindcss -i chat/static/src/input.css -o chat/static/css/output.css --watch
```

The Tailwind CLI binary (`tailwindcss`) is the v4 standalone release for Linux x64.

## Running tests

```bash
# Run all tests with coverage
coverage run -m pytest && coverage report

# Lint and format check
ruff check . && ruff format --check .

# Type check
mypy .

# Security audit
bandit -r chat/ -c pyproject.toml
pip-audit
```

## Docker

```bash
# Build and run
docker compose up --build

# The app will be available at http://localhost:8000
```

Environment variables passed through compose:

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (required) | Django secret key |
| `DEBUG` | `False` | Django debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |

## Environment variables

All configuration is environment-driven. Copy `.env.example` as a starting point:

```bash
cp .env.example .env
```

`OLLAMA_HOST` and `OLLAMA_MODEL` configure the LLM backend. `DJANGO_SECRET_KEY` is required — there is no hardcoded fallback.
