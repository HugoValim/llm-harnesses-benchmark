A. **Quick summary line**

The submission is a broken Django Channels project: `settings.py` raises `NameError` (missing `Path` import), the SPA view is entirely absent, a hallucinated `streaming=True` parameter is passed to `ChatOllama`, `DEBUG=True` is hardcoded, and multiple tool configs are malformed or missing.

B. **Scores per dimension**

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 14 / 25 | Missing `chat_view` (`chat/views.py:1`), ruff/coverage configs malformed (`pyproject.toml:1`, `.coveragerc:1`), bandit and pip-audit unconfigured, Tailwind CDN-only (-2), `settings.py:16` missing `from pathlib import Path` → NameError at startup. |
| 2 | LLM integration correctness | 12 / 20 | Hallucinated `streaming=True` constructor parameter on `ChatOllama` (`chat/services.py:10`; not in `ChatOllama.model_fields`), single-turn only with no history (-3). |
| 3 | Test quality | 5 / 15 | Tests do not exercise the LLM path: `test_chat.py:3` uses a broken relative import, `test_chat.py:16` patches `astream` with a `list` return_value (fails `async for`), and `test_consumers.py:15` admits it does not mock the LLM consumer path. |
| 4 | Error handling | 0 / 10 | No try/except around the streaming loop in `ChatConsumer.receive` (`chat/consumers.py:9`), bare-pass `disconnect` (`chat/consumers.py:6`), no Ollama reachability preflight guard (U1). |
| 5 | Persistence / multi-turn state | 3 / 10 | No history accumulation; every message is a one-shot prompt. |
| 6 | Streaming & frontend wiring | 8 / 10 | Vanilla JS WebSocket correctly streams tokens to the DOM, but no chunk-by-chunk test assertion exists (-2). |
| 7 | Architecture | 5 / 5 | LLM client extracted to `chat/services.py`; no inline wiring in the consumer. |
| 8 | Secrets & config hygiene | 0 / 3 | `DEBUG = True` hardcoded in `config/settings.py:20` (CF#10), capping this dimension at 0; `ALLOWED_HOSTS = ['*']` (`config/settings.py:22`) is masked by the cap. |
| 9 | Production hardening | 0 / 2 | No `HEALTHCHECK` in `Dockerfile` or compose, no structured logging. |

C. **Total score / 100**

47 / 100

D. **Practical tier**

**C (41–60)**: major rework needed. Core bugs or missing deliverables. The app cannot start because of the missing `Path` import and missing `chat_view`, and the `ChatOllama` integration relies on a hallucinated parameter.

E. **Verification section**

- `ChatOllama` constructor parameter `streaming`: `model_fields` inspection shows `streaming` is **not** a field. Verified by `python -c "from langchain_ollama import ChatOllama; print('streaming' in ChatOllama.model_fields)"` → `False`. The installed source defines `model`, `base_url`, `reasoning`, etc., but no `streaming` field.
- `ChatOllama.astream` signature: `astream(input: 'LanguageModelInput', config: 'RunnableConfig | None' = None, *, stop: 'list[str] | None' = None, **kwargs: 'Any') -> 'AsyncIterator[AIMessageChunk]'`. Verified from installed source; correct usage in `chat/services.py:12`.
- `AsyncWebsocketConsumer` methods: `connect(self)`, `disconnect(self, code)`, `receive(self, text_data=None, bytes_data=None)`, `receive_json(self, content, **kwargs)`, `send_json(self, content, close=False)`. Verified from `channels/generic/websocket.py`.
- `ProtocolTypeRouter` and `URLRouter`: verified present in `channels/routing.py`.

F. **Critical Failures**

- `chat/services.py:10` — hallucinated `streaming=True` passed to `ChatOllama` constructor; parameter does not exist in library source.
- `config/settings.py:20` — `DEBUG = True` hardcoded for the production/Docker path (CF#10).
- `chat/views.py:1` / `chat/urls.py:2` — `chat_view` function is entirely absent; URL configuration imports a non-existent symbol.
- `pyproject.toml:1` — ruff claimed in README but unconfigured (malformed `[ruff]` section; ruff ignores it).
- `.coveragerc:1` — coverage claimed in README but unconfigured (malformed `[tool.coverage.run]` in an INI file; source/omit remain `None`).
- Absence — bandit claimed in README but has no configuration file.
- Absence — pip-audit claimed in README but unconfigured.

G. **Critical-failure ledger**

| File:line | Mapped rubric trigger | Deduction |
|-----------|----------------------|-----------|
| `chat/services.py:10` | no trigger (hallucinated constructor parameter, not a class/method); -5 from D2 | -5 |
| `config/settings.py:20` | CF#10 — `DEBUG = True` hardcoded for the production stack | cap D8 at 0 |
| `chat/views.py:1` | no trigger (missing SPA view not explicitly listed in D1); -5 from D1 | -5 |
| `pyproject.toml:1` | D1 — Each missing tool config (ruff, mypy, bandit, coverage, pip-audit): -1 | -1 |
| `.coveragerc:1` | D1 — Each missing tool config: -1 | -1 |
| Absence | D1 — Each missing tool config: -1 (bandit) | -1 |
| Absence | D1 — Each missing tool config: -1 (pip-audit) | -1 |

H. **Submission metadata & generation metrics**

- Model: gemma4:31b-cloud
- Harness: claude-code
- Generation-Time: 536.52 s
- Input-Tokens: 1647474
- Output-Tokens: 10137
- Total-Tokens: 1658611
- Estimated-Cost-USD: n/a
- Pricing-Source: n/a — model absent from benchmark-ai-code skill PRICING.md
- Date: 2026-05-15
- Prompt-Version: v2.1
- Source: `/home/hugo/projects/python-benchmark/results/claude-gemma4_ollama_cloud`

I. **Killer strength + Killer weakness**

- **Killer strength**: The consumer streams tokens chunk-by-chunk over the WebSocket without buffering, and the LLM client is cleanly factored into `services.py`.
- **Killer weakness**: The SPA view is missing and `settings.py` won't compile, so the application cannot even start.
