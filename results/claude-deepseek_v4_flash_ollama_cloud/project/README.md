# Chat App

Django Channels + Ollama ChatGPT-style chat SPA.

## Prerequisites

- Python 3.13+ (via [mise](https://mise.jdx.dev) or system)
- Node.js 18+ (for Tailwind CLI)
- [Ollama](https://ollama.ai) with a model pulled:
  ```bash
  ollama pull qwen2.5:7b
  ```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DJANGO_SECRET_KEY in production
```

## Tailwind CSS build

```bash
npx tailwindcss -i chat/static/src/input.css -o static/css/output.css
```

Watch mode during development:
```bash
npx tailwindcss -i chat/static/src/input.css -o static/css/output.css --watch
```

## Run locally

```bash
source .venv/bin/activate
python manage.py migrate
OLLAMA_HOST=http://localhost:11434 OLLAMA_MODEL=qwen2.5:7b \
  DJANGO_SECRET_KEY=dev-secret-key \
  DJANGO_DEBUG=True \
  python manage.py runserver
```

Open http://localhost:8000.

## Run tests

```bash
source .venv/bin/activate
pytest
# With coverage:
coverage run -m pytest && coverage report
```

## Lint & format

```bash
ruff check .
ruff format --check .
mypy chat config
bandit -r chat config
pip-audit
```

## Docker

```bash
# Build
docker compose build

# Run (Ollama must be accessible from inside container)
OLLAMA_HOST=http://host.docker.internal:11434 docker compose up -d
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | (required) | Django secret key |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |
