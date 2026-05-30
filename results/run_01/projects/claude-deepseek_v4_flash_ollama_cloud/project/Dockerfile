FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV DJANGO_SECRET_KEY=change-me
ENV DJANGO_DEBUG=False
ENV ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
ENV OLLAMA_HOST=http://host.docker.internal:11434
ENV OLLAMA_MODEL=qwen2.5:7b

RUN python manage.py migrate --noinput

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
