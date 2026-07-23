"""WebSocket consumer for the live order board.

Scope: one group per branch. A connection is only accepted after the user is
authenticated *and* proven to have access to that branch — otherwise anyone
could subscribe to another tenant's order stream by guessing a store id.

This is an enhancement, not the delivery guarantee. Orders are committed to the
database and pushed via web push before anything is emitted here.
"""
from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .services.realtime import store_group

logger = logging.getLogger(__name__)


class OrderBoardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        try:
            self.store_id = int(self.scope['url_route']['kwargs']['store_pk'])
        except (KeyError, TypeError, ValueError):
            await self.close(code=4400)
            return

        if not await self._may_access(user, self.store_id):
            await self.close(code=4403)
            return

        self.group_name = store_group(self.store_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, 'group_name', None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # The board is read-only; state changes go through authenticated HTTP
        # views so they are permission-checked and audited.
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def aggregator_event(self, message):
        await self.send_json({
            'type': message.get('event', 'order.new'),
            'payload': message.get('payload', {}),
        })

    @database_sync_to_async
    def _may_access(self, user, store_id: int) -> bool:
        from pos_config.access import accessible_store_qs
        return accessible_store_qs(user).filter(pk=store_id).exists()
