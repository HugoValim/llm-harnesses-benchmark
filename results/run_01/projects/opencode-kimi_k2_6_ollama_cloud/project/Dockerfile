FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir django channels[daphne] langchain-ollama

RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "chat_project.asgi:application"]

