# Chat App

Django + Django Channels chat UI with real-time Ollama streaming via WebSocket.

## Requirements

- Python 3.13.13 (managed via mise)
- Ollama running locally or remotely

## Setup

```bash
mise install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Generate a secret key and export it:

```bash
export DJANGO_SECRET_KEY=$(openssl rand -base64 48)
```

Pull the default model before running:

```bash
ollama pull qwen2.5:7b
```

## Tailwind CSS build

Build static CSS from source:

```bash
./tailwindcss -i static/src/input.css -o static/dist/output.css --minify
```

Watch mode:

```bash
./tailwindcss -i static/src/input.css -o static/dist/output.css --watch
```

## Local run

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
python manage.py migrate
python manage.py runserver
```

## Test commands

```bash
export DJANGO_SECRET_KEY=test
pytest -v
```

## Docker run

```bash
export DJANGO_SECRET_KEY=$(openssl rand -base64 48)
docker compose up --build
```

Override Ollama host if needed:

```bash
OLLAMA_HOST=http://host.docker.internal:11434 docker compose up --build
```

## Verification

See `VERIFY.md` for the full verification summary and command results.
