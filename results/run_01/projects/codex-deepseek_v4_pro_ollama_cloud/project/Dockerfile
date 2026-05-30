FROM python:3.13.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Tailwind CLI
RUN curl -sL https://github.com/tailwindlabs/tailwindcss/releases/download/v4.1.6/tailwindcss-linux-x64 \
    -o /usr/local/bin/tailwindcss && chmod +x /usr/local/bin/tailwindcss

# Install Python deps
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source, build Tailwind, collect static
COPY . /app/

# Build-time secret for collectstatic only — replaced at runtime by real secret
ARG DJANGO_SECRET_KEY=build-time-dummy-key-not-for-prod
ENV DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY

RUN tailwindcss --input static_src/input.css --output static/css/output.css \
    && python manage.py collectstatic --noinput --clear

# Clear the build-time secret and require runtime override
ENV DJANGO_SECRET_KEY=

EXPOSE 8000

# daphne ASGI server — listens on 0.0.0.0:8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
