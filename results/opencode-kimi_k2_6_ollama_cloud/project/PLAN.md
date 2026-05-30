mise.toml plan:
[tools]
python = "3.13.13"

run:
mise install
mise exec python -- python -m venv .venv
source .venv/bin/activate
pip install django channels[daphne] channels-redis langchain-ollama pytest pytest-django pytest-asyncio coverage

project layout:
manage.py
chat_project/asgi.py settings.py urls.py wsgi.py
chat_app/
  consumers.py  # AsyncWebsocketConsumer streaming
  services.py   # ChatOllama wrapper
  views.py      # SPA view
  urls.py
  templates/chat_app/
    base.html
    chat.html
    partials/
      message.html
      stream_token.html
  tests/
    test_consumers.py
    test_views.py
    test_services.py
static/src/input.css
static/css/output.css
pyproject.toml with ruff, mypy, coverage, bandit, pip-audit
Dockerfile
.dockerignore
docker-compose.yml
.env.example
README.md
VERIFY.md

ASGI routing: websocket to ChatConsumer, http to Django ASGI handler.
HTMX ws extension included via CDN in base.html.
Tailwind CLI for building CSS.
