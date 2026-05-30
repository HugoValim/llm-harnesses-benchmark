# Django + Channels Ollama Chat (benchmark)

Single-page “ChatGPT-style” UI built with **Django**, **Django Channels**, **HTMX (WebSocket extension)**, **Tailwind CSS**, and **LangChain `ChatOllama`** streaming tokens over a WebSocket.

## Requirements

- **Python 3.13.13** (this repo pins it via `mise.toml`)
- A running **Ollama** server (defaults below)
- Node/npm **only** if you want to rebuild Tailwind CSS locally

## Quickstart (local)

1. Trust + install Python via `mise` (first time only):

```bash
mise trust mise.toml
mise install
python -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

2. Create a local env file (do **not** commit `.env`):

```bash
cp .env.example .env
```

3. Set a real Django secret in `.env`:

- `DJANGO_SECRET_KEY` (preferred) **or** `SECRET_KEY`

There is **no** hardcoded fallback in `chat_project/settings.py`.

4. Pull the default model (first run):

```bash
ollama pull qwen2.5:7b
```

5. Migrate + run ASGI:

```bash
python manage.py migrate --noinput
daphne -b 127.0.0.1 -p 8000 chat_project.asgi:application
```

Open `http://127.0.0.1:8000/`.

### Ollama configuration (env-driven)

- `OLLAMA_HOST` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `qwen2.5:7b`)

These are **not** secrets, but they must remain environment-driven (see `.env.example` and `docker-compose.yml`).

### Optional local flags

- `DJANGO_DEBUG=true` to enable Django `DEBUG` (default: `false`)
- `DJANGO_ALLOWED_HOSTS` comma-separated hosts (default: `localhost,127.0.0.1`)

## Tailwind CSS (official CLI)

Source file:

- `styles/tailwind.input.css`

Built output (committed for reproducible Docker builds):

- `chat/static/chat/css/tailwind.css`

Install JS deps once:

```bash
npm install
```

Build command (also available as an npm script):

```bash
npm run build:css
```

Equivalent raw CLI:

```bash
npx tailwindcss -i ./styles/tailwind.input.css -o ./chat/static/chat/css/tailwind.css --minify
```

## Tests + static analysis

```bash
pytest
ruff check .
ruff format --check .
mypy chat chat_project
bandit -q -r chat --exclude '*/tests/*' && bandit -q -r chat_project
coverage run -m pytest
coverage report -m
pip-audit
```

## Docker

Build:

```bash
docker build -t django-channels-chat:local .
```

Run (requires `DJANGO_SECRET_KEY` in your shell or compose env):

```bash
export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
docker compose up --build
```

Notes:

- Compose defaults `OLLAMA_HOST` to `http://host.docker.internal:11434` (see `docker-compose.yml`) so a host-running Ollama is reachable from Linux containers via `extra_hosts`.
- On pure Linux, if that mapping fails for your setup, set `OLLAMA_HOST` explicitly to a reachable URL (for example your LAN IP).

## Health check

- `GET /health/` returns JSON including Ollama reachability **without** echoing secrets.
- `GET /health/live/` returns plain `ok` if Django is up.

## Verification evidence

See `VERIFY.md` for phase 1 + phase 2 end-to-end validation commands, pass/fail notes, and environment blockers (including Docker/Ollama reachability expectations).
