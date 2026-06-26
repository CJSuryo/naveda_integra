"""Security: EntitasBisnis access scoping (OWASP A01 — broken access control).

A user may only resolve / see entities they are linked to via
UserEntitasBisnis. Superusers are unrestricted.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.accounts.models import UserEntitasBisnis
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.purchase.views import (
    accessible_eb_lv1_ids, _resolve_eb_selection, _get_eb_dropdown_options,
)

User = get_user_model()


class EbAccessScopingTest(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='T')
        self.eb_a = EntitasBisnis.objects.create(
            nama='A', standar_akuntansi='psak', tipe_entitas=self.tipe)
        self.eb_b = EntitasBisnis.objects.create(
            nama='B', standar_akuntansi='psak', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u@x.id', password='p')
        UserEntitasBisnis.objects.create(user=self.user, entitas_bisnis=self.eb_a)
        self.admin = User.objects.create_user(email='admin@x.id', password='p')
        self.admin.is_superuser = True
        self.admin.save()

    def test_scoped_to_linked_entity(self):
        self.assertEqual(accessible_eb_lv1_ids(self.user), {self.eb_a.pk})

    def test_superuser_unrestricted(self):
        self.assertIsNone(accessible_eb_lv1_ids(self.admin))

    def test_resolve_rejects_foreign_entity(self):
        # Linked entity resolves; a foreign one is denied server-side.
        self.assertIsNotNone(_resolve_eb_selection(f'lv1:{self.eb_a.pk}', self.user))
        self.assertIsNone(_resolve_eb_selection(f'lv1:{self.eb_b.pk}', self.user))
        # Superuser can resolve any entity.
        self.assertIsNotNone(_resolve_eb_selection(f'lv1:{self.eb_b.pk}', self.admin))

    def test_dropdown_excludes_foreign_entity(self):
        vals = {o['value'] for o in _get_eb_dropdown_options(self.user)}
        self.assertIn(f'lv1:{self.eb_a.pk}', vals)
        self.assertNotIn(f'lv1:{self.eb_b.pk}', vals)
