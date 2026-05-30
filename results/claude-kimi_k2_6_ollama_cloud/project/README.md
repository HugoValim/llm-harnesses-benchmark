# Ollama Chat

A Django + Django Channels single-page chat application that streams tokens from a local Ollama instance through HTMX WebSocket extension.

## Prerequisites

- Python 3.13.13 (managed via mise)
- Node.js (for Tailwind CSS CLI)
- Ollama running locally with a model pulled, e.g.:
  ```bash
  ollama pull qwen2.5:7b
  ```

## Setup

1. Install Python 3.13.13 via mise:
   ```bash
   mise install
   ```

2. Create a virtualenv and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file from `.env.example` and set `DJANGO_SECRET_KEY`:
   ```bash
   cp .env.example .env
   # Generate a secret key:
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   # Add the generated value to .env as DJANGO_SECRET_KEY
   ```

4. Build Tailwind CSS:
   ```bash
   ./tailwindcss-linux-x64 --input chat/static/css/input.css --output chat/static/css/tailwind.css
   ```

5. Collect static files:
   ```bash
   python manage.py collectstatic --noinput
   ```

6. Run migrations:
   ```bash
   python manage.py migrate --noinput
   ```

## Local run

```bash
python manage.py runserver
```

Or with an ASGI server:
```bash
daphne -b 127.0.0.1 -p 8000 chat_project.asgi:application
```

Open http://localhost:8000 in your browser.

## Test commands

```bash
pytest
ruff check .
ruff format --check .
mypy chat/
bandit -r .
coverage run -m pytest
coverage report
pip-audit
```

## Docker run

```bash
docker compose up --build
```

The compose file reads `DJANGO_SECRET_KEY` from your environment. Ensure it is set before running:
```bash
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
docker compose up --build
```
