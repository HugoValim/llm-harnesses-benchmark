# syntax=docker/dockerfile:1

# Pinned to the same interpreter the local mise environment uses.
FROM python:3.13.13-slim AS runtime

# Fail fast, no .pyc, unbuffered logs for container-friendly output.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Production-safe defaults. DEBUG is off and ALLOWED_HOSTS is narrow; both can
# be overridden at runtime. OLLAMA_* are non-secret and env-driven.
ENV DJANGO_DEBUG=false \
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=qwen2.5:7b

WORKDIR /app

# Install runtime dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the application source (see .dockerignore for what is excluded).
COPY . .

# Collect static assets (Tailwind output is already built and committed). No
# secret is needed: settings generate an ephemeral key when none is supplied,
# so the build never embeds a secret value.
RUN python manage.py collectstatic --noinput

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ASGI server (daphne) serving the Channels application.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
