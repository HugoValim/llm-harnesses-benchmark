# AI Chat - Django + Channels + Ollama

A real-time chat application built with Django, Django Channels, and LangChain-Ollama. Features token streaming from Ollama models to a ChatGPT-style web UI.

## Features

- **Real-time streaming**: Tokens stream from Ollama -> LangChain -> WebSocket -> browser UI
- **ChatGPT-style UI**: Clean, modern interface with Tailwind CSS
- **Multi-turn context**: Conversation history maintained per WebSocket session
- **HTMX + WebSocket**: Partial DOM updates via HTMX WebSocket extension
- **AsyncWebsocketConsumer**: Full async streaming with Channels
- **Environment-driven config**: No secrets in source code

## Requirements

- Python 3.13.13 (via mise) or Python 3.12+
- Node.js 18+ (for Tailwind CSS build)
- Ollama running locally with `qwen2.5:7b` model pulled

## Quick Start

### 1. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Node.js dependencies (for Tailwind)

```bash
npm install
npm run build:css
```

### 3. Set up environment

```bash
cp .env.example .env
# Edit .env and set DJANGO_SECRET_KEY
```

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. Pull the Ollama model

```bash
ollama pull qwen2.5:7b
```

### 5. Run migrations and start server

```bash
python manage.py migrate
python manage.py runserver
```

Visit http://localhost:8000/

## Tailwind CSS Build

Build minified CSS:
```bash
npm run build:css
```

Watch for changes during development:
```bash
npm run watch:css
```

## Running Tests

```bash
source venv/bin/activate
pytest
```

Run with coverage:
```bash
coverage run -m pytest
coverage report
```

## Code Quality Tools

### Ruff (lint + format)
```bash
ruff check .
ruff format .
```

### mypy (type checking)
```bash
mypy .
```

### bandit (security audit)
```bash
bandit -r chat/ benchmark_chat/
```

### pip-audit (dependency vulnerabilities)
```bash
pip-audit
```

## Docker

### Build and run with docker-compose

```bash
# Set required environment variables
export DJANGO_SECRET_KEY="your-secret-key"
export OLLAMA_HOST="http://host.docker.internal:11434"

# Build and start
docker compose up --build
```

### Docker health check

The container includes a health check at `/health/` endpoint.

## Project Structure

```
.
├── benchmark_chat/       # Django project settings
│   ├── settings.py       # Django + Channels config
│   ├── urls.py           # Root URL routing
│   └── asgi.py           # ASGI + WebSocket routing
├── chat/                 # Chat application
│   ├── consumers.py      # AsyncWebsocketConsumer
│   ├── views.py          # SPA + health check views
│   ├── routing.py        # WebSocket URL patterns
│   ├── services/
│   │   └── llm.py        # ChatOllama streaming service
│   └── tests/
│       ├── test_consumer.py
│       ├── test_views.py
│       └── test_llm_service.py
├── templates/chat/
│   └── chat.html         # Main SPA template
├── static/
│   ├── css/
│   │   ├── source.css    # Tailwind source
│   │   └── styles.css    # Built CSS
│   └── js/
│       └── chat.js       # WebSocket client
├── Dockerfile
├── docker-compose.yml
├── package.json          # Tailwind CSS deps
├── tailwind.config.js
├── requirements.txt
├── pytest.ini
├── ruff.toml
├── mypy.ini
└── .coveragerc
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (required) | Django secret key - no default |
| `SECRET_KEY` | (required) | Alternative name for secret key |
| `DEBUG` | `False` | Debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Model to use |

## API Endpoints

### GET `/`
Main chat SPA view.

### GET `/health/`
Health check for Ollama connectivity. Returns JSON:
```json
{
  "healthy": true,
  "host": "http://localhost:11434",
  "model": "qwen2.5:7b"
}
```

### GET `/config/`
Non-sensitive configuration for the frontend. Returns JSON:
```json
{
  "ollama_host": "http://localhost:11434",
  "ollama_model": "qwen2.5:7b",
  "debug": false
}
```

### WebSocket `/ws/chat/`
Real-time chat WebSocket endpoint.

**Client -> Server:**
```json
{"message": "Hello!"}
```

**Server -> Client:**
```json
{"type": "connection_ack", "message": "Connected"}
{"type": "response_start"}
{"type": "token", "content": "Hello"}
{"type": "token", "content": " there"}
{"type": "response_end", "complete_message": "Hello there"}
{"type": "error", "message": "...", "code": "..."}
```

## Security Notes

- `SECRET_KEY` must come from environment - no hardcoded fallback
- `DEBUG` defaults to `False` in production
- `ALLOWED_HOSTS` defaults to localhost only
- No secrets exposed in `/config/` endpoint
- Django security middleware enabled by default (CSRF, SecurityMiddleware, etc.)

## License

MIT
