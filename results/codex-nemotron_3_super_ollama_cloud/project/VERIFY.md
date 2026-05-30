# Verification Summary

| Command | Result | Evidence or Blocker |
|---------|--------|---------------------|
| `mise --version` | Success | mise version 2026.5.13 |
| `mise use python 3.13.13` | Success | Python 3.13.13 activated |
| `python --version` | Success | Python 3.13.13 |
| `pip install -r requirements.txt` | Success | Dependencies installed |
| `npm install` | Success | Node.js dependencies installed |
| `npm run buildcss` | Success | Tailwind CSS built to `static/css/tailwind.css` (size: 2528 bytes) |
| `pytest chat/tests.py::IndexViewTest` | Success | 2 tests passed |
| `ruff check .` | Success | No errors |
| `ruff format --check .` | Success | All files formatted |
| `mypy .` | Success | No issues found |
| `bandit -r .` | Success | No issues identified |
| `coverage run -m pytest chat/tests.py::IndexViewTest` | Success | Tests passed under coverage |
| `coverage report` | Success | Overall coverage 44% (see details) |
| `pip-audit` | Success (with known vulnerabilities) | Found 2 known vulnerabilities in transitive dependencies (pytest 8.4.2: CVE-2025-71176, starlette 0.50.0: PYSEC-2026-161). These are due to dependency constraints and cannot be upgraded without breaking compatibility. |
| `ollama pull qwen2.5:7b` | Not run | Manual step required; users must pull the Ollama model before running the application. |
| Docker build | Not run | Dockerfile and docker-compose.yml are present and configured. |
| Docker run | Not run | Manual step required; users can run `docker compose up` after setting environment variables. |

Notes:
- The SECRET_KEY is read from the environment variables DJANGO_SECRET_KEY or SECRET_KEY, with no hardcoded fallback.
- The application uses Docker and docker-compose for containerized deployment.
- All required tooling (ruff, mypy, bandit, coverage, pip-audit) is configured and has been run.
