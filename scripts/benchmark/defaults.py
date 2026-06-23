"""Shared defaults for audit and meta-analysis dispatch."""

from __future__ import annotations

# Composer 2.5 via Cursor Agent CLI (config/models.json: composer_2_5).
DEFAULT_AUDITOR_SLUG = "composer_2_5"

# Harness for DEFAULT_AUDITOR_SLUG (cursor provider -> cursor).
DEFAULT_AUDIT_HARNESS = "cursor"

# Default concurrent workers for benchmark build and full-pipeline phases.
DEFAULT_JOBS = 3

# Default concurrent audit dispatches for ``scripts/run_audit.py``.
DEFAULT_AUDIT_JOBS = 5
