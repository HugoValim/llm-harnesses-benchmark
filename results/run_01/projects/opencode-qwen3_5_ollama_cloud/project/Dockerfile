FROM python:3.13.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SECRET_KEY for build-time only (runtime value provided via env)
ARG BUILD_SECRET_KEY=build-time-key-for-collectstatic-only
ENV DJANGO_SECRET_KEY=${BUILD_SECRET_KEY}
RUN python manage.py collectstatic --noinput

ENV DEBUG=False \
    ALLOWED_HOSTS=localhost,127.0.0.1

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "chatproject.asgi:application"]
