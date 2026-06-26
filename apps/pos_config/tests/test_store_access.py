"""Security: POS store access scoping (cross-store IDOR prevention).

A user may only reach stores under entities they are linked to via
UserEntitasBisnis. Superusers see all stores.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.accounts.models import UserEntitasBisnis
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from pos_config.access import accessible_store_qs

User = get_user_model()


def _make_store(eb, name):
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama=name)
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb)
    return StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)


class StoreAccessScopingTest(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='T')
        self.eb_a = EntitasBisnis.objects.create(
            nama='A', standar_akuntansi='psak', tipe_entitas=self.tipe)
        self.eb_b = EntitasBisnis.objects.create(
            nama='B', standar_akuntansi='psak', tipe_entitas=self.tipe)
        self.store_a = _make_store(self.eb_a, 'Store A')
        self.store_b = _make_store(self.eb_b, 'Store B')
        self.user = User.objects.create_user(email='u@x.id', password='p')
        UserEntitasBisnis.objects.create(user=self.user, entitas_bisnis=self.eb_a)
        self.admin = User.objects.create_user(email='admin@x.id', password='p')
        self.admin.is_superuser = True
        self.admin.save()

    def test_user_sees_only_linked_store(self):
        ids = set(accessible_store_qs(self.user).values_list('pk', flat=True))
        self.assertEqual(ids, {self.store_a.pk})

    def test_superuser_sees_all_stores(self):
        ids = set(accessible_store_qs(self.admin).values_list('pk', flat=True))
        self.assertEqual(ids, {self.store_a.pk, self.store_b.pk})
