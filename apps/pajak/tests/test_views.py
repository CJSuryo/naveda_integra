from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class PajakViewsSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='x')
        self.client.force_login(self.user)

    def test_transaksi_list_returns_200(self):
        url = reverse('pajak:transaksi_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_masa_list_returns_200(self):
        url = reverse('pajak:masa_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_tarif_list_returns_200(self):
        url = reverse('pajak:tarif_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_tarif_tambah_returns_200(self):
        url = reverse('pajak:tarif_tambah')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class AnonymousAccessTest(TestCase):
    def test_transaksi_list_requires_login(self):
        response = self.client.get(reverse('pajak:transaksi_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_masa_list_requires_login(self):
        response = self.client.get(reverse('pajak:masa_list'))
        self.assertEqual(response.status_code, 302)

    def test_tarif_list_requires_login(self):
        response = self.client.get(reverse('pajak:tarif_list'))
        self.assertEqual(response.status_code, 302)

    def test_tarif_tambah_requires_login(self):
        response = self.client.get(reverse('pajak:tarif_tambah'))
        self.assertEqual(response.status_code, 302)
