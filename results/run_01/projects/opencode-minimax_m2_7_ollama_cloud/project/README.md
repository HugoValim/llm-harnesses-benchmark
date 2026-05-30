# ChatGPT-style Web Application

A Django + Django Channels web application with real-time token streaming from Ollama.

## Requirements

- Python 3.13 (via mise)
- Ollama running locally or via Docker
- Node.js for Tailwind CSS build

## Local Setup

### 1. Install Python dependencies

```bash
# Set up Python 3.13 via mise
mise use python:3.13.13

# Install dependencies
pip install django channels daphne langchain-ollama pytest pytest-django pytest-asyncio ruff mypy bandit coverage pip-audit
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env and set DJANGO_SECRET_KEY
```

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Pull Ollama model

```bash
ollama pull qwen2.5:7b
```

### 4. Build Tailwind CSS

```bash
tailwindcss -i ./chat/static/css/src/styles.css -o ./chat/static/css/styles.css --minify
```

Or use npx:
```bash
npx tailwindcss -i ./chat/static/css/src/styles.css -o ./chat/static/css/styles.css --minify
```

### 5. Run database migrations

```bash
python manage.py migrate
```

### 6. Run the development server

```bash
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Or with Django's runserver (for development only):
```bash
python manage.py runserver 8000 --settings=config.settings
```

## Test Commands

```bash
# Run all tests
pytest

# Run with coverage
coverage run -m pytest
coverage report

# Lint with ruff
ruff check .

# Format check
ruff format --check .

# Type check
mypy chat config

# Security check
bandit -r .

# Audit dependencies
pip-audit
```

## Docker Run

### Build and run with Docker Compose

```bash
# Start Ollama and web services
docker-compose up --build

# Run in detached mode
docker-compose up -d
```

### Pull Ollama model inside container

```bash
docker exec ollama ollama pull qwen2.5:7b
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | Required | Django secret key |
| `DEBUG` | False | Enable debug mode |
| `ALLOWED_HOSTS` | localhost,127.0.0.1 | Allowed hosts |
| `OLLAMA_HOST` | http://localhost:11434 | Ollama server URL |
| `OLLAMA_MODEL` | qwen2.5:7b | Ollama model name |

## Architecture

- `chat/consumers.py` - AsyncWebsocketConsumer for WebSocket handling
- `chat/llm_service.py` - Ollama service wrapper using langchain-ollama
- `chat/views.py` - Django views for the chat UI
- `chat/templates/` - HTML templates with HTMX WebSocket extension
- `chat/static/` - Tailwind CSS and JavaScript files

## Verification

See [VERIFY.md](./VERIFY.md) for detailed verification commands and results.