# Django Channels Chat Application

A real-time chat application built with Django, Django Channels, HTMX, and Tailwind CSS that streams responses from Ollama via LangChain.

## Features

- Real-time chat interface using Django Channels WebSockets
- HTMX with WebSocket extension for partial DOM updates
- Tailwind CSS for styling (via official CLI)
- Streaming LLM responses from Ollama using LangChain
- Environment variable configuration for Ollama host and model
- Comprehensive test suite

## Prerequisites

- Python 3.13.13 (via mise)
- Node.js and npm (for Tailwind CSS)
- Ollama running locally or accessible via network
- Ollama model `qwen2.5:7b` pulled (`ollama pull qwen2.5:7b`)

## Setup

1. **Clone the repository** (if applicable)
2. **Install Python dependencies**:
   ```bash
   # Activate mise environment
   eval "$(/home/hugo/.local/bin/mise activate bash)"
   
   # Install Python packages
   pip install -r requirements.txt
   ```
3. **Install Node.js dependencies**:
   ```bash
   npm install
   ```
4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env if needed (defaults are usually fine for local development)
   ```
5. **Apply database migrations**:
   ```bash
   python manage.py migrate
   ```
6. **Build Tailwind CSS**:
   ```bash
   # For development (watch mode):
   npx tailwindcss -i ./static/src/input.css -o ./static/dist/output.css --watch
   
   # For production build:
   npx tailwindcss -i ./static/src/input.css -o ./static/dist/output.css
   ```

## Running the Application

1. **Start the Tailwind CSS build process** (in a separate terminal):
   ```bash
   npx tailwindcss -i ./static/src/input.css -o ./static/dist/output.css --watch
   ```
2. **Start the Django development server**:
   ```bash
   python manage.py runserver
   ```
3. **Open your browser** to `http://localhost:8000`

## Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
coverage run -m pytest
coverage report
```

## Docker Usage

The application can be run using Docker Compose:

```bash
docker-compose up --build
```

Make sure to set the required environment variables in your `.env` file or docker-compose.override.yml.

## Configuration

Key configuration options are set via environment variables:

- `OLLAMA_HOST`: URL of the Ollama API (default: `http://localhost:11434`)
- `OLLAMA_MODEL`: Model to use for chat (default: `qwen2.5:7b`)
- `DJANGO_SECRET_KEY`: Secret key for Django security
- `DEBUG`: Set to `True` for development, `False` for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts

See `.env.example` for more details.

## Implementation Details

### Architecture

- **Django Channels**: Handles WebSocket connections for real-time communication
- **HTMX**: Used with WebSocket extension for updating the DOM without custom JavaScript
- **Tailwind CSS**: Utility-first CSS framework for styling
- **LangChain Ollama**: Official integration for streaming responses from Ollama models

### File Structure

- `chat/`: Main application containing views, consumers, templates, and services
- `chatproject/`: Django project configuration
- `static/src/`: Source CSS files for Tailwind
- `static/dist/`: Compiled CSS output from Tailwind
- `templates/chat/`: HTML templates for the chat interface

### Key Components

1. **Chat View** (`chat/views.py`): Renders the main chat page
2. **WebSocket Consumer** (`chat/consumers.py`): Handles WebSocket connections and message streaming
3. **Ollama Service** (`chat/services.py`): Wrapper around LangChain's ChatOllama for streaming responses
4. **Templates** (`chat/templates/chat/chat.html`): HTMX-powered chat interface
5. **Routing** (`chat/routing.py`): WebSocket URL patterns
6. **Tests** (`chat/tests.py`): Test suite for views, consumers, and services

## Verification

See `VERIFY.md` for detailed verification commands and results.

## License

MIT