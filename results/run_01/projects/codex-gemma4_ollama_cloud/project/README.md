# Ollama Chat App

A real-time chat application built with Django, Django Channels, LangChain, and HTMX.

## Setup

### Local Development
1. Install Python 3.13.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env and set DJANGO_SECRET_KEY
   ```
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Start the server:
   ```bash
   daphne -p 8000 core.asgi:application
   ```

### Tailwind Build
The project uses the official Tailwind CLI.
Build command:
```bash
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css
```

### Docker Run
1. Start services:
   ```bash
   docker-compose up -d
   ```
2. Pull the model:
   ```bash
   docker exec -it $(docker ps -qf "name=ollama") ollama pull qwen2.5:7b
   ```

## Testing & Quality
- Tests: `pytest`
- Lint: `ruff check`
- Format: `ruff format --check`
- Types: `mypy .`
- Security: `bandit -r .`
- Audit: `pip-audit`
