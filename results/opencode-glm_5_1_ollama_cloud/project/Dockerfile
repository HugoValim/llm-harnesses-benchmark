FROM python:3.13.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g @tailwindcss/cli@4 tailwindcss

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN npx @tailwindcss/cli@4 --input static/src/input.css --output static/css/app.css

RUN python -c "import secrets; open('/tmp/.build_secret', 'w').write(secrets.token_urlsafe(50))" && \
    DJANGO_SECRET_KEY=$(cat /tmp/.build_secret) python manage.py collectstatic --noinput && \
    rm -f /tmp/.build_secret

EXPOSE 8000

CMD ["sh", "-c", "DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set} uvicorn config.asgi:application --host 0.0.0.0 --port 8000"]