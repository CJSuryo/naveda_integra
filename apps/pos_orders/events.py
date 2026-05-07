from channels.layers import get_channel_layer


async def broadcast(store_id: int, group_prefix: str, event_type: str, data: dict) -> None:
    """Send an event to all connected WebSocket clients in a store group."""
    layer = get_channel_layer()
    await layer.group_send(
        f'{group_prefix}_{store_id}',
        {
            'type': 'order.update',
            'data': {'event': event_type, **data},
        }
    )
