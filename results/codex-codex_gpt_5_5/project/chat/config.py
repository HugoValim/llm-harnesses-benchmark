from dataclasses import dataclass
from os import environ
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


@dataclass(frozen=True)
class OllamaSettings:
    host: str
    model: str


def read_ollama_settings() -> OllamaSettings:
    """Return env-driven Ollama settings.

    Example:
        config = read_ollama_settings()
    """
    host = _normalized_host(environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    model = _normalized_model(environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    return OllamaSettings(host=host, model=model)


def _normalized_host(raw_host: str) -> str:
    host = raw_host.strip().rstrip("/")
    parsed = urlparse(host)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        expected = "http(s) URL with host, e.g. http://localhost:11434"
        raise ImproperlyConfigured(
            f"OLLAMA_HOST={raw_host!r} invalid; expected {expected}."
        )
    return host


def _normalized_model(raw_model: str) -> str:
    model = raw_model.strip()
    if not model or any(character.isspace() for character in model):
        expected = "non-empty Ollama model name without whitespace"
        raise ImproperlyConfigured(
            f"OLLAMA_MODEL={raw_model!r} invalid; expected {expected}."
        )
    return model
