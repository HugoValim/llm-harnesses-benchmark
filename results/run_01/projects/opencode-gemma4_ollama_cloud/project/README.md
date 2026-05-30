# AI Chat App

ChatGPT-style streaming chat using Django, Channels, HTMX and Ollama.

## Setup

1. **Environment**: Use Python 3.13.13.
2. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Env Variables**: Copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY`.
4. **Ollama**: 
   - Ensure Ollama is running.
   - `ollama pull qwen2.5:7b`

## Local Run

1. Build Tailwind CSS:
   ```bash
   npx tailwindcss -i ./static/src/input.css -o ./static/dist/output.css --config .tailwind.config.js
   ```
2. Run migrations and start server:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

## Docker Run

```bash
docker-compose up --build
```

## Test Commands

- `pytest`
- `ruff check`
- `ruff format --check`
- `mypy .`
- `bandit -r .`
- `pip-audit`
- `coverage run -m pytest && coverage report`

## Verification Summary

| Command | Result | Evidence/Blocker |
|---------|--------|------------------|
| `python --version` | PASS | Python 3.13.13 |
| `pip install` | PASS | All dependencies installed |
| `tailwindcss build` | PASS | static/dist/output.css created |
| `pytest` | PASS | All tests passed |
| `ruff check` | PASS | No issues found |
| `ruff format --check` | PASS | No formatting issues |
| `mypy .` | PASS | No type errors |
| `bandit -r .` | PASS | No high severity findings |
| `pip-audit` | PASS | No vulnerabilities |
