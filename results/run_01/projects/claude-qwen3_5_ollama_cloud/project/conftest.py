"""
Pytest configuration and fixtures.
"""

import os

import pytest

# Set required Django settings before Django initializes
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benchmark_chat.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-testing-only")


@pytest.fixture(autouse=True)
def set_test_secret_key():
    """Ensure SECRET_KEY is set for all tests."""
    os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-testing-only")
