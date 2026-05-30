# AI Chat Application

A Django + Django Channels chat application with AI-powered responses using Ollama.

## Features

- Django 6.0+ web framework
- Django Channels for WebSocket support
- HTMX for dynamic UI updates
- Tailwind CSS for styling
- AI integration with Ollama via LangChain
- Dockerized deployment
- Comprehensive test suite
- Code quality tools (ruff, mypy, bandit, coverage, pip-audit)

## Prerequisites

- Python 3.13.13 (or compatible)
- Node.js and npm (for Tailwind CSS)
- Docker (for containerized deployment)
- Ollama (for AI model inference)

## Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd <project-directory>
   ```

2. **Set up Python environment**
   ```bash
   # Using pyenv or virtualenv is recommended
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Node.js dependencies for Tailwind CSS**
   ```bash
   npm install
   ```

5. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your specific values
   ```

6. **Apply database migrations**
   ```bash
   python manage.py migrate
   ```

7. **Start Tailwind CSS build process (in a separate terminal)**
   ```bash
   npm run dev
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```

9. **Visit the application**
   Open your browser to `http://localhost:8000`

### Docker Deployment

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up --build
   ```

2. **Visit the application**
   Open your browser to `http://localhost:8000`

## Environment Variables

The following environment variables can be set:

- `OLLAMA_HOST`: URL of the Ollama API (default: `http://localhost:11434`)
- `OLLAMA_MODEL`: Name of the Ollama model to use (default: `qwen2.5:7b`)
- `DJANGO_SECRET_KEY`: Secret key for Django (required)
- `DEBUG`: Set to `True` for development, `False` for production (default: `True`)
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts (default: `localhost,127.0.0.1`)

## Development Commands

### Testing
```bash
# Run all tests
python manage.py test

# Run tests with coverage
coverage run -m pytest
coverage report
```

### Code Quality
```bash
# Run Ruff linting
ruff check .

# Run Ruff with auto-fix
ruff check --fix .

# Run MyPy type checking
mypy .

# Run Bandit security scan
bandit -r .

# Run Django migrations
python manage.py makemigrations
python manage.py migrate

# Build Tailwind CSS for production
npm run build
```

## Project Structure

```
.
├── config/               # Django project settings
├── chat/                 # Main application
│   ├── consumers.py      # WebSocket consumers
│   ├── views.py          # Application views
│   ├── templates/        # HTML templates
│   └── tests.py          # Unit tests
├── llm_service/          # LLM service layer
│   └── ollama_service.py # Ollama integration
├── static/               # Static files
│   ├── css/              # CSS files (processed by Tailwind)
│   └── src/              # Source CSS files
├── templates/            # Global templates
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose configuration
├── requirements.txt      # Python dependencies
├── package.json          # Node.js dependencies
├── tailwind.config.js    # Tailwind CSS configuration
├── postcss.config.js     # PostCSS configuration
└── README.md             # This file
```

## How It Works

1. **Frontend**: The application uses HTMX for dynamic updates and Tailwind CSS for styling.
2. **WebSocket**: Django Channels handles WebSocket connections for real-time communication.
3. **LLM Integration**: The `llm_service` module handles communication with Ollama via LangChain.
4. **Workflow**:
   - User sends a message via the form
   - Message is sent to the WebSocket consumer
   - Consumer processes the message through the LLM service
   - LLM response is streamed back to the client via WebSocket
   - HTMX updates the chat interface in real-time

## Testing

The application includes tests for:
- Views and URL routing
- WebSocket consumer connections and messaging
- LLM service functionality (with mocks)

## Deployment

The application is designed for easy deployment with Docker:
- Uses Django Daphne ASGI server
- Includes Ollama service in docker-compose
- Properly handles static files collection
- Environment variable configuration

## License

This project is licensed under the MIT License.
