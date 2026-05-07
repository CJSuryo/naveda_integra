from django.test import TestCase, override_settings
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from naveda_integra.asgi import application
from apps.accounts.models import User, Role, NiPermission
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig

TEST_CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}


@database_sync_to_async
def make_store_and_user():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Pusat')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
    user = User.objects.create_user(email='kasir@test.com', password='pass', name='Budi', role=role)
    perm, _ = NiPermission.objects.get_or_create(code='pos_cashier', defaults={'name': 'POS Cashier', 'module': 'pos'})
    user.ni_permissions.add(perm)
    return store, user


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class CashierConsumerTest(TestCase):
    async def test_can_connect_and_receive_event(self):
        store, user = await make_store_and_user()

        communicator = WebsocketCommunicator(
            application, f'/ws/pos/cashier/{store.pk}/'
        )
        communicator.scope['user'] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Simulate broadcast to the group
        layer = get_channel_layer()
        await layer.group_send(
            f'cashier_{store.pk}',
            {'type': 'order.update', 'data': {'event': 'order.new', 'order_number': 'ORD-TST-001'}}
        )
        message = await communicator.receive_json_from()
        self.assertEqual(message['event'], 'order.new')
        self.assertEqual(message['order_number'], 'ORD-TST-001')

        await communicator.disconnect()
