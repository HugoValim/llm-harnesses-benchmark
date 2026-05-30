# Chat - Django Channels + Ollama Streaming

Real-time chat application with token streaming from Ollama via LangChain and Django Channels.

## Requirements

- Python 3.13.13 (via mise)
- Node.js (for Tailwind CLI)
- Ollama server running locally or remotely

## Environment Setup

### 1. Install Python

```bash
mise use python@3.13.13
```

### 2. Install Dependencies

```bash
mise exec python@3.13.13 -- pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `DJANGO_SECRET_KEY` - Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `OLLAMA_HOST` - Defaults to `http://localhost:11434`
- `OLLAMA_MODEL` - Defaults to `qwen2.5:7b`

### 4. Pull Ollama Model

```bash
ollama pull qwen2.5:7b
```

### 5. Run Migrations

```bash
mise exec python@3.13.13 -- python manage.py migrate
```

### 6. Build Tailwind CSS

```bash
npx @tailwindcss/cli -i ./static/css/input.css -o ./static/css/styles.css
```

### 7. Run Development Server

```bash
mise exec python@3.13.13 -- python manage.py runserver
```

Visit http://localhost:8000

## Running Tests

```bash
mise exec python@3.13.13 -- pytest chatapp/ -v
```

With coverage:

```bash
mise exec python@3.13.13 -- pytest chatapp/ --cov=chatapp --cov-report=term-missing
```

## Code Quality

### Ruff (lint + format)

```bash
mise exec python@3.13.13 -- ruff check .
mise exec python@3.13.13 -- ruff format --check .
```

### Mypy (type checking)

```bash
mise exec python@3.13.13 -- mypy chatapp/
```

### Bandit (security)

```bash
mise exec python@3.13.13 -- bandit -r chatapp/ -ll
```

### Pip Audit

```bash
mise exec python@3.13.13 -- pip-audit
```

## Docker

### Build and Run

```bash
docker-compose up --build
```

### Environment Variables

Pass environment variables to docker-compose:

```bash
DJANGO_SECRET_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())") \
OLLAMA_HOST=http://host.docker.internal:11434 \
OLLAMA_MODEL=qwen2.5:7b \
docker-compose up
```

## Architecture

- **Frontend**: ChatGPT-style SPA with HTMX WebSocket extension
- **Backend**: Django + Django Channels ASGI
- **Streaming**: AsyncWebsocketConsumer with LangChain ChatOllama
- **CSS**: Tailwind CSS v4 via official CLI

## Project Structure

```
.
├── chatapp/                 # Main Django app
│   ├── consumers.py         # WebSocket consumer for streaming
│   ├── llm_service.py       # ChatOllama service layer
│   ├── routing.py           # WebSocket URL routing
│   ├── tests.py             # View and template tests
│   ├── test_consumer.py     # WebSocket consumer tests
│   └── views.py             # HTTP views
├── chatproject/             # Django project config
│   ├── asgi.py              # ASGI application
│   ├── settings.py          # Django settings
│   └── urls.py              # URL configuration
├── templates/
│   ├── chat.html            # Main chat SPA
│   └── health.html          # Health check page
├── static/css/
│   ├── input.css            # Tailwind source
│   └── styles.css           # Built CSS
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── pyproject.toml           # Tool configuration
└── .env.example
```

## API Endpoints

- `GET /` - Chat SPA
- `GET /health/` - Health check page
- `GET /api/health/` - JSON health check with Ollama reachability
- `WS /ws/chat/` - WebSocket endpoint for streaming

## Security Notes

- `SECRET_KEY` must be provided via environment variable
- `DEBUG` defaults to `False` in production
- `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`
- CSRF protection enabled
- No secrets stored in source code or `.env.example`
