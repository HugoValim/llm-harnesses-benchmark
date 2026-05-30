from __future__ import annotations

import os
import secrets
from pathlib import Path


def pytest_configure() -> None:
    """
    Ensure Django settings can import without leaking a committed SECRET_KEY.

    If the developer already exported DJANGO_SECRET_KEY / SECRET_KEY, keep it.
    """
    if not (os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY")):
        os.environ["SECRET_KEY"] = secrets.token_hex(32)

    repo_root = Path(__file__).resolve().parent
    (repo_root / "staticfiles").mkdir(exist_ok=True)
