.PHONY: audit coverage css format-check lint security test typecheck

css:
	npm run build:css

test:
	.venv/bin/pytest

coverage:
	.venv/bin/coverage run -m pytest
	.venv/bin/coverage report

lint:
	.venv/bin/ruff check .

format-check:
	.venv/bin/ruff format --check .

typecheck:
	.venv/bin/mypy

security:
	.venv/bin/bandit -r .

audit:
	.venv/bin/pip-audit
