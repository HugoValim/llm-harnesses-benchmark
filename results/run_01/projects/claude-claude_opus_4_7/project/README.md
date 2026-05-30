# Ollama Chat

A ChatGPT-style single-page chat application that streams tokens from a local
[Ollama](https://ollama.com) model in real time. Built with **Django** +
**Django Channels** (ASGI WebSockets), **HTMX** with its WebSocket extension for
partial DOM updates, **Tailwind CSS** (official CLI) for styling, and
**`langchain-ollama`** as the only LLM client path.

No Django REST Framework, no authentication, no Celery — just a focused,
streaming chat UI.

## How it works

```
Browser (HTMX ws-ext)  ──ws──▶  ChatConsumer (AsyncWebsocketConsumer)
       ▲                              │
       │  HTML partials (OOB swaps)   ▼
       └──────────────────────  OllamaChatService.astream_reply()
                                      │  langchain_ollama.ChatOllama.astream(...)
                                      ▼
                                  Ollama server
```

- The page connects once via `hx-ext="ws"` + `ws-connect="/ws/chat/"`.
- The composer form uses `ws-send`; each submit sends the message over the socket.
- `chat/consumers.py` streams the reply through `chat/services.py`
  (`langchain_ollama.ChatOllama.astream`) and pushes one rendered HTML partial
  per token. HTMX swaps each partial out-of-band (`hx-swap-oob`) into the
  transcript, so the answer appears token by token.
- Multi-turn context is kept per WebSocket connection in the consumer.

## Project layout

```
config/            Django project (settings, asgi, wsgi, urls)
chat/              Chat app: views, consumer, LLM service, routing, templates
  services.py      OllamaChatService — the only place that talks to the model
  consumers.py     ChatConsumer — streams tokens over the WebSocket
  templates/chat/  index.html + partials/ (header, messages, token, error, ...)
assets/css/        Tailwind source stylesheet (input.css)
static/            Built Tailwind output.css, htmx.min.js, ws.js, chat-ui.js
tests/             pytest suite (services, consumer, views/templates)
```

## Prerequisites

- [mise](https://mise.jdx.dev/) (pins Python **3.13.13** via `mise.toml`)
- Node.js + npm (for the Tailwind CLI build)
- A running [Ollama](https://ollama.com) server with the model pulled:

  ```bash
  ollama pull qwen2.5:7b
  ```

## Configuration

All configuration is environment-driven. Copy the example file and edit:

```bash
cp .env.example .env
```

| Variable                      | Default                                         | Notes                                            |
| ----------------------------- | ----------------------------------------------- | ------------------------------------------------ |
| `OLLAMA_HOST`                 | `http://localhost:11434`                        | Ollama base URL (not a secret).                  |
| `OLLAMA_MODEL`                | `qwen2.5:7b`                                     | Model tag to stream (not a secret).              |
| `DJANGO_SECRET_KEY`           | *(none)*                                        | **Required in production.** No hardcoded default.|
| `DJANGO_DEBUG`                | `false`                                         | Production-safe default.                         |
| `DJANGO_ALLOWED_HOSTS`        | `localhost,127.0.0.1`                           | Comma-separated; never `*`.                      |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000`   | Comma-separated scheme+host.                     |

`DJANGO_SECRET_KEY` is read from the environment with **no hardcoded fallback
and no placeholder literal** in source. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

If it is not set, an ephemeral key is generated at runtime so local dev, tests,
and static analysis work; running with `DEBUG=False` and no key logs a loud
warning because sessions/signatures will not survive a restart.

## Local setup & run

```bash
# 1. Install the pinned Python and create the virtualenv
mise install                         # installs Python 3.13.13
mise exec -- python -m venv .venv     # or rely on mise's managed venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt          # runtime only
pip install -r requirements-dev.txt      # runtime + dev tooling (tests/lint/types)

# 3. Build the Tailwind stylesheet (see below)
npm install
npm run build:css

# 4. Apply migrations (Django framework tables) and run the ASGI server
python manage.py migrate
DJANGO_DEBUG=true python manage.py runserver
```

Open <http://localhost:8000>, type a message, and watch the reply stream in.

> The chat history itself needs no database — it lives per WebSocket connection.
> `migrate` only creates Django's default framework tables (sessions, etc.).

## Tailwind CSS build

Styling uses the **official Tailwind CLI** (`@tailwindcss/cli`, v4). The source
stylesheet is `assets/css/input.css`; the built, minified output is
`static/css/output.css` (committed so the app runs without a Node step).

Exact build command (also available as the `build:css` npm script):

```bash
npx @tailwindcss/cli -i ./assets/css/input.css -o ./static/css/output.css --minify
# or:
npm run build:css
```

Watch mode during development:

```bash
npm run watch:css
```

## Tests & tooling

Install dev dependencies first (`pip install -r requirements-dev.txt`), then:

```bash
pytest                                   # full test suite
ruff check .                             # lint
ruff format --check .                    # formatting
mypy                                     # type check (chat + config)
bandit -c pyproject.toml -r .            # security scan (config excludes .venv/tests)
coverage run -m pytest && coverage report
pip-audit -r requirements.txt            # dependency vulnerability scan
```

The suite mocks the LLM boundary with a named fake (`tests/fakes.FakeChatService`)
and covers the service, the consumer (via `WebsocketCommunicator`, asserting
multiple streamed chunks and mid-stream disconnect cleanup), and the
views/templates (SPA render, partials, and HTMX WebSocket wiring).

## Run with Docker

The image uses Python 3.13.13 and serves the ASGI app with **daphne**. Static
assets are collected during the build (Tailwind output is already committed).

```bash
# Provide the required secret (no literal lives in compose):
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")

# Point at your Ollama server if it is not on the host default:
# export OLLAMA_HOST=http://host.docker.internal:11434
# export OLLAMA_MODEL=qwen2.5:7b

docker compose up --build
```

The app listens on <http://localhost:8000>. `docker-compose.yml` passes
`OLLAMA_HOST` / `OLLAMA_MODEL` through and reaches an Ollama server on the host
via `host.docker.internal`. Remember to `ollama pull qwen2.5:7b` on the host
first.

## Health check

`GET /health/` reports Ollama reachability without exposing any secret:

```json
{ "status": "ok", "ollama_reachable": true, "model": "qwen2.5:7b" }
```

It returns `503` with `"status": "degraded"` when the Ollama host is unreachable.

## Verification

See [VERIFY.md](VERIFY.md) for the exact commands run in this phase, their
pass/fail results, and evidence.
