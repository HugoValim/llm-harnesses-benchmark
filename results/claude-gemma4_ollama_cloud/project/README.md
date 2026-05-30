# Ollama Chat SPA

A Django + Channels chat application utilizing HTMX and LangChain-Ollama for streaming LLM responses.

## Setup

### Local Development
1. **Environment**: Use `mise` to ensure Python 3.13.13 is active.
2. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Environment Variables**:
   Copy `.env.example` to `.env` and fill in `SECRET_KEY`.
   ```bash
   cp .env.example .env
   # Generate a secret key:
   # python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
   ```
4. **Ollama**:
   Ensure Ollama is running locally and pull the model:
   ```bash
   ollama pull qwen2.5:7b
   ```
5. **Migrations**:
   ```bash
   python manage.py migrate
   ```
6. **Tailwind Build**:
   ```bash
   npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css
   ```
7. **Run Server**:
   ```bash
   daphne -p 8000 config.asgi:application
   ```

### Docker Run
```bash
docker-compose up --build
```
The app will be available at `http://localhost:8000`.

## Testing and Tooling
- **Tests**: `pytest`
- **Lint/Format**: `ruff check`, `ruff format`
- **Type Check**: `mypy .`
- **Security**: `bandit -r .`, `pip-audit`
- **Coverage**: `coverage run -m pytest && coverage report`

## Verification
See [VERIFY.md](VERIFY.md) for detailed verification results.
