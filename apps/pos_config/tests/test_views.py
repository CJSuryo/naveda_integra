from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig


class MerchantConfigViewTest(TestCase):
    def setUp(self):
        role = Role.objects.create(kode='admin', nama='Admin', deskripsi='')
        self.user = User.objects.create_user(email='admin@test.com', password='pass', name='Admin', role=role)
        role_kasir = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
        self.kasir = User.objects.create_user(email='kasir@test.com', password='pass', name='Kasir', role=role_kasir)
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
        self.client = Client()

    def test_config_view_requires_login(self):
        url = reverse('pos_config:merchant_config', kwargs={'pk': self.entitas.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    def test_config_view_forbidden_without_permission(self):
        self.client.login(email='kasir@test.com', password='pass')
        url = reverse('pos_config:merchant_config', kwargs={'pk': self.entitas.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_config_view_accessible_with_permission(self):
        self.client.login(email='admin@test.com', password='pass')
        url = reverse('pos_config:merchant_config', kwargs={'pk': self.entitas.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
