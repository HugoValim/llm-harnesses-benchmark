"""Django settings for the Ollama chat project.

Configuration is environment-driven. No secrets are hardcoded: the secret key
must be supplied through ``DJANGO_SECRET_KEY`` (or ``SECRET_KEY``) in any
non-debug deployment.
"""

from __future__ import annotations

import os
import secrets
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean flag from the environment."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    """Read a comma-separated list from the environment."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# SECURITY: DEBUG defaults to False so production/Docker is safe by default.
DEBUG = _env_flag("DJANGO_DEBUG", default=False)


def _resolve_secret_key() -> str:
    """Resolve the secret key from the environment.

    The key is read from ``DJANGO_SECRET_KEY`` (or ``SECRET_KEY``). There is no
    hardcoded fallback and no placeholder literal in source. When neither is
    set, an ephemeral key is generated at runtime so local development, tests,
    and static analysis work without persisting a secret. In a non-DEBUG
    deployment this is a misconfiguration (sessions and signatures will not
    survive a restart), so a loud warning is emitted; supply
    ``DJANGO_SECRET_KEY`` to silence it.
    """
    key = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if key:
        return key
    if not DEBUG:
        warnings.warn(
            "DJANGO_SECRET_KEY (or SECRET_KEY) is not set; using an ephemeral key. "
            "Set it in production: python -c 'import secrets; print(secrets.token_urlsafe(64))'",
            RuntimeWarning,
            stacklevel=2,
        )
    return secrets.token_urlsafe(64)


SECRET_KEY = _resolve_secret_key()

# SECURITY: never default to ["*"]. Narrow list from env, localhost otherwise.
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Both WSGI (admin/static fallback) and ASGI (Channels) entrypoints exist.
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# In-memory channel layer: no external broker required for this single-node app.
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# WhiteNoise serves from the staticfiles finders so the app boots and serves
# assets without a prior `collectstatic`. Compression is applied at
# `collectstatic` time for production; rendering never depends on a manifest.
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Production hardening applied only when DEBUG is off (i.e. real deployments).
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = _env_flag("DJANGO_SECURE_COOKIES", default=False)
    CSRF_COOKIE_SECURE = _env_flag("DJANGO_SECURE_COOKIES", default=False)
