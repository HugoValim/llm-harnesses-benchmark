# Django Channels Chat Application

A ChatGPT-style single-page chat UI using Django, Django Channels, HTMX WebSocket
extension, and Tailwind CSS. LLM integration via `langchain-ollama.ChatOllama`.

## Architecture

```
Browser (HTMX + ws.js)  <--WebSocket-->  Daphne/ASGI  <-->  ChatConsumer
                                                                    |
                                                              chat/services.py
                                                                    |
                                                          langchain_ollama.ChatOllama
                                                                    |
                                                                Ollama
```

## Prerequisites

- [mise](https://mise.jdx.dev/) (Python 3.13.13)
- [Ollama](https://ollama.com/) running locally or at a reachable host
- [Tailwind CSS CLI](https://tailwindcss.com/blog/standalone-cli) (v3.x standalone binary)
- The ollama model pulled: `ollama pull qwen2.5:7b`

## Setup (local development)

```bash
# Generate a Django secret key (never commit it)
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Create .env (not committed)
cat > .env <<'EOF'
DJANGO_SECRET_KEY=<paste the generated key>
DEBUG=true
EOF

# Create virtual environment with Python 3.13.13
mise exec python@3.13.13 -- python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Build Tailwind CSS
tailwindcss -i chat/static/chat/css/tailwind.src.css -o chat/static/chat/css/tailwind.css --minify

# Run Django checks
DJANGO_SECRET_KEY=<key> DEBUG=true python manage.py check

# Start the server (daphne)
DJANGO_SECRET_KEY=<key> DEBUG=true daphne config.asgi:application
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | **required** | Django secret key (generate with Django's `get_random_secret_key()`) |
| `SECRET_KEY` | **required** (fallback) | Alternative name for Django secret key |
| `DEBUG` | `false` | Set to `true` for local development |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated host list |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |

## Ollama

Pull the default model before running:

```bash
ollama pull qwen2.5:7b
```

## Tailwind CSS build

```bash
tailwindcss -i chat/static/chat/css/tailwind.src.css -o chat/static/chat/css/tailwind.css --minify
```

Source CSS: `chat/static/chat/css/tailwind.src.css`
Built CSS: `chat/static/chat/css/tailwind.css`
Config: `tailwind.config.js`

## Testing

```bash
DJANGO_SECRET_KEY=test-key DEBUG=true pytest chat/tests.py -v
```

## Tooling

| Tool | Command |
|---|---|
| ruff lint | `ruff check .` |
| ruff format | `ruff format --check .` |
| mypy | `mypy chat/ config/ --ignore-missing-imports` |
| bandit | `bandit -r chat/ config/` |
| coverage | `coverage run -m pytest chat/tests.py && coverage report` |
| pip-audit | `pip-audit` |

## Docker

```bash
# Set DJANGO_SECRET_KEY in your environment (not in a file)
export DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

docker compose up --build
```

The Docker image uses Python 3.13.13-slim and daphne as the ASGI server.
