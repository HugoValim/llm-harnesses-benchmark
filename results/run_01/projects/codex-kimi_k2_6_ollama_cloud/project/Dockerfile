FROM python:3.13.13-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY chat/ ./chat/
COPY config/ ./config/
COPY manage.py .
COPY static/ ./static/
COPY templates/ ./templates/
COPY tailwind.config.js .
COPY tailwindcss .

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 8000 config.asgi:application"]
