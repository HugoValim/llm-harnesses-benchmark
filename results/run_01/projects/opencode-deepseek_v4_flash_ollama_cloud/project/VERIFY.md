# Verification summary

Commands run against the project code in this workspace.

| Command | Result | Evidence / Blocker |
|---|---|---|
| `python --version` | 3.13.13 via mise | `mise exec python@3.13.13 -- python --version` |
| `pip install -r requirements.txt` | pass | All deps installed |
| `npx tailwindcss -i static/src/input.css -o static/css/output.css --minify` | pass | output.css generated |
| `python manage.py check` | pass | 0 issues |
| `python manage.py migrate` | pass | All migrations applied |
| `python -m pytest -v --cov` | 11 passed, 93% coverage | All tests pass; coverage >70% |
| `ruff check .` | pass | All checks passed |
| `ruff format --check .` | pass | 16 files already formatted |
| `mypy chat chat_project --config-file mypy.ini` | pass | Success: no issues found |
| `bandit -r . -c .bandit` | pass | No issues identified |
| `pip-audit` | 6 known vulns in *transitive* deps | Only in transitive deps (nicegui, starlette, twisted), not project code |

All commands were run with `DJANGO_SECRET_KEY` set to a generated value.
