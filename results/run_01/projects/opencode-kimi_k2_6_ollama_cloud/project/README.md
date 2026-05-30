# Chat Project

This is a Django + Django Channels chat application with real-time token streaming from Ollama via LangChain, using the HTMX WebSocket extension and Tailwind CSS.

## Prerequisites

- mise (manages Python 3.13.13)
- Ollama running locally or remotely

## Quick start

```bash
# 1. Install Python 3.13.13 with mise
mise install

# 2. Create a virtual environment
mise exec python -- python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e '.[dev]'

# 4. Set a Django secret key
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")

# 5. Run migrations
python manage.py migrate

# 6. Build Tailwind CSS
tailwindcss -i static/src/input.css -o static/css/output.css --minify

# 7. Start the ASGI server
daphne -b 0.0.0.0 -p 8000 chat_project.asgi:application
```

## Tailwind CSS

- Source CSS: `static/src/input.css`
- Built CSS: `static/css/output.css`
- Build command:
  ```bash
  tailwindcss -i static/src/input.css -o static/css/output.css --minify
  ```

## Tests

```bash
DJANGO_SECRET_KEY=test pytest
```

## Linting, type checking, security

```bash
ruff check .
ruff format --check .
mypy chat_app --ignore-missing-imports --no-error-summary
bandit -r . -x ./.venv
coverage run -m pytest
coverage report
pip-audit
```

## Docker

```bash
# Ensure DJANGO_SECRET_KEY is exported, then:
docker compose up --build
```

## Ollama

Before using the chat, pull the default model:

```bash
ollama pull qwen2.5:7b
```

## Environment variables

See `.env.example` for non-secret variables.

## Verification evidence

See `VERIFY.md` for the exact commands that were run and their pass/fail results.
