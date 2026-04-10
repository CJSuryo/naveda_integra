"""Unit tests for the entitas_bisnis app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import EntitasBisnis

User = get_user_model()


class EntitasBisnisModelTests(TestCase):
    def test_create_entitas_bisnis(self):
        eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas='pelanggan')
        self.assertEqual(str(eb), 'PT Test')
        self.assertTrue(eb.status_aktif)

    def test_unique_tax_id(self):
        EntitasBisnis.objects.create(nama='EB1', tipe_entitas='pelanggan', tax_id='123')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            EntitasBisnis.objects.create(nama='EB2', tipe_entitas='pemasok', tax_id='123')

    def test_user_can_have_multiple_entitas(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        eb1 = EntitasBisnis.objects.create(nama='EB1', tipe_entitas='pelanggan')
        eb2 = EntitasBisnis.objects.create(nama='EB2', tipe_entitas='pemasok')
        eb1.users.add(user)
        eb2.users.add(user)
        self.assertEqual(user.entitas_bisnis_set.count(), 2)


class EntitasBisnisViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='eb@test.com', password='pass', name='EB User')
        self.client.force_login(self.user)
        self.eb = EntitasBisnis.objects.create(nama='PT Contoh', tipe_entitas='pelanggan', email='pt@test.com')

    def test_list_view(self):
        response = self.client.get(reverse('entitas_bisnis:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PT Contoh')

    def test_detail_view(self):
        response = self.client.get(reverse('entitas_bisnis:detail', args=[self.eb.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PT Contoh')

    def test_create_view_get(self):
        response = self.client.get(reverse('entitas_bisnis:create'))
        self.assertEqual(response.status_code, 200)

    def test_create_view_post(self):
        data = {'nama': 'PT Baru', 'tipe_entitas': 'pemasok', 'status_aktif': True}
        response = self.client.post(reverse('entitas_bisnis:create'), data)
        self.assertRedirects(response, reverse('entitas_bisnis:list'))
        self.assertTrue(EntitasBisnis.objects.filter(nama='PT Baru').exists())

    def test_update_view(self):
        data = {'nama': 'PT Updated', 'tipe_entitas': 'keduanya', 'status_aktif': True}
        response = self.client.post(reverse('entitas_bisnis:update', args=[self.eb.pk]), data)
        self.assertRedirects(response, reverse('entitas_bisnis:list'))
        self.eb.refresh_from_db()
        self.assertEqual(self.eb.nama, 'PT Updated')

    def test_delete_view_get(self):
        response = self.client.get(reverse('entitas_bisnis:delete', args=[self.eb.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_view_post(self):
        response = self.client.post(reverse('entitas_bisnis:delete', args=[self.eb.pk]))
        self.assertRedirects(response, reverse('entitas_bisnis:list'))
        self.assertFalse(EntitasBisnis.objects.filter(pk=self.eb.pk).exists())

    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('entitas_bisnis:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])
