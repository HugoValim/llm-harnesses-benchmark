A. The submission produced zero project files; the Codex harness errored with "Invalid tool type" immediately and stalled, leaving only the injected AGENTS.md and CLAUDE.md.

B. Scores per dimension

| # | Dimension | Score / Max | Justification |
|---|-----------|-------------|---------------|
| 1 | Deliverable completeness | 0 / 25 | `result.json:82` file_count=2 (only harness-injected files); Dockerfile, compose, requirements/README/.env.example, ASGI app, all tool configs absent. |
| 2 | LLM integration correctness | 0 / 20 | No code produced; no imports, streaming methods, env wiring, or Ollama client present. |
| 3 | Test quality | 0 / 15 | No test files. |
| 4 | Error handling | 0 / 10 | No code. |
| 5 | Persistence / multi-turn state | 0 / 10 | No code. |
| 6 | Streaming & frontend wiring | 0 / 10 | No templates, HTMX, WebSocket consumer, or static files. |
| 7 | Architecture | 0 / 5 | No code. |
| 8 | Secrets & config hygiene | 0 / 3 | No config files; no SECRET_KEY literal, but zero hygiene demonstrated. |
| 9 | Production hardening | 0 / 2 | No Dockerfile/healthcheck, no logging config. |

C. **0 / 100**

D. **D (0–40)** — throw away or use only for architectural inspiration.

E. Verification section

No API calls present in submission; no hallucination claims required. `project/.venv` does not exist → package-source verification unverified for this run per U1 preflight evidence.

F. Critical Failures

- `result.json:82` → CF#2: Dockerfile entirely absent.
- `result.json:82` → CF#2: docker-compose.yml entirely absent.
- `result.json:82` → CF#5: requirements.txt / pyproject.toml absent; all spec-required dev tools (pytest, ruff, mypy, bandit, coverage, pip-audit) undeclared.
- `result.json:82` → CF#2: README.md entirely absent.
- `result.json:82` → CF#2: HTMX with WebSocket extension entirely absent.
- `result.json:82` → CF#2: tests entirely absent.

G. Critical-failure ledger

- `result.json:82` → "Missing/broken Dockerfile: -5" → D1 deduction -5
- `result.json:82` → "Missing docker-compose.yml: -5" → D1 deduction -5
- `result.json:82` → "Missing requirements.txt OR pyproject.toml: -5" → D1 deduction -5
- `result.json:82` → "README has actual content (NOT the stock template). Stock template: -5" → D1 deduction -5
- `result.json:82` → "No HTMX ws ext or equivalent JS streaming: -4" → D6 deduction -4
- `result.json:82` → "Tests don't exercise LLM path (constants/import smoke only): -10" → D3 deduction -10

H. Submission metadata

- Model: gemini-3-flash-preview:cloud
- Harness: codex (ollama launch codex)
- Generation-Time: 372.08 s
- Input-Tokens: 0
- Output-Tokens: 0
- Total-Tokens: 0
- Estimated-Cost-USD: $0.00 (0 tokens consumed; model row missing from PRICING.md)
- Pricing-Source: n/a — model not present in benchmark-ai-code PRICING.md @ 2026-05-09
- Date: 2026-05-15
- Prompt-Version: v2.1
- Source: /home/hugo/projects/python-benchmark/results/codex-gemini_3_flash_preview_ollama_cloud/

I. Killer strength / Killer weakness

- **Killer strength**: n/a — no code produced.
- **Killer weakness**: Total harness failure; the model never emitted a tool call or file, stalling on an "Invalid tool type" error.
