"""Shared agent-run timeout defaults for build, audit, and meta-analysis."""

from __future__ import annotations

DEFAULT_TIMEOUT_MINUTES = 50
DEFAULT_NO_PROGRESS_MINUTES = 15

DEFAULT_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_MINUTES * 60
DEFAULT_NO_PROGRESS_TIMEOUT_SECONDS = DEFAULT_NO_PROGRESS_MINUTES * 60


def timeout_cli_flags() -> list[str]:
    """Argv fragment for ``--timeout-minutes`` and ``--no-progress-minutes``."""
    return [
        "--timeout-minutes",
        str(DEFAULT_TIMEOUT_MINUTES),
        "--no-progress-minutes",
        str(DEFAULT_NO_PROGRESS_MINUTES),
    ]


def meta_timeout_cli_flags() -> list[str]:
    """Argv fragment for ``run_meta_analysis.py`` timeout flags."""
    return [
        "--meta-timeout-minutes",
        str(DEFAULT_TIMEOUT_MINUTES),
        "--no-progress-minutes",
        str(DEFAULT_NO_PROGRESS_MINUTES),
    ]
