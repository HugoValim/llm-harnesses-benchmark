# Django Chat App with Streaming LLM

A ChatGPT-style chat application built with Django, Django Channels, and LangChain Ollama for real-time token streaming.

## Features

- Real-time token streaming from Ollama LLM via WebSocket
- ChatGPT-style single-page UI
- HTMX with WebSocket extension for partial DOM updates
- Tailwind CSS for styling
- Async WebSocket consumer for streaming

## Prerequisites

- Python 3.13.13 (via mise)
- Node.js (for Tailwind CSS build)
- Ollama running locally or remotely

## Setup

### 1. Install Python dependencies

```bash
mise use python@3.13.13
mise exec python@3.13.13 -- pip install -r requirements.txt
```

### 2. Install Node dependencies and build Tailwind CSS

```bash
npm install
npm run build:css
```

### 3. Configure environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `DJANGO_SECRET_KEY` - Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `OLLAMA_HOST` - Default: `http://localhost:11434`
- `OLLAMA_MODEL` - Default: `qwen2.5:7b`

### 4. Pull Ollama model

```bash
ollama pull qwen2.5:7b
```

### 5. Run migrations

```bash
mise exec python@3.13.13 -- python manage.py migrate
```

## Running Locally

```bash
mise exec python@3.13.13 -- python manage.py runserver
```

Visit http://localhost:8000

## Running with Docker

```bash
docker-compose up --build
```

## Tailwind CSS Build

Source CSS: `chat/static/css/src.css`
Built CSS: `chat/static/css/styles.css`

Build command:
```bash
npm run build:css
```

## Testing

Run all tests:
```bash
mise exec python@3.13.13 -- pytest chat/tests/ -v
```

Run with coverage:
```bash
mise exec python@3.13.13 -- coverage run -m pytest chat/tests/
mise exec python@3.13.13 -- coverage report
```

## Code Quality

### Ruff (lint + format)

```bash
mise exec python@3.13.13 -- ruff check .
mise exec python@3.13.13 -- ruff format --check .
```

### Bandit (security)

```bash
mise exec python@3.13.13 -- bandit -r . -c .bandit.yml
```

### Coverage

```bash
mise exec python@3.13.13 -- coverage run -m pytest chat/tests/
mise exec python@3.13.13 -- coverage report
```

### pip-audit

```bash
mise exec python@3.13.13 -- pip-audit
```

## Project Structure

```
.
├── chat/                  # Chat application
│   ├── consumers.py       # WebSocket consumer for streaming
│   ├── llm_service.py     # LangChain Ollama service
│   ├── routing.py         # WebSocket URL routing
│   ├── views.py           # HTTP views
│   ├── urls.py            # URL patterns
│   ├── templates/chat/    # HTML templates
│   ├── static/css/        # Tailwind CSS
│   └── tests/             # Test suite
├── config/                # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── asgi.py            # ASGI configuration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── package.json
└── .env.example
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key (required) | None |
| `DEBUG` | Debug mode | `False` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `qwen2.5:7b` |

## License

MIT
