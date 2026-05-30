# ChatLLM

Django + Django Channels chat application with streaming LLM responses via LangChain + Ollama.

## Requirements

- Python 3.13+
- Node.js 18+ (for Tailwind CLI build)
- [Ollama](https://ollama.ai) with a pulled model (default: `qwen2.5:7b`)

## Setup

```bash
# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install daphne

# Environment variables (copy and edit)
cp .env.example .env
# Generate a secret key:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
# Set DJANGO_SECRET_KEY in .env

# Tailwind CSS
npm install
npx tailwindcss -i chat/static/chat/css/input.css -o chat/static/chat/css/output.css

# Run migrations
python manage.py migrate
```

## Run locally

```bash
source .venv/bin/activate
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
export DJANGO_DEBUG=True

daphne -b 0.0.0.0 -p 8000 chat_project.asgi:application
```

Open http://localhost:8000 in your browser.

## Run with Docker

```bash
# Pull the model first (outside Docker or in the ollama container)
ollama pull qwen2.5:7b

# Set required secret key
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"

# Start services
docker compose up --build
```

## Tailwind CSS build

```bash
npx tailwindcss -i chat/static/chat/css/input.css -o chat/static/chat/css/output.css --watch
```

## Tests

```bash
source .venv/bin/activate
export DJANGO_SECRET_KEY=testkey
python -m pytest -v
```

## Verification commands

See [VERIFY.md](VERIFY.md) for the full verification gate output.

## Project structure

```
chat/                 # Django app
  consumers.py        # WebSocket AsyncWebsocketConsumer
  llm_service.py      # ChatOllama streaming service
  routing.py          # WebSocket URL routing
  views.py            # HTTP views (chat page + health check)
  templates/chat/     # HTML templates with HTMX ws-ext
  static/chat/css/    # Tailwind source + built CSS
  tests/              # pytest tests
chat_project/         # Django project config
  settings.py         # Settings (SECRET_KEY from env)
  asgi.py             # ASGI application with Channels
  urls.py             # URL configuration
Dockerfile            # Production Docker image
docker-compose.yml    # App + Ollama services
```
