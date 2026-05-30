"""Shared pytest fixtures."""

from __future__ import annotations

import os

import django
from django.conf import settings

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def pytest_configure() -> None:
    if not settings.configured:
        settings.configure(
            SECRET_KEY="test-secret-key-for-pytest-only",
            DEBUG=True,
            ALLOWED_HOSTS=["*"],
            INSTALLED_APPS=[
                "daphne",
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "django.contrib.sessions",
                "channels",
                "chat",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
            ROOT_URLCONF="config.urls",
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [os.path.join(os.path.dirname(__file__), "..", "templates")],
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "context_processors": [
                            "django.template.context_processors.request",
                        ],
                    },
                }
            ],
            STATIC_URL="/static/",
            ASGI_APPLICATION="config.asgi.application",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        )
    django.setup()
