from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig, WebPushSubscription
from apps.accounts.models import User, Role


def make_store_and_subscription():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Pusat')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
    user = User.objects.create_user(email='kasir@test.com', password='pass', name='Budi', role=role)
    sub = WebPushSubscription.objects.create(
        user=user, store=store,
        endpoint='https://fcm.googleapis.com/fcm/send/test123',
        p256dh_key='BBBBBBBBB',
        auth_key='AAAAAAA',
        role=WebPushSubscription.ROLE_CASHIER,
    )
    return store, sub


@override_settings(
    VAPID_PRIVATE_KEY='test_private_key',
    VAPID_PUBLIC_KEY='test_public_key',
    VAPID_CLAIM_EMAIL='test@test.com',
)
class PushServiceTest(TestCase):
    @patch('pywebpush.webpush')
    def test_sends_push_to_active_subscriptions(self, mock_webpush):
        store, sub = make_store_and_subscription()
        from pos_orders.services.push_service import send_push_to_store
        send_push_to_store(
            store.pk, WebPushSubscription.ROLE_CASHIER,
            'Test Title', 'Test Body', {'url': '/pos/'},
        )
        self.assertTrue(mock_webpush.called)

    @patch('pywebpush.webpush')
    def test_marks_subscription_inactive_on_410(self, mock_webpush):
        from pywebpush import WebPushException
        store, sub = make_store_and_subscription()
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_webpush.side_effect = WebPushException('Gone', response=mock_response)
        from pos_orders.services.push_service import send_push_to_store
        send_push_to_store(
            store.pk, WebPushSubscription.ROLE_CASHIER,
            'Test', 'Body', {'url': '/'},
        )
        sub.refresh_from_db()
        self.assertFalse(sub.is_active)

    @patch('pywebpush.webpush')
    def test_skips_inactive_subscriptions(self, mock_webpush):
        store, sub = make_store_and_subscription()
        sub.is_active = False
        sub.save()
        from pos_orders.services.push_service import send_push_to_store
        send_push_to_store(store.pk, WebPushSubscription.ROLE_CASHIER, 'T', 'B', {})
        mock_webpush.assert_not_called()
