from django.urls import path

from .consumers import OrderBoardConsumer

websocket_urlpatterns = [
    path('ws/pos/branch/<int:store_pk>/orders/', OrderBoardConsumer.as_asgi()),
]
