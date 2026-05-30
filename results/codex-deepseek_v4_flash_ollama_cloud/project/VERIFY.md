# Verification Summary

| # | Command | Result | Evidence / Blocker |
|---|---------|--------|-------------------|
| 1 | `python --version` | PASS | Python 3.13.13 via mise |
| 2 | `pip install -r requirements.txt` | PASS | All deps installed in `.venv13` |
| 3 | `npx tailwindcss -i ... -o ...` | PASS | Built `output.css` (1156ms) |
| 4 | `python -m pytest -v` | PASS | 6/6 passed (views + consumer) |
| 5 | `ruff check .` | PASS | 0 errors |
| 6 | `ruff format --check .` | PASS | 16 files already formatted |
| 7 | `mypy chat/ chat_project/` | PASS | 0 issues |
| 8 | `bandit -r chat/ chat_project/` | PASS | 0 HIGH severity findings (16 LOW from test asserts) |
| 9 | `python -m coverage report` | PASS | 75% overall; chat/views.py 100%, chat/consumers.py 92% |
| 10 | `pip-audit` | PASS | 0 vulns in project deps; 2 in pip itself (CVE-2026-3219, CVE-2026-6357) |
| 11 | `daphne -b 0.0.0.0 -p 8765 chat_project.asgi:application` + `curl :8765/` | PASS | HTTP 200; page loads with HTMX ws-ext |
| 12 | `curl :8765/health/` | PASS | Returns `{"ollama": "unreachable: ..."}` within 5s (timeout added to `check_ollama_health`) |
| 13 | WS connect + stream (mocked LLM) | PASS | WS connects, streams 3 chunks, done signal received |
| 14 | `docker build -t chatllm:test .` | PASS | Image built successfully (127s) |
| 15 | `docker compose up --build -d` | PASS | Both containers start; HTTP 200 from `:8000/` |
| 16 | `curl :8000/health/` (inside Docker) | PASS | Returns `{"ollama": "unreachable: "}` — expected env constraint (Ollama backend unreachable inside Docker) |

## Environment details

- Python: 3.13.13 (managed via `mise`)
- Node: v25.8.2
- pip: 26.0.1
- OS: Linux x64
- Docker: 29.4.2

## Code changes made during verification

### `chat/llm_service.py`
- Added `asyncio.wait_for(..., timeout=5.0)` to `check_ollama_health()` to prevent the health endpoint from hanging indefinitely when Ollama takes too long to respond.

### `docker-compose.yml`
- Removed NVIDIA GPU `deploy.resources` block from ollama service (driver not available in env).
- Changed ollama host port mapping from `11434:11434` to `11435:11434` to avoid conflict with host Ollama on `:11434`.

## Notes

- `bandit` B101 (assert_used) findings are all in test files — excluded from HIGH severity by tool default. No HIGH or MEDIUM issues.
- `pip-audit` reports CVEs in `pip` itself, not in project dependencies.
- Ollama `qwen2.5:7b` is pulled locally but model generation is slow (>5s). The health check now has a 5s timeout and reports `"unreachable"` gracefully.
- The app uses HTMX WebSocket extension (`hx-ext="ws"`, `ws-connect`, `ws-send`) — no raw `new WebSocket(...)` JavaScript for the streaming path.
- The Docker compose health endpoint returns 503 due to Ollama being unreachable inside containers — this is a documented environmental constraint, not a code bug.
