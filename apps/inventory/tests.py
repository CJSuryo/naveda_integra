"""Unit tests for the inventory app."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from .models import MutasiInventoryHeader, MutasiInventoryDetail, InventoryRecord

User = get_user_model()


from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase as DjangoTestCase

from apps.inventory.models import StockMovement, StockConsumption


class StockMovementModelTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_inflow_layer(self):
        mv = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('10'),
        )
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertIn('purchase_in', str(mv))

    def test_stock_consumption_links_out_and_in(self):
        inflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('4'),
        )
        outflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-02',
            movement_type='sale_out', qty=Decimal('-6'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('0'),
        )
        alloc = StockConsumption.objects.create(
            out_movement=outflow, in_movement=inflow,
            qty=Decimal('6'), unit_cost=Decimal('5'),
        )
        self.assertEqual(alloc.in_movement, inflow)
        self.assertEqual(alloc.out_movement, outflow)


class InventoryModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)

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


class InventoryRecordModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_auto_inventory_number(self):
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        self.assertTrue(rec.inventory_number.startswith('RM-'))
        self.assertEqual(rec.total_value, 50000)

    def test_sequential_numbering(self):
        r1 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        r2 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=5, unit_price=6000,
        )
        # Both should have same prefix, sequential suffix
        prefix = r1.inventory_number.rsplit('-', 1)[0]
        self.assertEqual(r2.inventory_number, f'{prefix}-002')

    def test_str(self):
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        self.assertEqual(str(rec), rec.inventory_number)


class InventoryViewTests(TestCase):
    def setUp(self):
        from apps.accounts.models import Role
        role = Role.objects.create(kode='admin', nama='Admin')
        self.user = User.objects.create_user(email='test@test.com', password='pass', role=role)
        self.client = Client()
        self.client.login(email='test@test.com', password='pass')

        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.record = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )

    def test_list_view(self):
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.record.inventory_number)

    def test_detail_view(self):
        resp = self.client.get(reverse('inventory:detail', args=[self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.record.inventory_number)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 302)
