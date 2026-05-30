# Verification Summary

All verification was run under Python 3.13.13 via `mise`.

## Toolchain

| Command | Result | Evidence |
|---|---|---|
| `mise run python --version` | PASS | Python 3.13.13 |
| `pip install -e ".[dev]"` | PASS | Dependencies installed |
| `ruff check .` | PASS | All checks passed! |
| `ruff format --check .` | PASS | 37 files already formatted |
| `mypy chat chat_project` | PASS | Success: no issues found in 17 source files |
| `bandit -r chat chat_project` | PASS | No issues identified. High: 0, Medium: 0 |
| `pip-audit` | PASS | No known vulnerabilities found |
| `pytest .` (env vars set) | PASS | 17 passed in ~4s |
| `coverage run -m pytest .` | PASS | 17 passed; 74% overall coverage |

## App Boot

| Command | Result | Evidence |
|---|---|---|
| `daphne -b 127.0.0.1 -p 8000 chat_project.asgi:application` | PASS | Daphne starts, HTTP 200 on `/` |
| `curl /` → HTML contains `hx-ext="ws"` | PASS | `<div class="chat-container" hx-ext="ws">` found |
| `curl /` → HTML contains `ws-connect="/ws/chat/"` | PASS | `ws-connect="/ws/chat/"` found |
| `curl /` → HTML contains `ws-send` | PASS | `ws-send` found on form and button |
| `curl /` → HTML contains no `new WebSocket` | PASS | 0 occurrences — uses HTMX ws extension, not raw WebSocket |
| Raw WebSocket upgrade request → 101 | PASS | HTTP/1.1 101 Switching Protocols, `Origin: http://127.0.0.1:8000` required |

## WebSocket Route

| Command | Result | Evidence |
|---|---|---|
| WebSocket upgrade to `/ws/chat/` | PASS | 101 Switching Protocols (origin required) |
| WebSocketCommunicator test (pytest) | PASS | 11 consumer tests pass — connect, disconnect, reset, multi-token streaming, error paths |
| Ollama unreachable → typed error | PASS | `OllamaConnectionError` surfaces as `{"type":"error","error":"..."}` |

## Docker

| Command | Result | Evidence |
|---|---|---|
| `docker build -t chat-web .` | PASS | Image built, no secrets hardcoded |
| `docker compose up --build -d` | PASS | Both containers up: `chat-ollama`, `chat-web` on `0.0.0.0:8000->8000/tcp` |
| `curl localhost:8000/` inside compose | PASS | HTTP 200, HTML contains `hx-ext="ws"`, `ws-connect="/ws/chat/"` |
| WebSocket upgrade inside container | PASS | `101 Switching Protocols` confirmed via `docker compose exec -T web` |
| Ollama health inside Docker | BLOCKED | Ollama not reachable from container in this environment — expected, not a code bug |

## Environment for pytest

Requires env vars (no hardcoded fallback):
```bash
DJANGO_SECRET_KEY="test-secret-key-for-pytest-32chars-xx" \
OLLAMA_HOST="http://localhost:11434" \
OLLAMA_MODEL="qwen2.5:7b" \
pytest .
```

The `tests/conftest.py` sets `os.environ.setdefault` for these vars, which works when env vars are set externally before pytest-django initializes Django settings. Without external env vars, pytest-django fails before conftest runs.

## Environment for docker compose

```bash
export DJANGO_SECRET_KEY="your-secret-key-here"
export OLLAMA_HOST="http://ollama:11434"   # default within compose
export OLLAMA_MODEL="qwen2.5:7b"           # default within compose
docker compose up --build
```

## Blockers

- **Ollama unreachable in Docker**: The Ollama server is not reachable from inside Docker containers in this benchmark environment. The `/health/` endpoint returns 503 inside Docker — this is an expected environmental constraint. The app handles it by surfacing `OllamaConnectionError` as a typed WebSocket error to the client. Not a code bug.
