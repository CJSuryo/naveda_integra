from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from pos_config.models import StorePOSConfig


@database_sync_to_async
def user_has_perm(user, perm_code):
    return user.has_ni_perm(perm_code)


class CashierConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.store_id = self.scope['url_route']['kwargs']['store_id']
        user = self.scope['user']

        if not user.is_authenticated or not await user_has_perm(user, 'pos_cashier'):
            await self.close(code=4003)
            return

        self.group_name = f'cashier_{self.store_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_update(self, event):
        await self.send_json(event['data'])


class KitchenConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.store_id = self.scope['url_route']['kwargs']['store_id']
        user = self.scope['user']

        if not user.is_authenticated or not await user_has_perm(user, 'pos_cashier'):
            await self.close(code=4003)
            return

        self.group_name = f'kitchen_{self.store_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_update(self, event):
        await self.send_json(event['data'])
