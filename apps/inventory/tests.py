"""Unit tests for the inventory app."""
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis
from .models import MutasiInventoryHeader, MutasiInventoryDetail


class InventoryModelTests(TestCase):
    def setUp(self):
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas='pelanggan')

    def test_mutasi_header_str(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        self.assertIn(str(h.id), str(h))

    def test_mutasi_detail_str(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        d = MutasiInventoryDetail.objects.create(mutasi_inventory_header=h)
        self.assertIn(str(h.id), str(d))

    def test_cascade_delete(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        MutasiInventoryDetail.objects.create(mutasi_inventory_header=h)
        h.delete()
        self.assertEqual(MutasiInventoryDetail.objects.count(), 0)
