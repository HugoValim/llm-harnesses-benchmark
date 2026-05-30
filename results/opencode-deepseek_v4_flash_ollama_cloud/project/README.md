# Chat - Django Channels + Ollama

Single-page chat app using Django Channels, HTMX WebSocket extension, Tailwind CSS, and LangChain Ollama.

## Requirements

- Python 3.13.13
- [Ollama](https://ollama.ai) running locally with a model pulled:
  ```bash
  ollama pull qwen2.5:7b
  ```
- Node.js (for Tailwind CSS CLI)

## Local setup

```bash
# Generate a secret key and export it
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")

# Create virtualenv and install
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build Tailwind CSS
npx tailwindcss -i static/src/input.css -o static/css/output.css --minify

# Run migrations (for Django internals)
python manage.py migrate

# Start the dev server (using Daphne for ASGI)
daphne -b 0.0.0.0 -p 8000 chat_project.asgi:application
```

Open http://localhost:8000 in a browser.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | *(required)* | Django secret key; generate with `secrets.token_urlsafe(64)` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |
| `DJANGO_DEBUG` | `False` | Enable Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | Comma-separated allowed hosts |

## Docker

```bash
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
docker compose up --build
```

## Tests

```bash
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
python -m pytest -v --cov --cov-config=.coveragerc
```

## Toolchain

```bash
ruff check .
ruff format --check .
mypy chat chat_project --config-file mypy.ini
bandit -r . -c .bandit
coverage run -m pytest && coverage report --fail-under=70
pip-audit
```
