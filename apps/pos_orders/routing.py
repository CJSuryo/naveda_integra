from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/pos/cashier/(?P<store_id>\d+)/$', consumers.CashierConsumer.as_asgi()),
    re_path(r'^ws/pos/kitchen/(?P<store_id>\d+)/$', consumers.KitchenConsumer.as_asgi()),
]
