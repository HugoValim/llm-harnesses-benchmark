FROM python:3.13.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md manage.py ./
COPY styles ./styles
COPY chat ./chat
COPY chat_project ./chat_project
COPY templates ./templates

# `chat/static/chat/css/tailwind.css` is generated locally via Tailwind CLI and committed for reproducible Docker builds.
RUN python -m pip install --upgrade pip \
    && python -m pip install .

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "chat_project.asgi:application"]
