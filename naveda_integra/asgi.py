"""
ASGI config for naveda_integra project.

Exposes the ASGI callable as a module-level variable named ``application``.
Django Channels is used to support WebSocket connections in addition to HTTP.

The legacy pos_orders websocket routing has been removed; there are currently
no websocket routes. A new POS will register its routes here in future.
"""

import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naveda_integra.settings')
django.setup()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([])
        )
    ),
})
