"""Tests for OllamaBackend.list_active() result caching."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmark.backends as backends  # noqa: E402
from benchmark.backends import OllamaBackend  # noqa: E402


class _Counter:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls = 0

    def __call__(self, *_args, **_kwargs) -> dict | None:
        self.calls += 1
        return self.payload


class TestOllamaListActiveCache(unittest.TestCase):
    def test_rapid_repeat_calls_collapse_to_single_http(self) -> None:
        backend = OllamaBackend("http://127.0.0.1:11434")
        counter = _Counter({"models": [{"name": "qwen3:32b"}]})
        with patch.object(backends, "_get_json", counter):
            first = backend.list_active()
            second = backend.list_active()
        self.assertEqual(first, ["qwen3:32b"])
        self.assertEqual(second, ["qwen3:32b"])
        self.assertEqual(counter.calls, 1)

    def test_cache_invalidated_after_unload(self) -> None:
        backend = OllamaBackend("http://127.0.0.1:11434")
        list_counter = _Counter({"models": [{"name": "qwen3:32b"}]})
        unload_payload = {"done_reason": "unload"}
        with patch.object(backends, "_get_json", list_counter), patch.object(
            backends, "_post_json", lambda *a, **k: unload_payload
        ):
            backend.list_active()
            backend.unload("qwen3:32b")
            backend.list_active()
        self.assertEqual(list_counter.calls, 2)

    def test_cache_invalidated_after_preload(self) -> None:
        backend = OllamaBackend("http://127.0.0.1:11434")
        list_counter = _Counter({"models": []})
        preload_payload = {"done": True}
        with patch.object(backends, "_get_json", list_counter), patch.object(
            backends, "_post_json", lambda *a, **k: preload_payload
        ):
            backend.list_active()
            backend.preload("qwen3:32b")
            backend.list_active()
        self.assertEqual(list_counter.calls, 2)

    def test_cache_expires_after_ttl(self) -> None:
        backend = OllamaBackend("http://127.0.0.1:11434")
        list_counter = _Counter({"models": [{"name": "qwen3:32b"}]})
        with patch.object(backends, "_get_json", list_counter):
            backend.list_active()
            # Simulate TTL expiry by rewinding the cache timestamp.
            backend._list_active_cached_at -= 10.0
            backend.list_active()
        self.assertEqual(list_counter.calls, 2)

    def test_unreachable_server_not_cached(self) -> None:
        backend = OllamaBackend("http://127.0.0.1:11434")
        counter = _Counter(None)
        with patch.object(backends, "_get_json", counter):
            backend.list_active()
            backend.list_active()
        # None means server unreachable — never cache failure, always retry.
        self.assertEqual(counter.calls, 2)


if __name__ == "__main__":
    unittest.main()
