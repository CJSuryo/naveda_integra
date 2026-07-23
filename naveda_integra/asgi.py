"""
ASGI config for naveda_integra project.

Exposes the ASGI callable as a module-level variable named ``application``.
Django Channels supports the live order board's WebSocket alongside HTTP.

Note the import order: ``django.setup()`` must run before any module that
touches models is imported, which is why the routing import sits below it.
"""

import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naveda_integra.settings')
django.setup()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from pos_aggregator.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
