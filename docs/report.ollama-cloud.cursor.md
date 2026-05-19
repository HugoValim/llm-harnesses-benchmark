# Cursor CLI Benchmark Report — Python (Django + Channels)

Same prompt as the main benchmark (`prompts/benchmark_prompt.txt`). Phase 1 + Phase 2 when `enable_followup` is true.

Variants: `composer_2_5`, `composer_2_0`

Runner: `agent -p --output-format stream-json --force --trust`

Each variant writes under `results/cursor-<slug>/`.

## Summary

| Variant | Model | Status | Time | Files | Turns |
|---|---|---|---:|---:|---:|
| composer_2_5 | composer-2.5 | failed | 1824s | 56 | 5 |
| composer_2_0 | composer-2 | completed | 1919s | 52 | 8 |

## Phase Breakdown

### composer_2_5

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 704s | 3 | 56 |
| phase2 | failed | 1120s | 2 | 56 |

### composer_2_0

| Phase | Status | Time | Turns | Files |
|---|---|---:|---:|---:|
| phase1 | completed | 1571s | 6 | 52 |
| phase2 | completed | 348s | 2 | 52 |


## Tool activity

### composer_2_5

- `tool`: 164
- `shell cd /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project &...`: 64
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/chat/views.py`: 4
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/config/settings.py`: 4
- `grep`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/VERIFY.md`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/chat/consumers.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/chat/services/llm.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/config/asgi.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/package.json`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/static/src/input.css`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/templates/chat/index.html`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_5/project/templates/chat/partials/user_message.html`: 2
- `shell curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:1...`: 2
- `shell grep -q "Ollama Chat" /tmp/docker_page.html && echo "DOCKER_HTML: pass" && cu...`: 2
- `shell kill 2931688 2>/dev/null; sleep 1; cd /home/hugo/projects/python-benchmark/re...`: 2
- `shell pwd && ls -la`: 2
- `shell sleep 12 && cd /home/hugo/projects/python-benchmark/results/cursor-composer_2...`: 2
- `shell sleep 15 && cd /home/hugo/projects/python-benchmark/results/cursor-composer_2...`: 2
- `shell sleep 2 && curl -s -o /tmp/chat_page.html -w "HTTP %{http_code}\n" http://127...`: 2
- `shell sleep 20 && cd /home/hugo/projects/python-benchmark/results/cursor-composer_2...`: 2
- `shell sleep 8 && curl -s -o /tmp/docker_page.html -w "HTTP %{http_code}\n" http://1...`: 2
- `shell which mise django-admin python3.13 2>/dev/null; mise --version 2>/dev/null; p...`: 2

### composer_2_0

- `tool`: 172
- `shell cd /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project &...`: 92
- `read /home/hugo/.cursor/projects/home-hugo-projects-python-benchmark-results-cursor-composer-2-0-project/terminals/795004.txt`: 14
- `grep`: 4
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/README.md`: 4
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat/llm_service.py`: 4
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat_project/wsgi.py`: 4
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/CLAUDE.md`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/VERIFY.md`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat/apps.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat/tests/fakes.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat/views.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat_project/asgi.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat_project/settings.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/chat_project/urls.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/conftest.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/manage.py`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/package.json`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/pyproject.toml`: 2
- `read /home/hugo/projects/python-benchmark/results/cursor-composer_2_0/project/templates/chat/partials/header.html`: 2
- `read ?`: 2
- `shell curl -sS -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:11434/a...`: 2
- `shell curl -sS -o /tmp/chat_page.html -w "http_code=%{http_code}\n" --max-time 5 ht...`: 2
- `shell kill $(cat /home/hugo/.cursor/projects/home-hugo-projects-python-benchmark-re...`: 2
- `shell sleep 2 && curl -sS -o /tmp/docker_index.html -w "http_code=%{http_code}\n" -...`: 2
