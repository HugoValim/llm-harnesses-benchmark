A. **Quick summary line**
Submission misses core benchmark requirements: streaming exists server-side, but frontend, config hygiene, production hardening, and verification are not shippable.

B. **Scores per dimension**

| # | Dimension | Score / Max | Justification (file:line) |
|---|---|---:|---|
| 1 | D1 Deliverable completeness | 0 / 15 | Docker build path needs env secret during `collectstatic` (`Dockerfile:26`, `config/settings.py:25`); auth present (`config/settings.py:39`); Tailwind CLI missing (`package.json:15`); unconfigured tools despite claim (`VERIFY.md:26`); unused deps (`requirements.txt:37-39,71`). |
| 2 | D2 LLM integration correctness | 7 / 10 | Uses `langchain_ollama` and `.astream` (`chat/services/ollama_service.py:2`, `chat/consumers.py:37`), but no multi-turn history (`chat/consumers.py:37`) and tests lack chunk-by-chunk assertion (`chat/tests.py:97-115`). |
| 3 | D3 Test quality | 8 / 10 | Has view and consumer tests (`chat/tests.py:9`, `chat/tests.py:22`), but CF#9 caps score: joined-output assertions would pass buffered streaming (`chat/tests.py:109-115`). |
| 4 | D4 Error handling | 1 / 10 | No Ollama preflight/validation beyond constructing client (`chat/services/ollama_service.py:11-13`), bare disconnect (`chat/consumers.py:17-18`), error path sends JSON not DOM partial (`chat/consumers.py:51-55`). |
| 5 | D5 Persistence / multi-turn | 1 / 5 | No accumulated conversation state; each call streams only current text (`chat/consumers.py:20-37`). |
| 6 | D6 Streaming & frontend | 0 / 10 | Single template/no partial include (`chat/templates/chat/index.html:1-17`); HTMX receives JSON not HTML (`chat/consumers.py:48-55`); `ws-receive` targets missing `#messages` (`chat/templates/chat/index.html:5`); Tailwind CLI not reproducible (`package-lock.json:15-20`). |
| 7 | D7 Architecture | 2 / 15 | Consumer owns LLM streaming instead of service boundary (`chat/consumers.py:33-49`); factory is untyped raw client (`chat/services/ollama_service.py:5-13`); no Docker/prod settings split (`config/settings.py:1`); consumer exceeds 30 nonblank lines. |
| 8 | D8 Secrets & config hygiene | 0 / 5 | Hardcoded `.env` secrets cap dimension at zero (`.env:14`, `.env:17`); `.env` also defaults debug on (`.env:22`). |
| 9 | D9 Production hardening | 0 / 10 | No healthcheck/restart/non-root user (`Dockerfile:1-35`, `docker-compose.yml:1-20`); no structured `LOGGING` config (`config/settings.py:142`); no WebSocket shutdown handling (`chat/consumers.py:17-18`). |
| 10 | D10 Code quality | 7 / 10 | -2 type gaps on public APIs (`chat/services/ollama_service.py:5`, `chat/consumers.py:8`); -1 maintainability for duplicated inline HTML fragments in consumer (`chat/consumers.py:29`, `chat/consumers.py:47`, `chat/consumers.py:54`). |

C. **Total score / 100**
26 / 100.

D. **Practical tier**
D (0-40): throw away or use only for architectural inspiration.

E. **Verification section**
No hallucinated API calls claimed. Package-source verification is unverified because the project venv is absent: `ls -ld .../project/.venv` returned `No such file or directory`. The code uses likely-correct but unverified `ChatOllama`/`.astream` (`chat/services/ollama_service.py:2`, `chat/consumers.py:37`).

F. **Critical Failures**
- `.env:14` / `.env:17` - CF#1 hardcoded Django secret values.
- `.env:22` - CF#10 `.env*` defaults to `DEBUG=true`.
- `chat/consumers.py:17-18` - CF#11 `disconnect` is bare `pass`.
- `chat/tests.py:97-115` - CF#9 test accepts joined output, so buffered streaming can pass.
- `package.json:15`, `package-lock.json:15-20` - CF#2 official Tailwind CLI deliverable absent; installed package exposes no local CLI.
- `VERIFY.md:26` - CF#6 claims required tooling configured, but only `mypy.ini:1` exists for those tools.

G. **Critical-failure ledger**
- `.env:14` -> CF#1 "Any hardcoded secret..." -> D8 cap 0, -5.
- `.env:22` -> CF#10 "`.env*` defaults to `DEBUG=True`" -> D8 -2, already capped.
- `chat/consumers.py:17` -> CF#11 "bare-`pass` disconnect" -> D4 -3.
- `chat/tests.py:97` -> CF#9 "tests pass against an anti-pattern" -> D3 cap 8, -2.
- `package.json:15` -> CF#2 "spec hard-requirement deliverable absent" -> D1 Tailwind CLI -2 and D6 Tailwind wiring -3.
- `VERIFY.md:26` -> CF#6 "tooling claimed... but unconfigured" -> D1 missing ruff/bandit/coverage configs, -3.

H. **Submission metadata & generation metrics**
Model: nemotron_3_super_ollama_cloud; Harness: codex; Harness-CLI-Version: n/a; Generation-Time: 2021.98 seconds; Input-Tokens: 5194713; Output-Tokens: 82401; Total-Tokens: 5277114; Estimated-Cost-USD: 0.504605; Pricing-Source: docs/PRICING.md @ 2026-05-25; Cost-Source: computed; Date: 2026-05-29; Prompt-Version: audit-v3.8; Primary-Benchmark-Prompt: benchmark-v3.2; Followup-Prompt: benchmark-followup-v3.2; Source: results/codex-nemotron_3_super_ollama_cloud/project; Benchmark-Result: /home/hugo/projects/python-benchmark/results/codex-nemotron_3_super_ollama_cloud/result.json; Primary-Prompt-SHA256: 14d18a37c91098a78ee7a8488f9386e25ab226178d7cd0020802256e9b4bbc5b; Followup-Prompt-SHA256: c224e7df59e60904bae7d1eb4b06abbf08f814cfe95effe0e025b1a67ece2ed5.

I. **Killer strength** + **Killer weakness**
Killer strength: it found the right high-level Django Channels + `ChatOllama.astream` shape. Killer weakness: secrets/config and frontend streaming contract are broken enough that the app is not production-usable.
