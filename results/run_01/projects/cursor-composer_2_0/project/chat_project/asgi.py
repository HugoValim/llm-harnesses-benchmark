"""
ASGI entrypoint: HTTP (Django) + WebSocket (Channels).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Imports after `load_dotenv()` so local `.env` is applied before Django settings import.
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from chat.routing import websocket_urlpatterns  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chat_project.settings")

django_asgi_app = get_asgi_application()

websocket_stack = AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns))

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": websocket_stack,
    }
)
