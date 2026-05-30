FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --no-cache-dir "uv[pip]>=0.5.0" && \
    uv pip install --system --no-cache-dir \
    django \
    channels \
    daphne \
    langchain-ollama \
    pytest \
    pytest-django \
    pytest-asyncio \
    ruff \
    mypy \
    bandit \
    coverage \
    pip-audit

COPY . .

RUN python manage.py migrate --noinput || true

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]