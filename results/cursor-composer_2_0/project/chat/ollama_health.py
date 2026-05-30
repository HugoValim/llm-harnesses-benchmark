"""
Ollama reachability checks (no secrets returned).
"""

from __future__ import annotations

import os

import httpx


def ollama_reachable_sync(timeout_seconds: float = 2.0) -> tuple[bool, str | None]:
    """
    Return (ok, error_kind) where error_kind is a short, non-sensitive classifier.
    """
    base = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    url = f"{base}/api/tags"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"http_error:{type(exc).__name__}"
    except OSError as exc:
        return False, f"os_error:{type(exc).__name__}"
    return True, None
