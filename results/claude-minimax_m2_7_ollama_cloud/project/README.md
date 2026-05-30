# Ollama Chat

A ChatGPT-style single-page chat application powered by Django, Django Channels, and Ollama via LangChain.

## Features

- Real-time token streaming from Ollama to browser
- WebSocket-based communication with HTMX for partial DOM updates
- Chat history maintained per browser session
- Health check endpoint for Ollama reachability
- Tailwind CSS for styling
- Docker and Docker Compose for deployment

## Prerequisites

- Python 3.13 (managed via `mise.toml`)
- [Ollama](https://ollama.ai/) running locally or accessible via `OLLAMA_HOST`
- Docker (for containerized deployment)

## Setup (Local Development)

### 1. Install dependencies

```bash
# Create virtual environment with Python 3.13
python3 -m venv .venv
source .venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### 2. Pull Ollama model

```bash
ollama pull qwen2.5:7b
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your Ollama settings if needed
```

### 4. Build Tailwind CSS

```bash
npm install
node_modules/.bin/tailwindcss init -p
node_modules/.bin/tailwindcss -i static/css/src.css -o static/css/output.css
```

### 5. Run migrations and server

```bash
python manage.py migrate
python -c "from ollama_chat.asgi import application; print('ASGI config OK')"
daphne -b 0.0.0.0 -p 8000 ollama_chat.asgi:application
```

The app will be available at `http://localhost:8000`.

## Running Tests

```bash
DJANGO_SECRET_KEY=test-secret .venv/bin/python -m pytest chat/tests.py -v
```

## Running with Docker

### Build and run with Docker Compose

```bash
docker compose up --build
```

Or build manually:

```bash
docker build -t ollama-chat .
docker run -p 8000:8000 \
  -e DJANGO_SECRET_KEY=<your-secret-key> \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -e OLLAMA_MODEL=qwen2.5:7b \
  ollama-chat
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (required) | Django secret key |
| `DEBUG` | `false` | Enable debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |

## Architecture

- **Django + Django Channels**: Web framework with WebSocket support
- **daphne**: ASGI server for production
- **langchain-ollama**: LLM client with streaming support
- **HTMX + WebSocket extension**: Partial DOM updates
- **Tailwind CSS**: Utility-first styling (built via official CLI)

## Project Structure

```
.
├── chat/
│   ├── consumers.py    # WebSocket consumer with streaming
│   ├── llm_service.py  # Ollama/LangChain client wrapper
│   ├── views.py        # Django views (chat page, health)
│   ├── urls.py         # URL routing
│   ├── routing.py      # WebSocket URL routing
│   ├── tests.py        # pytest test suite
│   └── conftest.py     # pytest fixtures
├── ollama_chat/
│   ├── settings.py     # Production settings
│   ├── test_settings.py # Test settings
│   ├── asgi.py         # ASGI application
│   └── urls.py         # Root URL configuration
├── templates/chat/
│   ├── index.html      # Main chat SPA
│   └── _*.html         # Template partials
├── static/
│   ├── css/
│   │   ├── src.css     # Tailwind source
│   │   └── output.css  # Built Tailwind CSS
│   └── js/
│       ├── htmx.min.js
│       ├── ws_extension.js
│       └── ws.js        # WebSocket client
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── ruff.toml
├── mypy.toml
├── setup.cfg
└── mise.toml
```