# Chat — Django + Channels + Ollama streaming

ChatGPT-style single-page chat app with real token streaming via HTMX WebSocket extension.

**Stack:** Django 6.0, Django Channels 4.3, daphne, langchain-ollama, Tailwind CSS v4 (standalone CLI), HTMX 2.0 + ws extension.

## Quick start (local)

```bash
# 1. Python 3.13 via mise
mise install

# 2. Create venv + install deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest pytest-django pytest-asyncio ruff mypy bandit coverage pip-audit django-stubs

# 3. Build Tailwind CSS
./twcli --input static_src/input.css --output static/css/output.css

# 4. Generate a secret key (never hardcode)
export DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
export DJANGO_DEBUG=True

# 5. Pull the model (default: qwen2.5:7b)
ollama pull qwen2.5:7b

# 6. Run
.venv/bin/daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Open http://127.0.0.1:8000/

## Tailwind CSS build

Source: `static_src/input.css` → Built: `static/css/output.css`

```bash
# One-shot
./twcli --input static_src/input.css --output static/css/output.css

# Watch mode (development)
./twcli --input static_src/input.css --output static/css/output.css --watch
```

The Tailwind CLI binary (`twcli`) is v4.1.6 for linux-x64. Download from:
https://github.com/tailwindlabs/tailwindcss/releases

## Configuration (environment)

| Variable              | Default                 | Notes                        |
|-----------------------|-------------------------|------------------------------|
| `DJANGO_SECRET_KEY`   | *(required, no default)*| Generate with secrets.token  |
| `DJANGO_DEBUG`        | `False`                 | Set `True` for development   |
| `DJANGO_ALLOWED_HOSTS`| `localhost,127.0.0.1`   | Comma-separated              |
| `OLLAMA_HOST`         | `http://localhost:11434`| Ollama server URL            |
| `OLLAMA_MODEL`        | `qwen2.5:7b`            | Model name                   |

See `.env.example` for the documented template.

## Docker

```bash
# Build + run (requires DJANGO_SECRET_KEY in env)
export DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
docker compose up --build
```

Dockerfile builds Tailwind and collects static assets at image build time.

For local Ollama, set `OLLAMA_HOST=http://host.docker.internal:11434` when running inside Docker.

## Test & toolchain commands

```bash
# Tests
DJANGO_SECRET_KEY=test-key .venv/bin/pytest tests/ -v

# Coverage
DJANGO_SECRET_KEY=test-key .venv/bin/coverage run -m pytest tests/ -q
.venv/bin/coverage report

# Lint + format
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Type check
.venv/bin/mypy chat/ config/

# Security scan
.venv/bin/bandit -r chat/ config/ manage.py

# Dependency audit
.venv/bin/pip-audit
```

## Project structure

```
├── chat/                  # Django app
│   ├── consumers.py       # AsyncWebsocketConsumer — LLM streaming
│   ├── routing.py         # WebSocket URL routing
│   ├── services.py        # LLM service (langchain-ollama wrapper)
│   └── views.py           # HTTP views (SPA + health check)
├── config/                # Django project
│   ├── asgi.py            # ASGI config with Channels routing
│   ├── settings.py        # Env-driven, no secrets
│   └── urls.py            # URL config
├── static/                # Built static assets
│   └── css/output.css     # Tailwind-built CSS
├── static_src/            # Tailwind source
│   └── input.css
├── templates/             # Django templates
│   ├── base.html          # Base layout with HTMX + ws extension
│   └── chat/chat.html     # SPA chat page
├── tests/                 # pytest test suite
│   ├── conftest.py
│   ├── test_consumer.py   # WebSocket consumer tests
│   ├── test_services.py   # LLM service tests
│   └── test_views.py      # View + template tests
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.txt
├── pyproject.toml         # Tooling config (ruff, mypy, bandit, coverage, pytest)
├── .env.example
├── README.md
├── VERIFY.md
└── twcli                  # Tailwind CLI binary
```

## ollama pull note

Default model is `qwen2.5:7b`. Pull it before running:

```bash
ollama pull qwen2.5:7b
```

Set `OLLAMA_MODEL` to any other model available in your Ollama instance.
