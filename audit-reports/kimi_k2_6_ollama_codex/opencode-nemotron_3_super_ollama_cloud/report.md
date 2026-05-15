A. **Quick summary line**
Submission is an incomplete Django Channels scaffold missing Docker, README, tests, .env.example, and a reachable template; the ASGI file has an unimported `get_asgi_application` and the consumer broadcasts every LLM call to all connected tabs.

B. **Scores per dimension**

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 0 / 25 | Dockerfile absent (-5), docker-compose absent (-5), README absent (-5), zero tool configs (-5), Tailwind CDN-only with dead `tailwind.config.js` (-2), no `.env.example` (-2), ASGI server missing from Dockerfile (-3). Floors at 0. |
| 2 | LLM integration correctness | 17 / 20 | `from langchain_ollama import ChatOllama` is correct; `.astream()` yields real chunks sent token-by-token. No multi-turn history (single-shot string passed to LLM) (-3). |
| 3 | Test quality | 0 / 15 | `chat/tests.py` is the empty Django stub; no tests exist for views, consumer, template, or LLM path (-10 -3 -3 -2 = 0). |
| 4 | Error handling | 0 / 10 | No try/except around `llm.astream()` in `chat/consumers.py:33` (-4); no Ollama preflight guard (U1) (-3); no degraded-UI signal on failure (U3) (-3). |
| 5 | Persistence / multi-turn state | 3 / 10 | No conversation history; every message is an independent one-shot (-7). |
| 6 | Streaming & frontend wiring | 0 / 10 | Single monolithic `index.html` with no `{% include %}` partials (-3); Tailwind CDN only, no built static files (-3); no chunk-by-chunk test assertions (-2); no try/except in consumer streaming loop (-2). Floors at 0. |
| 7 | Architecture | 2 / 5 | Consumer instantiates `ChatOllama` inline with no service layer (U4) (-3). `chatproject/asgi.py` uses `get_asgi_application()` without importing it (`from django.core.asgi import get_asgi_application` missing), so Channels will not boot. |
| 8 | Secrets & config hygiene | 3 / 3 | `SECRET_KEY` has no hardcoded fallback (`os.environ.get` + `ValueError`); `DEBUG` defaults to `False`; `ALLOWED_HOSTS` from env. |
| 9 | Production hardening | 0 / 2 | No Dockerfile/compose → no HEALTHCHECK (-1); no `logging` setup (-1). |

C. **Total score / 100**
25 / 100

D. **Practical tier**
**D (0–40)**: throw away or use only for architectural inspiration. The app cannot boot (`asgi.py` NameError), the template is unreachable (`project/templates/chat/index.html` is outside any installed app; `DIRS: []`), and roughly half the spec deliverables are missing.

E. **Verification section**
No venv exists at `project/.venv` and `langchain_ollama` is not installed system-wide; package-source verification is unverified for this run. No API calls are claimed as hallucinated.

F. **Critical Failures**
- `Dockerfile` entirely absent (CF#2). Spec hard-requirement #13.
- `docker-compose.yml` entirely absent (CF#2). Spec hard-requirement #13.
- `README.md` entirely absent (CF#2). Spec hard-requirement #14.
- `.env.example` entirely absent (CF#2). Spec hard-requirement #16.
- Tool configs for ruff, mypy, bandit, coverage, and pip-audit entirely absent despite `requirements.txt` declaring them (CF#6). Spec hard-requirement #12.

G. **Critical-failure ledger**
- `project/:1` (Dockerfile absent) → D1 trigger "Dockerfile present AND has valid Python (3.10+). Missing/broken: -5" → -5
- `project/:1` (docker-compose.yml absent) → D1 trigger "docker-compose.yml present. Missing: -5" → -5
- `project/:1` (README.md absent) → D1 trigger "README has actual content (NOT the stock template). Stock template: -5" → -5
- `project/:1` (.env.example absent) → D1 trigger "No .env.example (or equivalent) documenting OLLAMA_HOST / OLLAMA_MODEL: -2" → -2
- `project/:1` (no [tool.ruff], [tool.mypy], .bandit, [tool.coverage], pip-audit config) → D1 trigger "Each missing tool config (ruff, mypy, bandit, coverage, pip-audit): -1" × 5 missing → -5

H. **Submission metadata & generation metrics**
- Model: nemotron-3-super:cloud
- Harness: opencode
- Generation-Time: 485.98 s
- Input-Tokens: 0
- Output-Tokens: 0
- Total-Tokens: 0
- Estimated-Cost-USD: $0.00 (tokens reported as 0 by harness)
- Pricing-Source: n/a — model not listed in PRICING.md; zero tokens make cost $0.00 regardless
- Date: 2026-05-15
- Prompt-Version: v2.1
- Source: /home/hugo/projects/python-benchmark/results/opencode-nemotron_3_super_ollama_cloud

I. **Killer strength** + **Killer weakness**
- **Killer strength**: Settings correctly avoid hardcoded secrets and default `DEBUG` to `False`.
- **Killer weakness**: The submission stalled before finishing half the spec deliverables; the ASGI file cannot boot, the template is orphaned in a non-app directory, and `chat/tests.py` is completely empty.
