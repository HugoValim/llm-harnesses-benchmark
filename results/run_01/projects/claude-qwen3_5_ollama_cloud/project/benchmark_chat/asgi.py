"""
ASGI config for benchmark_chat project.
Channels + WebSocket routing.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benchmark_chat.settings")

django_asgi = get_asgi_application()

# Import after Django initialization (required for ASGI apps)
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402, I001
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi,
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),  # type: ignore[arg-type]
    }
)
