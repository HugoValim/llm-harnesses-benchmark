"""Regression tests for benchmark module import graph (no circular imports)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def test_cursor_runner_imports_cleanly() -> None:
    from benchmark.cursor_runner import run_variant  # noqa: F401
