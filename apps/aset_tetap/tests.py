"""Unit tests for the aset_tetap app."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from .models import AsetTetapRecord

User = get_user_model()


class AsetTetapRecordModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Mesin Produksi', tipe_item='ATP')

    def test_auto_aset_number(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=50_000_000,
        )
        self.assertTrue(rec.aset_number.startswith('ATP-'))
        self.assertEqual(rec.total_value, 50_000_000)

    def test_sequential_numbering(self):
        r1 = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
        )
        r2 = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=20_000_000,
        )
        self.assertNotEqual(r1.aset_number, r2.aset_number)

    def test_nilai_buku_property(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
            akumulasi_penyusutan=2_000_000,
        )
        self.assertEqual(rec.nilai_buku, 8_000_000)

    def test_str(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=5_000_000,
        )
        self.assertEqual(str(rec), rec.aset_number)

    def test_cascade_entitas_protect(self):
        AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=5_000_000,
        )
        from django.db import IntegrityError
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.entitas.delete()


class AsetTetapViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='test@test.com', password='pass')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP')
        self.record = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
        )

    def test_list_view(self):
        res = self.client.get(reverse('aset_tetap:list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.record.aset_number)

    def test_detail_view(self):
        res = self.client.get(reverse('aset_tetap:detail', args=[self.record.pk]))
        self.assertEqual(res.status_code, 200)

    def test_create_get(self):
        res = self.client.get(reverse('aset_tetap:create'))
        self.assertEqual(res.status_code, 200)

    def test_create_post(self):
        res = self.client.post(reverse('aset_tetap:create'), {
            'item': self.item.pk,
            'entitas_bisnis': self.entitas.pk,
            'quantity': '1',
            'harga_perolehan': '5000000',
            'tanggal_perolehan': '2025-01-01',
            'akumulasi_penyusutan': '0',
            'kondisi': 'baik',
        })
        self.assertEqual(AsetTetapRecord.objects.count(), 2)

    def test_update_get(self):
        res = self.client.get(reverse('aset_tetap:update', args=[self.record.pk]))
        self.assertEqual(res.status_code, 200)

    def test_update_post(self):
        res = self.client.post(reverse('aset_tetap:update', args=[self.record.pk]), {
            'item': self.item.pk,
            'entitas_bisnis': self.entitas.pk,
            'quantity': '2',
            'harga_perolehan': '10000000',
            'tanggal_perolehan': '2025-01-01',
            'akumulasi_penyusutan': '1000000',
            'kondisi': 'baik',
        })
        self.record.refresh_from_db()
        from decimal import Decimal
        self.assertEqual(self.record.quantity, Decimal('2'))

    def test_delete_get(self):
        res = self.client.get(reverse('aset_tetap:delete', args=[self.record.pk]))
        self.assertEqual(res.status_code, 302)

    def test_delete_post(self):
        res = self.client.post(reverse('aset_tetap:delete', args=[self.record.pk]))
        self.assertEqual(AsetTetapRecord.objects.count(), 0)

    def test_login_required(self):
        self.client.logout()
        res = self.client.get(reverse('aset_tetap:list'))
        self.assertNotEqual(res.status_code, 200)
