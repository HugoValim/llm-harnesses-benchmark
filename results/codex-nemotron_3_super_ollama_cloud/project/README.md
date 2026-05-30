# Django Channels Chat Application

A chatGPT-style web application built with Django, Django Channels, HTMX, and Tailwind CSS, streaming responses from Ollama via LangChain.

## Features

- Single-page web interface using HTMX for dynamic updates
- Real-time token streaming from Ollama -> LangChain -> WebSocket -> browser
- Tailwind CSS for styling (built with the official Tailwind CLI)
- Dockerized for easy deployment
- Comprehensive test suite

## Prerequisites

- Python 3.13.13 (via mise)
- Node.js (for Tailwind CSS build)
- Docker (optional, for containerized deployment)
- Ollama server running with the qwen2.5:7b model (or another model configured via environment variables)

## Local Setup

1. **Set up Python environment**

   Ensure you have [mise](https://mise.jdx.dev/) installed and configured.

   ```bash
   mise use python 3.13.13
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Install Node.js dependencies (for Tailwind CSS)**

   ```bash
   npm install
   ```

4. **Set environment variables**

   Copy the example environment file and fill in the values:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` to set at least `DJANGO_SECRET_KEY` (required). Other variables have sensible defaults.

5. **Apply database migrations**

   ```bash
   python manage.py migrate
   ```

6. **Build Tailwind CSS**

   ```bash
   npm run buildcss
   ```

7. **Start the development server**

   ```bash
   python manage.py runserver
   ```

   The application will be available at http://127.0.0.1:8000.

## Using Docker

1. **Build the image**

   ```bash
   docker compose build
   ```

2. **Run the container**

   ```bash
   docker compose up
   ```

   The application will be available at http://localhost:8000.

   Note: Make sure to set the required environment variables in the `.env` file or override them in the `docker-compose.yml`.

## Ollama Model

Before running the application, ensure you have the Ollama server running and the desired model pulled:

```bash
ollama pull qwen2.5:7b
```

By default, the application expects the model `qwen2.5:7b` at `http://localhost:11434`. Adjust via `OLLAMA_HOST` and `OLLAMA_MODEL` environment variables if needed.

## Testing

Run the test suite with:

```bash
pytest
```

To run tests with coverage:

```bash
coverage run -m pytest
coverage report
```

## Tailwind CSS

The Tailwind CSS source is located at `static/src/input.css`. The built CSS is output to `static/css/tailwind.css`.

To rebuild the CSS when making changes:

```bash
npm run buildcss
```

For development, you can watch for changes:

```bash
npm run watchcss
```

## Verification

See `VERIFY.md` for a summary of verification commands and their results.

## License

This project is licensed under the MIT License.
