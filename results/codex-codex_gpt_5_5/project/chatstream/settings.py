import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def _required_secret_key() -> str:
    value = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if value:
        return value
    message = "DJANGO_SECRET_KEY/SECRET_KEY missing; expected non-empty env value."
    raise ImproperlyConfigured(message)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    expected = "true/false, 1/0, yes/no, or on/off"
    raise ImproperlyConfigured(f"{name}={raw!r} invalid; expected {expected}.")


def _env_host_list(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    hosts = [host.strip() for host in raw.split(",") if host.strip()]
    if not hosts:
        raise ImproperlyConfigured(f"{name}={raw!r} invalid; expected hosts.")
    if "*" in hosts:
        raise ImproperlyConfigured(f"{name}={raw!r} invalid; wildcard forbidden.")
    return hosts


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = _required_secret_key()
DEBUG = _env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = _env_host_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.staticfiles",
    "channels",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "chatstream.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

ASGI_APPLICATION = "chatstream.asgi.application"
WSGI_APPLICATION = "chatstream.wsgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
