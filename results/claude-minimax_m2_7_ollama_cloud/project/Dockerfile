FROM python:3.13.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt

COPY . .

RUN npm install tailwindcss@3 postcss autoprefixer && \
    npx tailwindcss init -p 2>/dev/null || true && \
    npx tailwindcss -i static/css/src.css -o static/css/output.css 2>/dev/null || true

RUN DJANGO_SECRET_KEY=build-secret python manage.py migrate --noinput

EXPOSE 8000

ENV OLLAMA_HOST \
    OLLAMA_MODEL \
    DEBUG=false \
    ALLOWED_HOSTS=localhost,127.0.0.1

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "ollama_chat.asgi:application"]