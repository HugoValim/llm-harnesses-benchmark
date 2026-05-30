A. **Quick summary line**
Mostly meets the chat/Channels/Ollama spec, but ships with Django auth, broken mypy config, weak architecture boundaries, and missing production hardening.

B. **Scores per dimension**
| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 11 / 15 | Core files present, but auth is enabled (`config/settings.py:30`, `config/settings.py:44`) and mypy config is not a valid pyproject block (`pyproject.toml:11`). |
| 2 | D2 LLM integration correctness | 10 / 10 | Correct `langchain_ollama.ChatOllama` with env model/host and `.astream()` to WS (`chat/services.py:5`, `chat/services.py:11`, `chat/services.py:31`; `config/settings.py:106`). |
| 3 | D3 Test quality | 8 / 10 | Tests cover view/service/consumer, but WS streaming only asserts final joined text, so CF#9 caps this at 8 (`chat/tests.py:101`, `chat/tests.py:138`). |
| 4 | D4 Error handling | 10 / 10 | Consumer catches stream failures and sends UI errors; disconnect clears per-consumer state (`chat/consumers.py:23`, `chat/consumers.py:50`, `chat/templates/chat/chat.html:136`). |
| 5 | D5 Persistence / multi-turn | 5 / 5 | Per-consumer history accumulates user and assistant turns (`chat/consumers.py:14`, `chat/consumers.py:41`, `chat/consumers.py:59`). |
| 6 | D6 Streaming & frontend | 8 / 10 | HTMX ws and Tailwind are wired, but the WS test lacks a chunk-by-chunk assertion for multiple token frames (`chat/templates/chat/chat.html:12`, `chat/templates/chat/chat.html:116`; `chat/tests.py:138`). |
| 7 | D7 Architecture | 8 / 15 | Has a service module, but no settings split (`config/settings.py:1`), consumer body exceeds 30 nonblank lines (`chat/consumers.py:11`), and service lacks a protocol/interface (`chat/services.py:10`). |
| 8 | D8 Secrets & config hygiene | 5 / 5 | Secret has no hardcoded fallback and DEBUG defaults false; allowed hosts are narrowed (`config/settings.py:13`, `config/settings.py:20`, `config/settings.py:26`). |
| 9 | D9 Production hardening | 0 / 10 | No Docker/compose healthcheck, no restart policy, no non-root `USER`, no LOGGING config, no WS shutdown handling (`Dockerfile:1`, `docker-compose.yml:1`, `config/settings.py:107`). |
| 10 | D10 Code quality | 10 / 10 | Production code is small/typed, no production `Any`/`type: ignore`, and broad handlers count is only 2 (`chat/services.py:10`, `chat/consumers.py:27`, `chat/services.py:22`, `chat/consumers.py:50`). |

C. **Total score / 100**
75 / 100.

D. **Practical tier**
B (61-80): close to shippable, but prod hardening and config/tooling cleanup are needed first.

E. **Verification section**
No hallucinated API calls found. Installed source verified: `langchain_ollama/chat_models.py:261` has `ChatOllama`, `:525` has `model`, `:693` has `base_url`, `:1366` has async `_astream`; `langchain_core/language_models/chat_models.py:842` has async `astream`; `channels/generic/websocket.py:156` has `AsyncWebsocketConsumer`, `:186` connect, `:254` disconnect, `:274` receive_json, `:280` send_json; `channels/routing.py:36` has `ProtocolTypeRouter`, `:55` has `URLRouter`; `ollama/_client.py:723` has `AsyncClient`, `:957` async streamed `chat`.

F. **Critical Failures**
- `pyproject.toml:11`: CF#6, mypy is claimed but configured as `[mypy]` instead of pyproject's `[tool.mypy]`, so the declared tool config is effectively absent.
- `chat/tests.py:138`: CF#9, the consumer streaming test joins collected tokens and would still pass if the consumer buffered before sending one full message.

G. **Critical-failure ledger**
`pyproject.toml:11` -> CF#6 "Tooling claimed by README/spec but unconfigured (no `[tool.mypy]`...)" -> D1 missing tool config, -1.
`chat/tests.py:138` -> CF#9 "Tests pass against an anti-pattern... assert buffered output instead of streaming chunks" -> D3 cap at 8, -2.

H. **Submission metadata & generation metrics**
Model: deepseek_v4_pro_ollama_cloud  
Harness: opencode  
Harness-CLI-Version: n/a  
Generation-Time: 1967.34 seconds  
Input-Tokens / Output-Tokens / Total-Tokens: 113569 / 387 / 113956  
Estimated-Cost-USD: 0.049739  
Pricing-Source: docs/PRICING.md @ 2026-05-25  
Cost-Source: computed  
Benchmark-Result: /home/hugo/projects/python-benchmark/results/opencode-deepseek_v4_pro_ollama_cloud/result.json  
Date: 2026-05-29  
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2  
Source: results/opencode-deepseek_v4_pro_ollama_cloud/project  
Primary-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5  
Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5

I. **Killer strength** + **Killer weakness**
Killer strength: real LangChain Ollama token streaming is wired through Channels with useful tests.  
Killer weakness: production readiness is thin, especially Docker health/restart/user/logging/shutdown coverage.
