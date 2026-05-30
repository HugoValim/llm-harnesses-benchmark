A. **Quick summary line**
Submission mostly works as demo, but misses spec-critical prod/config/frontend/test guarantees.

B. **Scores per dimension**

| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 8 / 15 | Docker/compose/README/pyproject exist, but Tailwind CLI file is invalid (`tailwindcss-linux-x64:1`), auth stack present despite "no auth" (`chat_project/settings.py:19-20`), project lives in nested `chat_app/` (`chat_app/consumers.py:1`). |
| 2 | D2 LLM integration correctness | 10 / 10 | Correct `langchain_ollama.ChatOllama` + `.astream()` (`chat_app/services.py:7`, `chat_app/services.py:19-23`); env host/model wired (`chat_project/settings.py:98-99`); tokens sent during loop (`chat_app/consumers.py:61-68`). |
| 3 | D3 Test quality | 3 / 10 | Consumer/view tests exist, but LLM/Ollama wiring is not tested; service test uses only fake streamer (`chat_app/tests/test_services.py:1-9`), and consumer monkeypatches service away (`chat_app/tests/test_consumers.py:27`). |
| 4 | D4 Error handling | 10 / 10 | Consumer wraps stream errors and sends visible error (`chat_app/consumers.py:60-72`); disconnect clears state (`chat_app/consumers.py:23-25`); CSRF/security middleware present (`chat_project/settings.py:28-35`). |
| 5 | D5 Persistence / multi-turn | 5 / 5 | Per-consumer history accumulates user/assistant turns (`chat_app/consumers.py:16`, `chat_app/consumers.py:40`, `chat_app/consumers.py:74-76`). |
| 6 | D6 Streaming & frontend | 2 / 10 | HTMX ws is wired (`chat_app/templates/chat_app/chat.html:7-15`), but no partial include (`chat_app/templates/chat_app/chat.html:1`), Tailwind CLI invalid (`tailwindcss-linux-x64:1`), streaming test lacks multi-chunk path assertion (`chat_app/tests/test_consumers.py:40-42`). |
| 7 | D7 Architecture | 8 / 15 | Service module exists (`chat_app/services.py:10`), but no settings split (`chat_project/settings.py:1`), consumer class exceeds 30 nonblank lines (`chat_app/consumers.py:11`), service lacks typed protocol boundary and uses concrete instantiation (`chat_app/consumers.py:58`). |
| 8 | D8 Secrets & config hygiene | 0 / 5 | Capped by hardcoded secret-shaped placeholders (`Dockerfile:12`, `README.md:48`, `VERIFY.md:18-27`). |
| 9 | D9 Production hardening | 0 / 10 | No Docker/compose healthcheck, restart policy, `USER`, structured logging, or SIGTERM stream handling (`Dockerfile:1-16`, `docker-compose.yml:1-14`). |
| 10 | D10 Code quality | 8 / 10 | Type-safety gap under declared mypy: `Any` and ignores in production (`chat_app/consumers.py:4`, `chat_app/consumers.py:11`, `chat_app/services.py:17`). |

C. **Total score / 100**
54 / 100.

D. **Practical tier**
C (41-60): major rework needed; core app works, but prod hardening, frontend build, secrets hygiene, and tests need real fixes.

E. **Verification section**
No hallucinated API claims found. Installed package source verifies: `ChatOllama` class plus `model`/`base_url` fields (`.venv/lib/python3.13/site-packages/langchain_ollama/chat_models.py:261`, `:525`, `:693`); `.invoke`/`.ainvoke`/`.stream`/`.astream` exist and `.astream` yields `AIMessageChunk` (`.venv/lib/python3.13/site-packages/langchain_core/language_models/chat_models.py:461`, `:488`, `:713`, `:842-849`, `:931-932`); `AsyncClient.chat(..., stream=True)` exists (`.venv/lib/python3.13/site-packages/ollama/_client.py:723`, `:957-970`); Channels consumer/router APIs exist (`.venv/lib/python3.13/site-packages/channels/generic/websocket.py:156`, `:186`, `:254`, `:274`, `:280`; `.venv/lib/python3.13/site-packages/channels/routing.py:36`, `:55`).

F. **Critical Failures**
- CF#1: Hardcoded secret-shaped placeholders appear in Dockerfile/docs (`Dockerfile:12`, `README.md:48`, `VERIFY.md:18-27`) -> D8 cap.
- CF#2: Required Tailwind CLI deliverable absent; submitted binary is literal `Not Found` (`tailwindcss-linux-x64:1`) while README requires `tailwindcss` (`README.md:30`).
- CF#9: Consumer test is false-green for streaming; it only checks any OOB/Hello message, not multiple streamed chunks (`chat_app/tests/test_consumers.py:40-42`).

G. **Critical-failure ledger**
- `Dockerfile:12`, `README.md:48`, `VERIFY.md:18-27` -> CF#1 "Any hardcoded secret..." -> D8 capped at 0 (-5).
- `tailwindcss-linux-x64:1` -> CF#2 "spec hard-requirement deliverable is entirely absent" -> D6 "Tailwind CLI not actually wired" (-3).
- `chat_app/tests/test_consumers.py:40-42` -> CF#9 "Tests pass against an anti-pattern" -> D3 capped at 8; D3 already 3 after LLM-test deduction.

H. **Submission metadata & generation metrics**
Model: kimi_k2_6_ollama_cloud  
Harness: opencode  
Harness-CLI-Version: n/a  
Generation-Time: 2478.28 seconds  
Input-Tokens / Output-Tokens / Total-Tokens: 120644 / 870 / 121514  
Estimated-Cost-USD: 0.091106  
Pricing-Source: docs/PRICING.md @ 2026-05-25  
Cost-Source: computed  
Date: 2026-05-29  
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2  
Source: results/opencode-kimi_k2_6_ollama_cloud/project  
Benchmark-Result: /home/hugo/projects/python-benchmark/results/opencode-kimi_k2_6_ollama_cloud/result.json  
Primary-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5  
Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5

I. **Killer strength** + **Killer weakness**
Killer strength: correct async LangChain/Ollama streaming path from service to WebSocket. Killer weakness: serious hygiene gaps around secrets, frontend build reproducibility, prod hardening, and false-green tests.
