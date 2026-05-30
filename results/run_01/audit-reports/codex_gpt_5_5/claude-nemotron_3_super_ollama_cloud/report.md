A. **Quick Summary**
Submission does not meet benchmark-v3.2: core WebSocket route/HTMX streaming is broken, secrets are hardcoded, toolchain is unreproducible, and production path is unsafe.

B. **Scores Per Dimension**
| # | Dimension | Score / Max | Justification |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 0 / 15 | Docker/compose/README exist, but required dev deps absent from `requirements.txt:1-5`, `pyproject.toml:53` is invalid TOML, `requirements.txt:3` uses disallowed django-tailwind, auth is enabled at `config/settings.py:35`, no verification summary in `README.md:94-126`. |
| 2 | D2 LLM integration correctness | 6 / 10 | Correct `ChatOllama` import and `.astream()` at `llm_service/ollama_service.py:2,20`, but no history at `chat/consumers.py:26-30`, env defaults silently fallback at `llm_service/ollama_service.py:8-9`, streaming test only joins chunks at `chat/tests.py:42-54`. |
| 3 | D3 Test quality | 2 / 10 | No test covers `llm_service/ollama_service.py`; consumer test bypasses routing with `ChatConsumer.as_asgi()` at `chat/tests.py:28` and asserts final string only at `chat/tests.py:53-54`. |
| 4 | D4 Error handling | 4 / 10 | No Ollama startup/preflight guard (`llm_service/ollama_service.py:7-13`); `disconnect` is bare `pass` at `chat/consumers.py:19-20`. |
| 5 | D5 Persistence / multi-turn | 1 / 5 | Per-message prompt rebuilt from only current message at `chat/consumers.py:26-30`; no accumulated history. |
| 6 | D6 Streaming & frontend | 0 / 10 | `chat/routing.py` is empty; ASGI falls back to empty routes at `config/asgi.py:15-18`; HTMX ws extension is loaded but unused at `chat/templates/chat/chat.html:9-10`, while raw `new WebSocket` is used at `chat/templates/chat/chat.html:28`; no partial include. |
| 7 | D7 Architecture | 8 / 15 | Service module exists, but no prod/settings split (`config/settings.py:1-147`), consumer body exceeds 30 nonblank lines (`chat/consumers.py:6-43`), service lacks typed protocol and uses `messages: list` at `llm_service/ollama_service.py:15`. |
| 8 | D8 Secrets & config hygiene | 0 / 5 | Hardcoded Django secret caps dimension: `config/settings.py:23`; compose fallback also hardcodes secret at `docker-compose.yml:11`; `DEBUG = True` at `config/settings.py:26`. |
| 9 | D9 Production hardening | 0 / 10 | No healthcheck or `USER` in `Dockerfile:1-30`, no restart policy in `docker-compose.yml:4-15`, no structured `LOGGING` in `config/settings.py:1-147`, no SIGTERM/WebSocket shutdown path. |
| 10 | D10 Code quality | 8 / 10 | Type-safety gap despite mypy config: untyped public consumer methods at `chat/consumers.py:7,11,19,22` and bare `messages: list` at `llm_service/ollama_service.py:15`; no god-method or security-smell cap found. |

C. **Total Score**
29 / 100.

D. **Practical Tier**
D (0-40): throw away or use only for architectural inspiration; tier also cannot exceed B because section F has >=3 CF types.

E. **Verification**
No hallucinated API call claimed. Required `.venv/lib/python3.*` glob had no match; installed source was verified from `project/venv/lib/python3.12/site-packages`. Grep evidence: `langchain_ollama/chat_models.py:261 class ChatOllama`, `:525 model`, `:693 base_url`, `:1366 async def _astream`; `langchain_core/language_models/chat_models.py:461 def invoke`, `:488 async def ainvoke`, `:713 def stream`, `:842 async def astream`; `ollama/_client.py:723 class AsyncClient`, `:941 async def chat`; `channels/generic/websocket.py:156 class AsyncWebsocketConsumer`, `:186 connect`, `:254 disconnect`, `:274 receive_json`, `:280 send_json`; `channels/routing.py:36 ProtocolTypeRouter`, `:55 URLRouter`.

F. **Critical Failures**
- CF#1: `config/settings.py:23`, `docker-compose.yml:11` hardcode secret-shaped Django keys.
- CF#2: `config/asgi.py:15-18` falls back to empty WebSocket routing; `chat/templates/chat/chat.html:9-10` loads HTMX ws without wiring.
- CF#5: `requirements.txt:1-5` omits pytest, pytest-django, pytest-asyncio, ruff, mypy, bandit, coverage, pip-audit.
- CF#6: `README.md:14` claims tools, but `pyproject.toml:53` is invalid TOML and no pip-audit config/invocation exists.
- CF#9: `chat/tests.py:28,53-54` bypasses ASGI routing and asserts only final joined stream.
- CF#10: `config/settings.py:26` hardcodes `DEBUG = True` for Docker path (`Dockerfile:6`).
- CF#11: `chat/consumers.py:19-20` has pass-only `disconnect`.
- CF#12: `chat/templates/chat/chat.html:28` uses vanilla `new WebSocket(...)` instead of HTMX ws extension.

G. **Critical-Failure Ledger**
| Evidence | Trigger -> deduction |
|---|---|
| `config/settings.py:23`, `docker-compose.yml:11` | CF#1 hardcoded secret -> D8 cap 0. |
| `config/asgi.py:15-18`, `chat/templates/chat/chat.html:9-10` | CF#2 absent/unused required deliverable -> D6 "No HTMX WebSocket extension wired" -4. |
| `requirements.txt:1-5` | CF#5 missing dependency declarations -> no exact D1 bullet; -5 from D1. |
| `README.md:14`, `pyproject.toml:53` | CF#6 claimed tooling unconfigured -> D1 missing tool configs -5. |
| `chat/tests.py:28,53-54` | CF#9 false-green tests -> D3 cap 8 plus D3 LLM/streaming deductions. |
| `config/settings.py:26` | CF#10 DEBUG hardcoded -> D8 -2. |
| `chat/consumers.py:19-20` | CF#11 bare disconnect -> D4 -3. |
| `chat/templates/chat/chat.html:28` | CF#12 disallowed vanilla JS path -> D6 -4. |

H. **Submission Metadata & Generation Metrics**
Model: nemotron_3_super_ollama_cloud
Harness: claude
Harness-CLI-Version: n/a
Generation-Time: 1098.43 seconds
Input-Tokens: 10877348
Output-Tokens: 28689
Total-Tokens: 10906037
Estimated-Cost-USD: 52.911205
Pricing-Source: docs/PRICING.md @ 2026-05-25
Cost-Source: harness_reported
Date: 2026-05-30
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2
Source: /home/hugo/projects/python-benchmark/results/claude-nemotron_3_super_ollama_cloud/project
Benchmark-Result: /home/hugo/projects/python-benchmark/results/claude-nemotron_3_super_ollama_cloud/result.json
Primary-Prompt-SHA256: 9940ae82ac8c1b8d3c5b76c2d5c0db62ed9e775d949e7b324c5b6c6e96f7ec28
Followup-Prompt-SHA256: bf86cbe9f5cf245ba911e3a1c9cffbe3e4ac1aed08da7c973a9c73c3a62eeae3

I. **Killer Strength / Killer Weakness**
Killer strength: Uses the correct `langchain_ollama.ChatOllama` async streaming surface in a small service module.
Killer weakness: User-visible streaming cannot work because WebSocket routing is empty and frontend uses the disallowed raw WebSocket path.
