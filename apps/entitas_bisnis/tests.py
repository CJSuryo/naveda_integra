"""Unit tests for the entitas_bisnis app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import TipeEntitas, EntitasBisnis, CabangEntitasBisnis

User = get_user_model()


class TipeEntitasModelTests(TestCase):
    def test_create_tipe_entitas(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.assertEqual(str(tipe), 'FnB')

    def test_unique_nama(self):
        TipeEntitas.objects.create(nama='Laundry')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TipeEntitas.objects.create(nama='Laundry')


class EntitasBisnisModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='Restaurant')

    def test_create_entitas_bisnis(self):
        eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.assertEqual(str(eb), 'PT Test')
        self.assertTrue(eb.status_aktif)
        self.assertEqual(eb.relasi, 'pelanggan')

    def test_unique_tax_id(self):
        EntitasBisnis.objects.create(nama='EB1', tipe_entitas=self.tipe, tax_id='123')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            EntitasBisnis.objects.create(nama='EB2', tipe_entitas=self.tipe, tax_id='123')

    def test_user_can_have_multiple_entitas(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        eb1 = EntitasBisnis.objects.create(nama='EB1', tipe_entitas=self.tipe)
        eb2 = EntitasBisnis.objects.create(nama='EB2', tipe_entitas=self.tipe)
        eb1.users.add(user)
        eb2.users.add(user)
        self.assertEqual(user.entitas_bisnis_owned.count(), 2)

    def test_tipe_entitas_protect(self):
        """Deleting TipeEntitas used by an EntitasBisnis must raise ProtectedError."""
        EntitasBisnis.objects.create(nama='EB', tipe_entitas=self.tipe)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.tipe.delete()


class CabangEntitasBisnisModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='Hotel')
        self.eb = EntitasBisnis.objects.create(nama='PT Hotel Mewah', tipe_entitas=self.tipe)

    def test_create_cabang(self):
        cab = CabangEntitasBisnis.objects.create(
            entitas_bisnis=self.eb, nama='Cabang Jakarta',
        )
        self.assertIn('Cabang Jakarta', str(cab))
        self.assertIn('PT Hotel Mewah', str(cab))
        self.assertTrue(cab.status_aktif)

    def test_cascade_delete(self):
        CabangEntitasBisnis.objects.create(entitas_bisnis=self.eb, nama='Cabang A')
        CabangEntitasBisnis.objects.create(entitas_bisnis=self.eb, nama='Cabang B')
        self.eb.delete()
        self.assertEqual(CabangEntitasBisnis.objects.count(), 0)


class TipeEntitasViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='admin@test.com', password='pass', name='Admin')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')

    def test_list(self):
        response = self.client.get(reverse('entitas_bisnis:tipe_entitas_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FnB')

    def test_create(self):
        data = {'nama': 'Laundry'}
        response = self.client.post(reverse('entitas_bisnis:tipe_entitas_create'), data)
        self.assertRedirects(response, reverse('entitas_bisnis:tipe_entitas_list'))
        self.assertTrue(TipeEntitas.objects.filter(nama='Laundry').exists())

    def test_update(self):
        data = {'nama': 'Updated'}
        response = self.client.post(reverse('entitas_bisnis:tipe_entitas_update', args=[self.tipe.pk]), data)
        self.assertRedirects(response, reverse('entitas_bisnis:tipe_entitas_list'))
        self.tipe.refresh_from_db()
        self.assertEqual(self.tipe.nama, 'Updated')

    def test_delete(self):
        response = self.client.post(reverse('entitas_bisnis:tipe_entitas_delete', args=[self.tipe.pk]))
        self.assertRedirects(response, reverse('entitas_bisnis:tipe_entitas_list'))
        self.assertFalse(TipeEntitas.objects.filter(pk=self.tipe.pk).exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('entitas_bisnis:tipe_entitas_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])


class EntitasBisnisViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='eb@test.com', password='pass', name='EB User')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='PT Contoh', tipe_entitas=self.tipe, email='pt@test.com')

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
        data = {'nama': 'PT Baru', 'tipe_entitas': self.tipe.pk, 'relasi': 'pemasok', 'status_aktif': True}
        response = self.client.post(reverse('entitas_bisnis:create'), data)
        self.assertRedirects(response, reverse('entitas_bisnis:list'))
        self.assertTrue(EntitasBisnis.objects.filter(nama='PT Baru').exists())

    def test_update_view(self):
        tipe2 = TipeEntitas.objects.create(nama='Hotel')
        data = {'nama': 'PT Updated', 'tipe_entitas': tipe2.pk, 'relasi': 'keduanya', 'status_aktif': True}
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


class CabangEntitasBisnisViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='cab@test.com', password='pass', name='Cab User')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='PT Parent', tipe_entitas=self.tipe)

    def test_create_cabang(self):
        data = {'nama': 'Cabang A', 'status_aktif': True}
        response = self.client.post(reverse('entitas_bisnis:cabang_create', args=[self.eb.pk]), data)
        self.assertRedirects(response, reverse('entitas_bisnis:detail', args=[self.eb.pk]))
        self.assertTrue(CabangEntitasBisnis.objects.filter(nama='Cabang A').exists())

    def test_update_cabang(self):
        cab = CabangEntitasBisnis.objects.create(entitas_bisnis=self.eb, nama='Old')
        data = {'nama': 'Updated', 'status_aktif': True}
        response = self.client.post(reverse('entitas_bisnis:cabang_update', args=[self.eb.pk, cab.pk]), data)
        self.assertRedirects(response, reverse('entitas_bisnis:detail', args=[self.eb.pk]))
        cab.refresh_from_db()
        self.assertEqual(cab.nama, 'Updated')

    def test_delete_cabang(self):
        cab = CabangEntitasBisnis.objects.create(entitas_bisnis=self.eb, nama='ToDelete')
        response = self.client.post(reverse('entitas_bisnis:cabang_delete', args=[self.eb.pk, cab.pk]))
        self.assertRedirects(response, reverse('entitas_bisnis:detail', args=[self.eb.pk]))
        self.assertFalse(CabangEntitasBisnis.objects.filter(pk=cab.pk).exists())

    def test_cabang_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('entitas_bisnis:cabang_create', args=[self.eb.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])
