"""Security: POS access scoping (cross-tenant IDOR prevention).

A user may only reach stores and merchants under lv1 entities they are linked to
via UserEntitasBisnis. Superusers see everything.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.accounts.models import UserEntitasBisnis
from pos_config.access import accessible_merchant_qs, accessible_store_qs

from .factories import make_lv1, make_lv2, make_lv3, make_merchant, make_store

User = get_user_model()


class AccessScopingTest(TestCase):
    def setUp(self):
        self.eb_a = make_lv1(nama='Grup A')
        self.eb_b = make_lv1(nama='Grup B')

        lv2_a = make_lv2(self.eb_a, nama='PT A')
        lv2_b = make_lv2(self.eb_b, nama='PT B')
        self.merchant_a = make_merchant(lv2_a)
        self.merchant_b = make_merchant(lv2_b)
        self.store_a = make_store(self.merchant_a, make_lv3(lv2_a, nama='Cabang A'))
        self.store_b = make_store(self.merchant_b, make_lv3(lv2_b, nama='Cabang B'))

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

    def test_user_sees_only_linked_merchant(self):
        ids = set(accessible_merchant_qs(self.user).values_list('pk', flat=True))
        self.assertEqual(ids, {self.merchant_a.pk})

    def test_superuser_sees_all_merchants(self):
        ids = set(accessible_merchant_qs(self.admin).values_list('pk', flat=True))
        self.assertEqual(ids, {self.merchant_a.pk, self.merchant_b.pk})

    def test_unlinked_user_sees_nothing(self):
        stranger = User.objects.create_user(email='none@x.id', password='p')
        self.assertEqual(accessible_store_qs(stranger).count(), 0)
        self.assertEqual(accessible_merchant_qs(stranger).count(), 0)
