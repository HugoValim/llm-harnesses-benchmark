# A. Quick Summary
Submission partially meets the spec: core Django/Channels/Ollama streaming exists, but dependency reproducibility, multi-turn state, HTMX DOM streaming, and prod hardening are weak.

# B. Scores Per Dimension
| # | Dimension | Score / Max | Justification |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 6 / 15 | Docker/compose/README exist, but no dependency manifest deps in `pyproject.toml:1`; auth is present despite “no auth” at `config/settings.py:16`; pip-audit has README invocation but no config (`pyproject.toml:1`). |
| 2 | D2 LLM integration correctness | 8 / 10 | Correct `langchain_ollama` + `ChatOllama(...).astream` path in `chat/llm_service.py:4` and `chat/llm_service.py:19`; no multi-turn context, only latest user msg in `chat/consumers.py:42`. |
| 3 | D3 Test quality | 8 / 10 | Consumer chunk assertions exist at `chat/tests/test_consumers.py:121`, but tests mock only `get_ollama_service` at `chat/tests/test_consumers.py:93` and never exercise `chat/llm_service.py` wiring. |
| 4 | D4 Error handling | 4 / 10 | LLM loop catches errors at `chat/consumers.py:49`, but no unreachable-Ollama preflight (`chat/llm_service.py:23`) and JSON errors are not user-visible HTMX fragments (`chat/consumers.py:62`). |
| 5 | D5 Persistence / multi-turn | 1 / 5 | No history accumulation; every request rebuilds `[system, user]` only at `chat/consumers.py:42`. |
| 6 | D6 Streaming & frontend | 8 / 10 | HTMX ws route is present at `chat/templates/chat/index.html:11`, but streamed JSON tokens at `chat/consumers.py:53` are not DOM fragments, so token updates are not visible. |
| 7 | D7 Architecture | 6 / 15 | Has service module, but no settings split (`config/settings.py:1`), consumer class is 60 nonblank lines, service uses `Any` not a protocol (`chat/llm_service.py:18`), and LLM imports leak into views (`chat/views.py:8`). |
| 8 | D8 Secrets & config hygiene | 5 / 5 | `SECRET_KEY` is env-only with startup failure at `config/settings.py:6`; `DEBUG` defaults false at `config/settings.py:10`; hosts are narrowed at `config/settings.py:12`. |
| 9 | D9 Production hardening | 0 / 10 | No Docker/compose healthcheck, restart policy, `USER`, structured logging, or SIGTERM stream handling (`Dockerfile:1`, `docker-compose.yml:1`, `config/settings.py:1`). |
| 10 | D10 Code quality | 8 / 10 | Type-safety debt despite mypy: `Any` in `chat/llm_service.py:18`, `dict[str, Any]` in `chat/consumers.py:32`, and `type: ignore` in `config/asgi.py:18`. |

# C. Total Score
54 / 100.

# D. Practical Tier
C (41-60): major rework needed; core streaming exists, but user-visible streaming, multi-turn behavior, reproducible deps, and production readiness need fixes.

# E. Verification
Installed-package verification: `.venv` is absent (`find .venv` returned `find: '.venv': No such file or directory`), and all required source globs under `.venv/lib/python3.*/site-packages/...` failed. Therefore API source verification is unverified; no API call is classified as hallucinated.

# F. Critical Failures
- CF#5 `pyproject.toml:1`: spec-required packages are not declared in `requirements*.txt` or `[project] dependencies`; deps appear only as ad hoc Docker/README install commands (`Dockerfile:11`, `README.md:20`), so the dev env is not reproducible.

# G. Critical-Failure Ledger
`pyproject.toml:1` -> CF#5 “Missing dependency declarations: spec-required tools absent from requirements*.txt / pyproject.toml” -> no direct D1 trigger for empty dependency manifest; -5 from D1.

# H. Submission Metadata & Generation Metrics
Model: minimax_m2_7_ollama_cloud  
Harness: opencode  
Harness-CLI-Version: n/a  
Generation-Time: 2347.07 seconds  
Input-Tokens: 107678  
Output-Tokens: 224  
Total-Tokens: 107902  
Estimated-Cost-USD: 0.030311  
Pricing-Source: docs/PRICING.md @ 2026-05-25  
Cost-Source: computed  
Benchmark-Result: /home/hugo/projects/python-benchmark/results/opencode-minimax_m2_7_ollama_cloud/result.json  
Date: 2026-05-29  
Prompt-Version: audit-v3.8; primary benchmark-v3.2; follow-up benchmark-followup-v3.2  
Source: results/opencode-minimax_m2_7_ollama_cloud/project  
Primary-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5  
Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5

# I. Killer Strength / Killer Weakness
Killer strength: the core async `ChatOllama.astream` service and Channels consumer path are present and chunk-tested.  
Killer weakness: the UI receives JSON over HTMX ws instead of HTML fragments, so benchmark-required partial DOM token streaming is not actually visible.
