"""Shared pytest fixtures."""

from __future__ import annotations

import os
import secrets

import pytest


@pytest.fixture(autouse=True)
def django_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure Django settings load during tests without a committed secret."""
    if not os.environ.get("DJANGO_SECRET_KEY") and not os.environ.get("SECRET_KEY"):
        monkeypatch.setenv("DJANGO_SECRET_KEY", secrets.token_hex(32))
