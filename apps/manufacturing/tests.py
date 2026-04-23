"""Manufacturing tests."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase, FIFOBatch

from .models import BillOfMaterials, BOMLine, ProductionOrder


def _make_user():
    role, _ = Role.objects.get_or_create(kode='admin', defaults={'nama': 'Admin'})
    return User.objects.create_user(
        email='test@example.com',
        password='testpass123',
        role=role,
    )


def _make_entitas():
    tipe, _ = TipeEntitas.objects.get_or_create(nama='PT')
    return EntitasBisnis.objects.create(
        nama='Test Bisnis', tipe_entitas=tipe, status_aktif=True,
    )


def _make_akun(kode, nama):
    return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id='beban')


def _make_item(item_id, nama, tipe, akun=None):
    return ItemMasterPurchase.objects.create(
        item_id=item_id, nama=nama, tipe_item=tipe, coa_account=akun,
    )


class BillOfMaterialsModelTests(TestCase):
    def setUp(self):
        self.eb = _make_entitas()
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG')
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM')

    def test_str(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        self.assertEqual(str(bom), 'BOM-FG-0001')

    def test_bom_id_auto_generated(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        self.assertEqual(bom.bom_id, 'BOM-FG-0001')

    def test_one_bom_per_fg(self):
        BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        from django.db import IntegrityError
        with self.assertRaises(Exception):
            BillOfMaterials.objects.create(
                finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-02',
            )

    def test_bom_line_str(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        line = BOMLine.objects.create(bom=bom, raw_material=self.rm, qty_required=Decimal('2.5'))
        self.assertIn('RM-0001', str(line))
        self.assertIn('BOM-FG-0001', str(line))


class ProductionOrderModelTests(TestCase):
    def setUp(self):
        self.eb = _make_entitas()
        self.akun_wip = _make_akun('5001', 'WIP')
        self.akun_rm = _make_akun('1401', 'Persediaan RM')
        self.akun_fg = _make_akun('1402', 'Persediaan FG')
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM', self.akun_rm)
        self.bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.rm, qty_required=Decimal('2'))

    def test_production_id_auto_generated(self):
        order = ProductionOrder.objects.create(
            tanggal='2025-01-10',
            entitas_bisnis=self.eb,
            bom=self.bom,
            qty_produced=Decimal('10'),
            coa_produksi=self.akun_wip,
        )
        self.assertTrue(order.production_id.startswith('PROD-'))

    def test_str(self):
        order = ProductionOrder.objects.create(
            tanggal='2025-01-10',
            entitas_bisnis=self.eb,
            bom=self.bom,
            qty_produced=Decimal('10'),
            coa_produksi=self.akun_wip,
        )
        self.assertEqual(str(order), order.production_id)


class BOMViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.login(email='test@example.com', password='testpass123')
        self.eb = _make_entitas()
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG')
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM')

    def test_bom_list(self):
        response = self.client.get(reverse('manufacturing:bom_list'))
        self.assertEqual(response.status_code, 200)

    def test_bom_create_get(self):
        response = self.client.get(reverse('manufacturing:bom_create'))
        self.assertEqual(response.status_code, 200)

    def test_bom_create_post_valid(self):
        response = self.client.post(reverse('manufacturing:bom_create'), {
            'finished_good': self.fg.pk,
            'entitas_bisnis': self.eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': self.rm.pk,
            'qty_0': '2.0000',
        })
        self.assertEqual(BillOfMaterials.objects.count(), 1)
        bom = BillOfMaterials.objects.first()
        self.assertRedirects(response, reverse('manufacturing:bom_detail', args=[bom.pk]))

    def test_bom_detail(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        BOMLine.objects.create(bom=bom, raw_material=self.rm, qty_required=Decimal('2'))
        response = self.client.get(reverse('manufacturing:bom_detail', args=[bom.pk]))
        self.assertEqual(response.status_code, 200)

    def test_bom_delete(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        response = self.client.post(reverse('manufacturing:bom_delete', args=[bom.pk]))
        self.assertRedirects(response, reverse('manufacturing:bom_list'))
        self.assertEqual(BillOfMaterials.objects.count(), 0)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse('manufacturing:bom_list'))
        self.assertNotEqual(response.status_code, 200)


class ProductionOrderViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.login(email='test@example.com', password='testpass123')
        self.eb = _make_entitas()
        self.akun_wip = _make_akun('5001', 'WIP')
        self.akun_rm = _make_akun('1401', 'Persediaan RM')
        self.akun_fg = _make_akun('1402', 'Persediaan FG')
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM', self.akun_rm)
        self.bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.rm, qty_required=Decimal('2'))
        # Seed FIFO stock
        FIFOBatch.objects.create(
            item=self.rm,
            tanggal='2025-01-01',
            quantity_in=Decimal('100'),
            unit_price=Decimal('5000'),
            remaining_qty=Decimal('100'),
        )

    def test_production_list(self):
        response = self.client.get(reverse('manufacturing:production_list'))
        self.assertEqual(response.status_code, 200)

    def test_production_create_get(self):
        response = self.client.get(reverse('manufacturing:production_create'))
        self.assertEqual(response.status_code, 200)

    def test_production_create_post_valid(self):
        response = self.client.post(reverse('manufacturing:production_create'), {
            'tanggal': '2025-01-10',
            'entitas_bisnis': self.eb.pk,
            'bom': self.bom.pk,
            'qty_produced': '5',
            'overhead_cost': '0',
            'coa_produksi': self.akun_wip.pk,
        })
        self.assertEqual(ProductionOrder.objects.count(), 1)
        order = ProductionOrder.objects.first()
        self.assertTrue(order.is_processed)
        self.assertEqual(order.status, 'completed')

    def test_api_bom_preview(self):
        response = self.client.get(reverse('manufacturing:api_bom_preview'), {
            'bom_id': self.bom.pk,
            'qty_produced': '5',
            'overhead_cost': '0',
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('lines', data)
        self.assertIn('unit_cost', data)
