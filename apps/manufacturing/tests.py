"""Manufacturing tests."""
import re
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase, FIFOBatch

from .models import (
    BillOfMaterials, BOMLine, OverheadApplied, OverheadCategory, OverheadRate,
    PeriodClosing, ProductionOrder,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

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


def _make_akun(kode, nama, kategori='beban'):
    return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori)


def _make_item(item_id, nama, tipe, akun=None):
    return ItemMasterPurchase.objects.create(
        item_id=item_id, nama=nama, tipe_item=tipe, coa_account=akun,
    )


def _make_bom_with_line(eb, fg, rm, qty_per_unit=Decimal('2')):
    bom = BillOfMaterials.objects.create(
        finished_good=fg, entitas_bisnis=eb, tanggal_dibuat='2025-01-01',
    )
    BOMLine.objects.create(bom=bom, raw_material=rm, qty_required=qty_per_unit)
    return bom


class ProductionOrderEBLevelTests(TestCase):
    def test_production_order_has_lv2_lv3(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.manufacturing.models import ProductionOrder
        tipe = TipeEntitas.objects.create(nama='PT')
        eb = EntitasBisnis.objects.create(nama='PT X', tipe_entitas=tipe)
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Divisi')
        lv3 = EntitasBisnisLv3.objects.create(parent_lv2=lv2, nama='Outlet')
        # Field wajib lain di-skip dgn hanya cek atribut model, bukan create penuh:
        self.assertTrue(hasattr(ProductionOrder, 'entitas_bisnis_lv2'))
        self.assertTrue(hasattr(ProductionOrder, 'entitas_bisnis_lv3'))
        field2 = ProductionOrder._meta.get_field('entitas_bisnis_lv2')
        field3 = ProductionOrder._meta.get_field('entitas_bisnis_lv3')
        self.assertTrue(field2.null)
        self.assertTrue(field3.null)


def _seed_fifo(rm, batches: list[tuple]):
    """batches = [(tanggal, qty, unit_price), ...]. Returns the created FIFOBatch list."""
    created = []
    for tanggal, qty, price in batches:
        created.append(FIFOBatch.objects.create(
            item=rm, tanggal=tanggal,
            quantity_in=Decimal(str(qty)), unit_price=Decimal(str(price)),
            remaining_qty=Decimal(str(qty)),
        ))
    return created


# ---------------------------------------------------------------------------
# BOM model tests
# ---------------------------------------------------------------------------

class BillOfMaterialsModelTests(TestCase):
    def setUp(self):
        self.eb = _make_entitas()
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG')
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM')

    def test_str(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        self.assertEqual(str(bom), f'{self.fg.nama} ({bom.bom_id})')

    def test_bom_id_auto_generated(self):
        bom = BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
        self.assertEqual(bom.bom_id, 'BOM-FG-0001')

    def test_one_bom_per_fg(self):
        BillOfMaterials.objects.create(
            finished_good=self.fg, entitas_bisnis=self.eb, tanggal_dibuat='2025-01-01',
        )
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


# ---------------------------------------------------------------------------
# Production Order model tests
# ---------------------------------------------------------------------------

class ProductionOrderModelTests(TestCase):
    def setUp(self):
        self.eb = _make_entitas()
        self.akun_wip = _make_akun('5001', 'WIP')
        self.akun_rm = _make_akun('1401', 'Persediaan RM')
        self.akun_fg = _make_akun('1402', 'Persediaan FG')
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM', self.akun_rm)
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm)

    def test_production_id_auto_generated(self):
        order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=self.eb,
            bom=self.bom, qty_produced=Decimal('10'), coa_produksi=self.akun_wip,
        )
        self.assertTrue(order.production_id.startswith('PROD-'))

    def test_str(self):
        order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=self.eb,
            bom=self.bom, qty_produced=Decimal('10'), coa_produksi=self.akun_wip,
        )
        self.assertEqual(str(order), order.production_id)


# ---------------------------------------------------------------------------
# Overhead Category model tests
# ---------------------------------------------------------------------------

class OverheadCategoryModelTests(TestCase):
    def setUp(self):
        self.akun_beban = _make_akun('5101', 'Listrik Mesin')
        self.akun_applied = _make_akun('2101', 'Overhead Applied', 'kewajiban')

    def test_str_production(self):
        cat = OverheadCategory.objects.create(
            name='Listrik Mesin', overhead_type='PRODUCTION',
            coa_expense=self.akun_beban, coa_overhead_applied=self.akun_applied,
            cost_driver='PER_UNIT',
        )
        self.assertIn('[PROD]', str(cat))
        self.assertIn('Listrik Mesin', str(cat))

    def test_str_period(self):
        cat = OverheadCategory.objects.create(
            name='Listrik Kantor', overhead_type='PERIOD',
            coa_expense=self.akun_beban,
        )
        self.assertIn('[PERIOD]', str(cat))
        self.assertIn('Listrik Kantor', str(cat))

    def test_production_requires_cost_driver_in_form(self):
        from .forms import OverheadCategoryForm
        form = OverheadCategoryForm(data={
            'name': 'Test',
            'overhead_type': 'PRODUCTION',
            'coa_expense': self.akun_beban.pk,
            'coa_overhead_applied': '',
            'cost_driver': '',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('cost_driver', form.errors)
        self.assertIn('coa_overhead_applied', form.errors)

    def test_period_disallows_cost_driver_in_form(self):
        from .forms import OverheadCategoryForm
        form = OverheadCategoryForm(data={
            'name': 'Test Period',
            'overhead_type': 'PERIOD',
            'coa_expense': self.akun_beban.pk,
            'coa_overhead_applied': '',
            'cost_driver': 'PER_UNIT',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('cost_driver', form.errors)


# ---------------------------------------------------------------------------
# Overhead Rate model tests
# ---------------------------------------------------------------------------

class OverheadRateModelTests(TestCase):
    def setUp(self):
        self.akun_beban = _make_akun('5101', 'Listrik Mesin')
        self.akun_applied = _make_akun('2101', 'Overhead Applied', 'kewajiban')

    def _make_cat(self, driver):
        return OverheadCategory.objects.create(
            name='Test Cat', overhead_type='PRODUCTION',
            coa_expense=self.akun_beban, coa_overhead_applied=self.akun_applied,
            cost_driver=driver,
        )

    def test_auto_rate_per_unit(self):
        """1,000,000 / 100 units = 10,000 per unit."""
        cat = self._make_cat('PER_UNIT')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'), estimasi_volume=Decimal('100'),
        )
        self.assertEqual(rate.rate_per_driver, Decimal('10000.000000'))

    def test_auto_rate_per_jam_mesin(self):
        """2,000,000 / 200 jam = 10,000 per jam."""
        cat = self._make_cat('PER_JAM_MESIN')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('2000000'), estimasi_volume=Decimal('200'),
        )
        self.assertEqual(rate.rate_per_driver, Decimal('10000.000000'))

    def test_auto_rate_per_jam_tk(self):
        """3,000,000 / 150 jam = 20,000 per jam."""
        cat = self._make_cat('PER_JAM_TK')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('3000000'), estimasi_volume=Decimal('150'),
        )
        self.assertEqual(rate.rate_per_driver, Decimal('20000.000000'))

    def test_persen_rm_cost_not_auto_calc(self):
        """PERSEN_RM_COST: rate_per_driver set directly by user (0.10 = 10%)."""
        cat = self._make_cat('PERSEN_RM_COST')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'),
            rate_per_driver=Decimal('0.10'),  # user-set directly
        )
        self.assertEqual(rate.rate_per_driver, Decimal('0.100000'))

    def test_rate_zero_when_no_volume(self):
        """No estimasi_volume â†’ rate = 0."""
        cat = self._make_cat('PER_UNIT')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'),
        )
        self.assertEqual(rate.rate_per_driver, Decimal('0'))

    def test_unique_per_category_per_period(self):
        cat = self._make_cat('PER_UNIT')
        OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'), estimasi_volume=Decimal('100'),
        )
        with self.assertRaises(Exception):
            OverheadRate.objects.create(
                overhead_category=cat, periode_bulan='2025-01',
                estimasi_total=Decimal('2000000'), estimasi_volume=Decimal('200'),
            )

    def test_str(self):
        cat = self._make_cat('PER_UNIT')
        rate = OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'), estimasi_volume=Decimal('100'),
        )
        self.assertIn('2025-01', str(rate))
        self.assertIn('Test Cat', str(rate))


# ---------------------------------------------------------------------------
# Overhead Applied model tests
# ---------------------------------------------------------------------------

class OverheadAppliedModelTests(TestCase):
    def setUp(self):
        eb = _make_entitas()
        akun_beban = _make_akun('5101', 'Listrik Mesin')
        akun_applied = _make_akun('2101', 'Overhead Applied', 'kewajiban')
        akun_wip = _make_akun('1301', 'WIP')
        akun_fg = _make_akun('1401', 'FG')
        akun_rm = _make_akun('1201', 'RM')
        fg = _make_item('FG-0001', 'Kopi Sachet', 'FG', akun_fg)
        rm = _make_item('RM-0001', 'Biji Kopi', 'RM', akun_rm)
        bom = _make_bom_with_line(eb, fg, rm)
        self.order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=eb,
            bom=bom, qty_produced=Decimal('10'), coa_produksi=akun_wip,
        )
        self.cat = OverheadCategory.objects.create(
            name='Listrik Mesin', overhead_type='PRODUCTION',
            coa_expense=akun_beban, coa_overhead_applied=akun_applied,
            cost_driver='PER_UNIT',
        )

    def test_amount_applied_auto_calc(self):
        """amount_applied = driver_value Ã— rate_per_driver."""
        applied = OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.cat,
            periode_bulan='2025-01',
            driver_value=Decimal('10'), rate_per_driver=Decimal('10000'),
        )
        self.assertEqual(applied.amount_applied, Decimal('100000.0000'))

    def test_amount_applied_persen_rm_cost(self):
        """PERSEN_RM_COST: rate=0.10, driver=RM_cost 1,530,000 â†’ applied=153,000."""
        applied = OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.cat,
            periode_bulan='2025-01',
            driver_value=Decimal('1530000'), rate_per_driver=Decimal('0.10'),
        )
        self.assertEqual(applied.amount_applied, Decimal('153000.0000'))

    def test_unique_per_order_per_category(self):
        OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.cat,
            periode_bulan='2025-01',
            driver_value=Decimal('10'), rate_per_driver=Decimal('10000'),
        )
        with self.assertRaises(Exception):
            OverheadApplied.objects.create(
                production_order=self.order, overhead_category=self.cat,
                periode_bulan='2025-01',
                driver_value=Decimal('5'), rate_per_driver=Decimal('10000'),
            )

    def test_str(self):
        applied = OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.cat,
            periode_bulan='2025-01',
            driver_value=Decimal('10'), rate_per_driver=Decimal('10000'),
        )
        self.assertIn(self.order.production_id, str(applied))
        self.assertIn('Listrik Mesin', str(applied))


# ---------------------------------------------------------------------------
# FIFO simulation tests
# ---------------------------------------------------------------------------

class FIFOSimulationTests(TestCase):
    """Tests for _simulate_fifo_cost â€” core of accurate FIFO pricing."""

    def setUp(self):
        self.rm = _make_item('RM-001', 'Biji Kopi', 'RM')
        # Older batch: 15 units @ Rp 20,000 (first in)
        _seed_fifo(self.rm, [
            ('2025-01-01', 15, 20000),
            ('2025-01-15', 5, 18000),   # newer: 5 units @ Rp 18,000
        ])

    def test_pure_first_batch(self):
        """10 units entirely from first batch â†’ 10 Ã— 20,000 = 200,000."""
        from .services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('10'))
        self.assertEqual(filled, Decimal('10'))
        self.assertEqual(cost, Decimal('200000'))

    def test_spans_two_batches(self):
        """17 units: 15 Ã— 20,000 + 2 Ã— 18,000 = 336,000 (not 17 Ã— weighted_avg 19,500)."""
        from .services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('17'))
        self.assertEqual(filled, Decimal('17'))
        self.assertEqual(cost, Decimal('336000'))

    def test_insufficient_stock(self):
        """Request 25 but only 20 available: 15Ã—20k + 5Ã—18k = 390,000, filled=20."""
        from .services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('25'))
        self.assertEqual(filled, Decimal('20'))
        self.assertEqual(cost, Decimal('390000'))

    def test_zero_stock(self):
        from .services import _simulate_fifo_cost
        rm2 = _make_item('RM-002', 'Item Kosong', 'RM')
        cost, filled = _simulate_fifo_cost(rm2.pk, Decimal('5'))
        self.assertEqual(filled, Decimal('0'))
        self.assertEqual(cost, Decimal('0'))

    def test_bom_preview_uses_fifo_order(self):
        """get_bom_preview should show 20,000/unit when taking 10 from first batch."""
        eb = _make_entitas()
        fg = _make_item('FG-X', 'Produk', 'FG')
        bom = _make_bom_with_line(eb, fg, self.rm, qty_per_unit=Decimal('1'))

        from .services import get_bom_preview
        rows = get_bom_preview(bom, Decimal('10'))
        row = rows[0]
        # 10 units all from first batch @ 20,000
        self.assertEqual(row['fifo_unit_cost'], Decimal('20000.0000'))
        self.assertEqual(row['total_rm_cost'], Decimal('200000.0000'))

    def test_bom_preview_blended_cost_across_batches(self):
        """17 units: blended unit cost â‰ˆ 336,000/17, total = 336,000."""
        eb = _make_entitas()
        fg = _make_item('FG-Y', 'Produk Y', 'FG')
        bom = _make_bom_with_line(eb, fg, self.rm, qty_per_unit=Decimal('1'))

        from .services import get_bom_preview
        rows = get_bom_preview(bom, Decimal('17'))
        row = rows[0]
        # Due to rounding when computing fifo_unit_cost then multiplying back,
        # the result is within 1 unit of the exact value.
        self.assertAlmostEqual(float(row['total_rm_cost']), 336000.0, delta=1.0)


# ---------------------------------------------------------------------------
# Production service tests
# ---------------------------------------------------------------------------

class ProductionServiceTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.eb = _make_entitas()
        self.akun_wip = _make_akun('1301', 'WIP')
        self.akun_rm = _make_akun('1201', 'Persediaan RM')
        self.akun_fg = _make_akun('1401', 'Persediaan FG')
        self.akun_beban = _make_akun('5101', 'Listrik Mesin')
        self.akun_applied = _make_akun('2101', 'Overhead Applied', 'kewajiban')
        self.fg = _make_item('FG-0001', 'Kopi Sachet', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM', self.akun_rm)
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm)
        rm_batch = _seed_fifo(self.rm, [('2025-01-01', 100, 5000)])[0]
        # Also seed the authoritative stock ledger (apps.inventory.ledger),
        # mirrored to the legacy FIFOBatch — process_production consumes RM
        # via StockMovement layers, not FIFOBatch directly, since Task 9.
        # Purchase always dual-writes with this mirror link (see Task 3), so
        # tests must too, to keep ProductionRMConsumption/journal tracing intact.
        from apps.inventory.ledger import record_inflow
        record_inflow(self.rm, self.eb, None, None, Decimal('100'),
                      Decimal('5000'), '2025-01-01', 'purchase_in',
                      legacy_fifo_batch=rm_batch)

        self.oh_cat = OverheadCategory.objects.create(
            name='Listrik Mesin', overhead_type='PRODUCTION',
            coa_expense=self.akun_beban, coa_overhead_applied=self.akun_applied,
            cost_driver='PER_UNIT',
        )
        OverheadRate.objects.create(
            overhead_category=self.oh_cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'), estimasi_volume=Decimal('100'),
        )
        self.order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=self.eb,
            bom=self.bom, qty_produced=Decimal('10'), coa_produksi=self.akun_wip,
        )

    def test_process_production_computes_rm_cost(self):
        """10 FG Ã— 2 RM per FG Ã— 5,000/unit = 100,000 RM cost."""
        from .services import process_production
        process_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.rm_cost, Decimal('100000'))

    def test_process_production_without_overhead(self):
        """Without overhead, total_cost == rm_cost, overhead_cost == 0."""
        from .services import process_production
        process_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.overhead_cost, Decimal('0'))
        self.assertEqual(self.order.total_cost, Decimal('100000'))

    def test_process_production_with_overhead_per_unit(self):
        """Rate = 10,000/unit; 10 units â†’ overhead = 100,000; total = 200,000."""
        from .services import create_overhead_applied, process_production
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.overhead_cost, Decimal('100000'))
        self.assertEqual(self.order.total_cost, Decimal('200000'))
        self.assertEqual(self.order.unit_cost, Decimal('20000.0000'))

    def test_journal_credits_overhead_applied_not_expense(self):
        """Overhead WIP absorption must CR Overhead Applied (2.x.x), NEVER CR expense (5.x.x)."""
        from .services import create_overhead_applied, process_production
        from apps.jurnal.models import JurnalDetail
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        # Must have a credit to the Overhead Applied account
        oh_credits = JurnalDetail.objects.filter(akun=self.akun_applied, kredit__gt=0)
        self.assertTrue(oh_credits.exists(), 'Missing CR to Overhead Applied account')
        # Must NEVER credit an expense account for overhead absorption
        expense_credits = JurnalDetail.objects.filter(akun=self.akun_beban, kredit__gt=0)
        self.assertFalse(
            expense_credits.exists(),
            'Expense account (5.x.x) must not be credited for overhead WIP absorption',
        )

    def test_journal_debits_wip_for_overhead(self):
        """DR WIP (coa_produksi) for each overhead applied."""
        from .services import create_overhead_applied, process_production
        from apps.jurnal.models import JurnalDetail
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        wip_debits = JurnalDetail.objects.filter(akun=self.akun_wip, debit__gt=0)
        # At minimum: RM line + overhead line both debit WIP
        self.assertGreaterEqual(wip_debits.count(), 2)

    def test_period_overhead_excluded_from_journal(self):
        """PERIOD overhead must not appear in production journals at all."""
        period_cat = OverheadCategory.objects.create(
            name='Listrik Kantor', overhead_type='PERIOD',
            coa_expense=self.akun_beban,
        )
        from .services import process_production
        from apps.jurnal.models import JurnalDetail
        # No overhead_applied created for this period type
        process_production(self.order)
        # Expense account should only appear as RM credit, no overhead entries
        # (the period cat's expense account = same akun_beban but no journal entry for it in production)
        expense_credits = JurnalDetail.objects.filter(akun=self.akun_beban, kredit__gt=0)
        self.assertFalse(expense_credits.exists())

    def test_journal_is_balanced(self):
        """Total debits must equal total credits for every journal."""
        from .services import create_overhead_applied, process_production
        from apps.jurnal.models import JurnalDetail, JurnalHeader
        from django.db.models import Sum
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        header = JurnalHeader.objects.filter(
            uraian_transaksi__icontains=self.order.production_id,
        ).first()
        self.assertIsNotNone(header)
        totals = JurnalDetail.objects.filter(jurnal_header=header).aggregate(
            total_debit=Sum('debit'), total_kredit=Sum('kredit'),
        )
        self.assertEqual(totals['total_debit'], totals['total_kredit'])

    def test_reverse_production_deletes_overhead_applied(self):
        from .services import create_overhead_applied, process_production, reverse_production
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.overhead_applied.count(), 1)
        reverse_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.overhead_applied.count(), 0)
        self.assertEqual(self.order.overhead_cost, Decimal('0'))

    def test_reverse_production_blocked_after_period_close(self):
        from .services import create_overhead_applied, process_production, reverse_production
        akun_cogs = _make_akun('5201', 'COGS')
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order)
        PeriodClosing.objects.create(
            periode_bulan='2025-01',
            closed_by=self.user,
            coa_cogs=akun_cogs,
        )
        with self.assertRaises(ValueError):
            reverse_production(self.order)

    def test_period_end_closing_creates_period_closing_record(self):
        from .services import period_end_closing

        akun_cogs = _make_akun('5201', 'COGS')
        existing_rate = OverheadRate.objects.get(overhead_category=self.oh_cat, periode_bulan='2025-01')
        existing_rate.aktual_total = Decimal('90000')
        existing_rate.save()
        OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.oh_cat,
            periode_bulan='2025-01', driver_value=Decimal('10'), rate_per_driver=Decimal('10000'),
        )

        results = period_end_closing('2025-01', akun_cogs.pk, closed_by=self.user)
        self.assertTrue(PeriodClosing.objects.filter(periode_bulan='2025-01').exists())
        closing = PeriodClosing.objects.get(periode_bulan='2025-01')
        self.assertEqual(closing.closed_by, self.user)
        self.assertEqual(closing.coa_cogs, akun_cogs)
        self.assertEqual(len(results), 1)

    def test_period_end_closing_blocks_duplicate_closing(self):
        from .services import period_end_closing

        akun_cogs = _make_akun('5201', 'COGS')
        PeriodClosing.objects.create(
            periode_bulan='2025-01',
            closed_by=self.user,
            coa_cogs=akun_cogs,
        )

        results = period_end_closing('2025-01', akun_cogs.pk, closed_by=self.user)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].get('skipped'), 'Closing should skip duplicate journal creation.')

    def test_next_production_journal_number_handles_invalid_suffix(self):
        from apps.jurnal.models import JurnalHeader
        from .services import _next_production_journal_number

        JurnalHeader.objects.create(
            nomor_transaksi='TRX-PROD-0001',
            uraian_transaksi='Test 1',
        )
        JurnalHeader.objects.create(
            nomor_transaksi='TRX-PROD-0005',
            uraian_transaksi='Test 5',
        )
        JurnalHeader.objects.create(
            nomor_transaksi='TRX-PROD-XYZ',
            uraian_transaksi='Test invalid',
        )
        self.assertEqual(_next_production_journal_number(), 'TRX-PROD-0006')

    def test_cannot_process_twice(self):
        from .services import process_production
        process_production(self.order)
        with self.assertRaises(ValueError):
            process_production(self.order)

    def test_create_overhead_applied_snapshots_rate(self):
        """rate_per_driver on OverheadApplied must be a snapshot of the rate at creation time."""
        from .services import create_overhead_applied
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        applied = self.order.overhead_applied.get(overhead_category=self.oh_cat)
        # Rate snapshot: 1,000,000 / 100 = 10,000
        self.assertEqual(applied.rate_per_driver, Decimal('10000.000000'))
        self.assertEqual(applied.amount_applied, Decimal('100000.0000'))

    def test_approve_production_completes_wip_and_creates_fg_journal(self):
        from .services import create_overhead_applied, process_production, approve_production
        from apps.jurnal.models import JurnalDetail

        self.order.status = 'in_progress'
        self.order.save()
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order, as_wip=True)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_processed)
        self.assertEqual(self.order.status, 'in_progress')
        self.assertIsNone(self.order.fg_inventory_record)

        approve_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'completed')
        self.assertIsNotNone(self.order.fg_inventory_record)

        journal = JurnalDetail.objects.filter(jurnal_header__uraian_transaksi__icontains=self.order.production_id)
        self.assertTrue(journal.exists())
        self.assertTrue(JurnalDetail.objects.filter(akun=self.akun_fg, debit=self.order.total_cost).exists())
        self.assertTrue(JurnalDetail.objects.filter(akun=self.akun_wip, kredit=self.order.total_cost).exists())

    def test_approve_production_wires_fg_to_ledger(self):
        """approve_production's FG must be visible via the authoritative stock ledger
        (get_available_stock), not just the legacy FIFOBatch/InventoryRecord mirrors —
        sales consumes exclusively via the ledger."""
        from .services import create_overhead_applied, process_production, approve_production
        from apps.inventory.ledger import get_available_stock

        self.order.status = 'in_progress'
        self.order.save()
        create_overhead_applied(self.order, {self.oh_cat.pk: Decimal('10')}, '2025-01')
        process_production(self.order, as_wip=True)
        approve_production(self.order)

        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('10'))

    def test_reverse_production_removes_fg_ledger_layer(self):
        """reverse_production must remove the FG production_in ledger layer, not
        just the legacy FIFOBatch/InventoryRecord — otherwise the ledger keeps
        reporting phantom FG stock after reversal."""
        from .services import process_production, reverse_production
        from apps.inventory.ledger import get_available_stock

        process_production(self.order)
        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('10'))

        reverse_production(self.order)
        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('0'))

    def test_reverse_production_blocked_when_fg_partially_consumed(self):
        """If the FG layer produced by this order has already been (partially)
        consumed — e.g. sold via the ledger — reverse_production must not
        silently destroy the consumption/allocation trail. It must fail loud
        (uncaught ProtectedError), matching the convention already used by
        apps.purchase.services.reverse_stock_movements / reverse_inflow_movements."""
        from django.db.models.deletion import ProtectedError
        from .services import process_production, reverse_production
        from apps.inventory.ledger import consume_stock

        process_production(self.order)
        consume_stock(self.fg, self.eb, None, None, Decimal('3'), '2025-01-15', 'sale_out')

        with self.assertRaises(ProtectedError):
            reverse_production(self.order)

    def test_period_end_closing_creates_variance_journals(self):
        from .services import period_end_closing
        from apps.jurnal.models import JurnalDetail, JurnalHeader

        akun_cogs = _make_akun('5201', 'COGS')
        other_cat = OverheadCategory.objects.create(
            name='Listrik Pabrik', overhead_type='PRODUCTION',
            coa_expense=self.akun_beban, coa_overhead_applied=self.akun_applied,
            cost_driver='PER_UNIT',
        )
        existing_rate = OverheadRate.objects.get(overhead_category=self.oh_cat, periode_bulan='2025-01')
        existing_rate.aktual_total = Decimal('90000')
        existing_rate.save()
        OverheadRate.objects.create(
            overhead_category=other_cat, periode_bulan='2025-01',
            estimasi_total=Decimal('2000000'), estimasi_volume=Decimal('200'), aktual_total=Decimal('220000'),
        )
        OverheadApplied.objects.create(
            production_order=self.order, overhead_category=self.oh_cat,
            periode_bulan='2025-01', driver_value=Decimal('10'), rate_per_driver=Decimal('10000'),
        )
        OverheadApplied.objects.create(
            production_order=self.order, overhead_category=other_cat,
            periode_bulan='2025-01', driver_value=Decimal('20'), rate_per_driver=Decimal('10000'),
        )

        results = period_end_closing('2025-01', akun_cogs.pk)
        self.assertEqual(len(results), 2)
        over = next(r for r in results if r['category'] == self.oh_cat.name)
        under = next(r for r in results if r['category'] == other_cat.name)
        self.assertEqual(over['variance'], Decimal('10000'))
        self.assertEqual(under['variance'], Decimal('-20000'))
        self.assertIsNotNone(over['journal_id'])
        self.assertIsNotNone(under['journal_id'])
        self.assertTrue(JurnalDetail.objects.filter(jurnal_header_id=over['journal_id'], akun=self.akun_applied, debit=Decimal('10000')).exists())
        self.assertTrue(JurnalDetail.objects.filter(jurnal_header_id=under['journal_id'], akun=self.akun_applied, kredit=Decimal('20000')).exists())

        header_over = JurnalHeader.objects.get(
            uraian_transaksi=f'Closing overhead over-absorbed {self.oh_cat.name} 2025-01'
        )
        self.assertEqual(header_over.tanggal, date(2025, 1, 31))
        self.assertEqual(header_over.entitas_bisnis, self.eb)

        current_count = JurnalHeader.objects.filter(uraian_transaksi__contains='Closing overhead').count()
        results_again = period_end_closing('2025-01', akun_cogs.pk)
        self.assertEqual(
            JurnalHeader.objects.filter(uraian_transaksi__contains='Closing overhead').count(),
            current_count,
        )
        self.assertTrue(all(result['journal_id'] is None for result in results_again))


# ---------------------------------------------------------------------------
# Warehouse (multi-gudang) wiring tests — Task 6
# ---------------------------------------------------------------------------

class ProductionWarehouseTests(TestCase):
    """RM consumption must lock to warehouse_rm; FG inflow must land in
    warehouse_fg, for both the direct-completed and WIP-approval paths."""

    def setUp(self):
        from apps.inventory.models import Warehouse
        self.user = _make_user()
        self.eb = _make_entitas()
        self.wh_rm = Warehouse.objects.create(entitas_bisnis=self.eb, kode='WH-RM', nama='Gudang Bahan Baku')
        self.wh_fg = Warehouse.objects.create(entitas_bisnis=self.eb, kode='WH-FG', nama='Gudang Barang Jadi')
        self.akun_wip = _make_akun('1301', 'WIP')
        self.akun_rm = _make_akun('1201', 'Persediaan RM')
        self.akun_fg = _make_akun('1401', 'Persediaan FG')
        self.fg = _make_item('FG-0002', 'Kopi Sachet WH', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0002', 'Biji Kopi WH', 'RM', self.akun_rm)
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm)
        rm_batch = _seed_fifo(self.rm, [('2025-01-01', 100, 5000)])[0]

        from apps.inventory.ledger import record_inflow
        record_inflow(self.rm, self.eb, None, None, Decimal('100'),
                      Decimal('5000'), '2025-01-01', 'purchase_in',
                      legacy_fifo_batch=rm_batch, warehouse=self.wh_rm)

        self.order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=self.eb,
            bom=self.bom, qty_produced=Decimal('10'), coa_produksi=self.akun_wip,
            warehouse_rm=self.wh_rm, warehouse_fg=self.wh_fg,
        )

    def test_process_production_locks_rm_and_fg_warehouses(self):
        """Completed path: RM outflow warehouse=wh_rm, FG inflow warehouse=wh_fg."""
        from .services import process_production
        from apps.inventory.models import StockMovement
        process_production(self.order)

        rm_out = StockMovement.objects.get(
            item=self.rm, movement_type='production_out',
            source_content_type__model='productionorder', source_object_id=self.order.pk,
        )
        self.assertEqual(rm_out.warehouse_id, self.wh_rm.pk)

        fg_in = StockMovement.objects.get(
            item=self.fg, movement_type='production_in',
            source_content_type__model='productionorder', source_object_id=self.order.pk,
        )
        self.assertEqual(fg_in.warehouse_id, self.wh_fg.pk)

    def test_approve_production_locks_fg_warehouse(self):
        """WIP-approval path: FG inflow must also land in warehouse_fg."""
        from .services import process_production, approve_production
        from apps.inventory.models import StockMovement
        process_production(self.order, as_wip=True)
        approve_production(self.order)

        fg_in = StockMovement.objects.get(
            item=self.fg, movement_type='production_in',
            source_content_type__model='productionorder', source_object_id=self.order.pk,
        )
        self.assertEqual(fg_in.warehouse_id, self.wh_fg.pk)


class ProductionOrderFormWarehouseTenantTests(TestCase):
    """ProductionOrderForm.clean() must reject a warehouse_rm/warehouse_fg
    that belongs to a different business (entitas_bisnis) than the one
    selected on the form, with a clean field error — not an unhandled
    ValueError from apps.inventory.ledger._validate_warehouse_tenant at
    ledger-call time."""

    def setUp(self):
        from apps.inventory.models import Warehouse
        self.eb = _make_entitas()
        self.other_eb = EntitasBisnis.objects.create(
            nama='Bisnis Lain',
            tipe_entitas=self.eb.tipe_entitas,
            status_aktif=True,
        )
        self.wh_rm_same = Warehouse.objects.create(
            entitas_bisnis=self.eb, kode='WH-RM-A', nama='Gudang RM Bisnis A',
        )
        self.wh_fg_same = Warehouse.objects.create(
            entitas_bisnis=self.eb, kode='WH-FG-A', nama='Gudang FG Bisnis A',
        )
        self.wh_rm_other = Warehouse.objects.create(
            entitas_bisnis=self.other_eb, kode='WH-RM-B', nama='Gudang RM Bisnis B',
        )
        self.akun_wip = _make_akun('1301', 'WIP')
        self.akun_rm = _make_akun('1201', 'Persediaan RM')
        self.akun_fg = _make_akun('1401', 'Persediaan FG')
        self.fg = _make_item('FG-0003', 'Kopi Sachet Form', 'FG', self.akun_fg)
        self.rm = _make_item('RM-0003', 'Biji Kopi Form', 'RM', self.akun_rm)
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm)

    def _base_data(self):
        return {
            'tanggal': '2025-01-10',
            'entitas_bisnis': self.eb.pk,
            'bom': self.bom.pk,
            'qty_produced': '10',
            'status': 'completed',
            'coa_produksi': self.akun_wip.pk,
        }

    def test_warehouse_rm_from_other_business_is_rejected(self):
        from .forms import ProductionOrderForm
        data = self._base_data()
        data['warehouse_rm'] = self.wh_rm_other.pk
        data['warehouse_fg'] = self.wh_fg_same.pk
        form = ProductionOrderForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('warehouse_rm', form.errors)

    def test_warehouse_fg_from_other_business_is_rejected(self):
        from .forms import ProductionOrderForm
        data = self._base_data()
        data['warehouse_rm'] = self.wh_rm_same.pk
        data['warehouse_fg'] = self.wh_rm_other.pk
        form = ProductionOrderForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('warehouse_fg', form.errors)

    def test_warehouses_matching_business_are_accepted(self):
        from .forms import ProductionOrderForm
        data = self._base_data()
        data['warehouse_rm'] = self.wh_rm_same.pk
        data['warehouse_fg'] = self.wh_fg_same.pk
        form = ProductionOrderForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)


# ---------------------------------------------------------------------------
# Bulk FG (FGB) production tests — value-based ledger convention
# ---------------------------------------------------------------------------

class ProductionBulkFGTests(TestCase):
    """FG completion for a bulk finished good (FGB) must follow the ledger's
    value-based convention (qty=1, unit_cost=total_value), same as Purchase's
    inflow dual-write for bulk items. RM lines stay non-bulk (RM) here — the
    RM-consumption side for bulk (RMB) is out of scope, see task report."""

    def setUp(self):
        self.user = _make_user()
        self.eb = _make_entitas()
        self.akun_wip = _make_akun('1301', 'WIP')
        self.akun_rm = _make_akun('1201', 'Persediaan RM')
        self.akun_fg = _make_akun('1401', 'Persediaan FG Bulk')
        self.fg = _make_item('FGB-0001', 'Semen Curah', 'FGB', self.akun_fg)
        self.rm = _make_item('RM-0001', 'Klinker', 'RM', self.akun_rm)
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm, qty_per_unit=Decimal('2'))
        rm_batch = _seed_fifo(self.rm, [('2025-01-01', 100, 5000)])[0]
        from apps.inventory.ledger import record_inflow
        record_inflow(self.rm, self.eb, None, None, Decimal('100'),
                      Decimal('5000'), '2025-01-01', 'purchase_in',
                      legacy_fifo_batch=rm_batch)
        self.order = ProductionOrder.objects.create(
            tanggal='2025-01-10', entitas_bisnis=self.eb,
            bom=self.bom, qty_produced=Decimal('10'), coa_produksi=self.akun_wip,
        )

    def test_process_production_bulk_fg_uses_value_convention(self):
        """qty_produced=10, 2 RM/unit @ 5000 = 100,000 total_cost (no overhead).
        Bulk FG completion must write qty=1 / unit_cost=total_value everywhere,
        not qty=10 / unit_cost=per-unit."""
        from .services import process_production
        from apps.purchase.models import FIFOBatch
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.inventory.ledger import get_available_stock

        process_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_cost, Decimal('100000'))

        fg_batch = FIFOBatch.objects.get(item=self.fg)
        self.assertEqual(fg_batch.quantity_in, Decimal('1'))
        self.assertEqual(fg_batch.unit_price, Decimal('100000'))
        self.assertEqual(fg_batch.remaining_qty, Decimal('1'))

        fg_rec = InventoryRecord.objects.get(item=self.fg)
        self.assertEqual(fg_rec.quantity, Decimal('1'))
        self.assertEqual(fg_rec.unit_price, Decimal('100000'))

        fg_movement = StockMovement.objects.get(item=self.fg, movement_type='production_in')
        self.assertEqual(fg_movement.qty, Decimal('1'))
        self.assertEqual(fg_movement.unit_cost, Decimal('100000'))
        self.assertEqual(fg_movement.remaining_qty, Decimal('1'))

        # Ledger get_available_stock is unit-agnostic (sums remaining_qty);
        # for a bulk layer that's the bulk "1 unit" convention, not a real qty.
        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('1'))

    def test_approve_production_bulk_fg_uses_value_convention(self):
        """Same value-based convention must hold for the WIP-approval path."""
        from .services import process_production, approve_production
        from apps.purchase.models import FIFOBatch
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.inventory.ledger import get_available_stock

        self.order.status = 'in_progress'
        self.order.save()
        process_production(self.order, as_wip=True)
        approve_production(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_cost, Decimal('100000'))

        fg_batch = FIFOBatch.objects.get(item=self.fg)
        self.assertEqual(fg_batch.quantity_in, Decimal('1'))
        self.assertEqual(fg_batch.unit_price, Decimal('100000'))

        fg_rec = InventoryRecord.objects.get(item=self.fg)
        self.assertEqual(fg_rec.quantity, Decimal('1'))
        self.assertEqual(fg_rec.unit_price, Decimal('100000'))

        fg_movement = StockMovement.objects.get(item=self.fg, movement_type='production_in')
        self.assertEqual(fg_movement.qty, Decimal('1'))
        self.assertEqual(fg_movement.unit_cost, Decimal('100000'))

        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('1'))

    def test_reverse_production_bulk_fg_removes_ledger_layer(self):
        """Reversal of a bulk-FG production order must remove the FG layer,
        leaving get_available_stock at 0 — same as the non-bulk case."""
        from .services import process_production, reverse_production
        from apps.inventory.ledger import get_available_stock

        process_production(self.order)
        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('1'))

        reverse_production(self.order)
        self.assertEqual(get_available_stock(self.fg, self.eb), Decimal('0'))
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_processed)


# ---------------------------------------------------------------------------
# BOM view tests
# ---------------------------------------------------------------------------

class ParseBomLinesTests(TestCase):
    """Direct unit tests of parse_bom_lines() — bypasses login/client so it
    is unaffected by the pre-existing axes-backend test-client issue."""

    def setUp(self):
        self.rm = _make_item('RM-0001', 'Biji Kopi', 'RM')
        self.rmb = _make_item('RMB-0001', 'Minyak Curah', 'RMB')
        self.fgb = _make_item('FGB-0001', 'Selai Curah', 'FGB')
        self.itmb = _make_item('ITMB-0001', 'Bahan Curah Lain', 'ITMB')

    def test_normal_rm_is_accepted(self):
        from .forms import parse_bom_lines
        lines, errors = parse_bom_lines({'rm_0': str(self.rm.pk), 'qty_0': '2.0000'})
        self.assertEqual(errors, [])
        self.assertEqual(len(lines), 1)

    def test_bulk_rmb_is_rejected(self):
        from .forms import parse_bom_lines
        lines, errors = parse_bom_lines({'rm_0': str(self.rmb.pk), 'qty_0': '0.5000'})
        self.assertTrue(errors, 'RMB raw_material should produce a validation error')
        self.assertEqual(lines, [])

    def test_bulk_fgb_is_rejected(self):
        from .forms import parse_bom_lines
        lines, errors = parse_bom_lines({'rm_0': str(self.fgb.pk), 'qty_0': '0.5000'})
        self.assertTrue(errors, 'FGB raw_material should produce a validation error')
        self.assertEqual(lines, [])

    def test_bulk_itmb_is_rejected(self):
        from .forms import parse_bom_lines
        lines, errors = parse_bom_lines({'rm_0': str(self.itmb.pk), 'qty_0': '0.5000'})
        self.assertTrue(errors, 'ITMB raw_material should produce a validation error')
        self.assertEqual(lines, [])

    def test_mixed_lines_one_bulk_one_normal_reports_error(self):
        """A bulk-RM line anywhere in the batch must produce an error, which
        the calling view treats as fatal (it only saves when there are no
        errors at all — see bom_create/bom_update in views.py)."""
        from .forms import parse_bom_lines
        lines, errors = parse_bom_lines({
            'rm_0': str(self.rm.pk), 'qty_0': '2.0000',
            'rm_1': str(self.rmb.pk), 'qty_1': '0.5000',
        })
        self.assertTrue(errors)


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
        bom = _make_bom_with_line(self.eb, self.fg, self.rm)
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

    def test_bom_create_post_rejects_bulk_raw_material(self):
        """RMB (bulk RM) has no defined qty_required semantics — must be
        rejected as a BOM raw material at the form/view level, not silently
        misinterpreted as a value by consume_stock() downstream."""
        rmb = _make_item('RMB-0001', 'Minyak Curah', 'RMB')
        response = self.client.post(reverse('manufacturing:bom_create'), {
            'finished_good': self.fg.pk,
            'entitas_bisnis': self.eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': rmb.pk,
            'qty_0': '0.5000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BillOfMaterials.objects.count(), 0)

    def test_bom_create_post_rejects_itmb_raw_material(self):
        itmb = _make_item('ITMB-0001', 'Bahan Curah Lain', 'ITMB')
        response = self.client.post(reverse('manufacturing:bom_create'), {
            'finished_good': self.fg.pk,
            'entitas_bisnis': self.eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': itmb.pk,
            'qty_0': '0.5000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BillOfMaterials.objects.count(), 0)

    def test_bom_update_post_rejects_bulk_raw_material(self):
        rmb = _make_item('RMB-0002', 'Minyak Curah 2', 'RMB')
        bom = _make_bom_with_line(self.eb, self.fg, self.rm)
        response = self.client.post(reverse('manufacturing:bom_update', args=[bom.pk]), {
            'finished_good': self.fg.pk,
            'entitas_bisnis': self.eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': rmb.pk,
            'qty_0': '0.5000',
        })
        self.assertEqual(response.status_code, 200)
        # Existing valid line must remain untouched
        bom.refresh_from_db()
        self.assertEqual(bom.lines.count(), 1)
        self.assertEqual(bom.lines.first().raw_material_id, self.rm.pk)

    def test_bom_create_post_normal_rm_still_valid(self):
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


# ---------------------------------------------------------------------------
# Production Order view tests
# ---------------------------------------------------------------------------

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
        self.bom = _make_bom_with_line(self.eb, self.fg, self.rm)
        rm_batch = _seed_fifo(self.rm, [('2025-01-01', 100, 5000)])[0]
        # Also seed the authoritative stock ledger, mirrored to the legacy
        # FIFOBatch — process_production consumes RM via StockMovement
        # layers, not FIFOBatch directly (see ProductionServiceTests.setUp).
        from apps.inventory.ledger import record_inflow
        record_inflow(self.rm, self.eb, None, None, Decimal('100'),
                      Decimal('5000'), '2025-01-01', 'purchase_in',
                      legacy_fifo_batch=rm_batch)

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
            'status': 'completed',
            'coa_produksi': self.akun_wip.pk,
        })
        self.assertEqual(ProductionOrder.objects.count(), 1)
        order = ProductionOrder.objects.first()
        self.assertTrue(order.is_processed)
        self.assertEqual(order.status, 'completed')

    def test_production_create_post_wip(self):
        response = self.client.post(reverse('manufacturing:production_create'), {
            'tanggal': '2025-01-10',
            'entitas_bisnis': self.eb.pk,
            'bom': self.bom.pk,
            'qty_produced': '5',
            'status': 'in_progress',
            'coa_produksi': self.akun_wip.pk,
        })
        order = ProductionOrder.objects.first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, 'in_progress')

    def test_production_create_post_persen_rm_cost_uses_server_side_rm_cost(self):
        akun_beban = _make_akun('5102', 'Overhead Umum')
        akun_applied = _make_akun('2102', 'Overhead Applied Umum', 'kewajiban')
        cat = OverheadCategory.objects.create(
            name='Overhead % RM', overhead_type='PRODUCTION',
            coa_expense=akun_beban, coa_overhead_applied=akun_applied,
            cost_driver='PERSEN_RM_COST',
        )
        OverheadRate.objects.create(
            overhead_category=cat, periode_bulan='2025-01',
            estimasi_total=Decimal('1000000'), rate_per_driver=Decimal('0.10'),
        )

        response = self.client.post(reverse('manufacturing:production_create'), {
            'tanggal': '2025-01-10',
            'entitas_bisnis': self.eb.pk,
            'bom': self.bom.pk,
            'qty_produced': '5',
            'status': 'completed',
            'coa_produksi': self.akun_wip.pk,
        })
        self.assertEqual(ProductionOrder.objects.count(), 1)
        order = ProductionOrder.objects.first()
        self.assertEqual(order.overhead_cost, Decimal('5000'))
        self.assertEqual(order.total_cost, Decimal('55000'))

    def test_api_bom_preview(self):
        response = self.client.get(reverse('manufacturing:api_bom_preview'), {
            'bom_id': self.bom.pk,
            'qty_produced': '5',
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('lines', data)
        self.assertIn('rm_cost', data)
        # 5 FG Ã— 2 RM Ã— 5,000 = 50,000
        self.assertEqual(Decimal(data['rm_cost']), Decimal('50000.0000'))

    def test_api_boms_by_entity(self):
        response = self.client.get(
            reverse('manufacturing:api_boms_by_entity'),
            {'eb_id': self.eb.pk},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['boms']), 1)
        self.assertEqual(data['boms'][0]['bom_id'], self.bom.bom_id)


# ---------------------------------------------------------------------------
# Production EB isolation tests (authoritative stock ledger)
# ---------------------------------------------------------------------------

class ProductionEBIsolationTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.purchase.models import ItemMasterPurchase
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Pabrik A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Pabrik B')
        self.rm = ItemMasterPurchase.objects.create(nama='Tepung', tipe_item='RM')

    def test_production_consume_isolated_by_eb(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError, record_inflow
        # stok RM hanya di Pabrik B
        record_inflow(self.rm, self.eb, self.lv2, self.lv3b, Decimal('100'),
                      Decimal('2'), '2026-01-01', 'purchase_in')
        # produksi di Pabrik A minta 10 → harus gagal (tak lihat stok B)
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.rm, self.eb, self.lv2, self.lv3a, Decimal('10'),
                          '2026-01-03', 'production_out')


# ---------------------------------------------------------------------------
# Overhead Category view tests
# ---------------------------------------------------------------------------

class OverheadCategoryViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.login(email='test@example.com', password='testpass123')
        self.akun_beban = _make_akun('5101', 'Listrik Mesin')
        self.akun_applied = _make_akun('2101', 'Overhead Applied', 'kewajiban')

    def test_list(self):
        response = self.client.get(reverse('manufacturing:overhead_category_list'))
        self.assertEqual(response.status_code, 200)

    def test_create_get(self):
        response = self.client.get(reverse('manufacturing:overhead_category_create'))
        self.assertEqual(response.status_code, 200)

    def test_create_post_production(self):
        response = self.client.post(reverse('manufacturing:overhead_category_create'), {
            'name': 'Listrik Mesin',
            'overhead_type': 'PRODUCTION',
            'coa_expense': self.akun_beban.pk,
            'coa_overhead_applied': self.akun_applied.pk,
            'cost_driver': 'PER_UNIT',
            'is_active': True,
        })
        self.assertEqual(OverheadCategory.objects.count(), 1)
        cat = OverheadCategory.objects.first()
        self.assertEqual(cat.cost_driver, 'PER_UNIT')
        self.assertEqual(cat.overhead_type, 'PRODUCTION')

    def test_create_post_period(self):
        response = self.client.post(reverse('manufacturing:overhead_category_create'), {
            'name': 'Listrik Kantor',
            'overhead_type': 'PERIOD',
            'coa_expense': self.akun_beban.pk,
            'coa_overhead_applied': '',
            'cost_driver': '',
            'is_active': True,
        })
        self.assertEqual(OverheadCategory.objects.count(), 1)
        cat = OverheadCategory.objects.first()
        self.assertIsNone(cat.cost_driver)
        self.assertIsNone(cat.coa_overhead_applied)


# ---------------------------------------------------------------------------
# UOM conversion in Manufacturing (BOM + Production) — Task 7
# ---------------------------------------------------------------------------

class ManufacturingUomTests(TestCase):
    def setUp(self):
        from apps.uom.models import UnitOfMeasure, ItemUOM
        from apps.uom.conversion import convert_input_to_base
        self._convert_input_to_base = convert_input_to_base
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.rm = _make_item('RM-UOM-0001', 'RM-A', 'RM')
        self.rm.stock_uom = self.pcs
        self.rm.save()
        self.ctn = UnitOfMeasure.objects.create(
            kode='ctn-m', nama='Carton', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.rm, uom=self.ctn, qty_in_stock_uom=Decimal('24'))

    def test_bom_qty_converts_to_base(self):
        qty_base, _ = self._convert_input_to_base(self.rm, self.ctn, Decimal('2'), Decimal('0'))
        self.assertEqual(qty_base, Decimal('48'))

    def test_bom_create_view_converts_input_uom_to_base(self):
        """POST with input_uom_0/qty_0 in a packaging UOM must store
        qty_required in the item's base/stock_uom, and persist the raw
        input_uom/input_qty on the BOMLine for audit."""
        user = _make_user()
        self.client.force_login(user)
        eb = _make_entitas()
        fg = _make_item('FG-UOM-0001', 'FG-A', 'FG')

        response = self.client.post(reverse('manufacturing:bom_create'), {
            'finished_good': fg.pk,
            'entitas_bisnis': eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': self.rm.pk,
            'qty_0': '2',
            'input_uom_0': self.ctn.pk,
        })
        self.assertEqual(BillOfMaterials.objects.count(), 1)
        bom = BillOfMaterials.objects.first()
        line = bom.lines.first()
        self.assertEqual(line.qty_required, Decimal('48'))
        self.assertEqual(line.input_uom_id, self.ctn.pk)
        self.assertEqual(line.input_qty, Decimal('2'))

    def test_bom_create_view_without_input_uom_is_unchanged(self):
        """Regression: POST without input_uom_i must behave exactly as
        before this change — qty_i is read directly as qty_required."""
        user = _make_user()
        self.client.force_login(user)
        eb = _make_entitas()
        fg = _make_item('FG-UOM-0002', 'FG-B', 'FG')

        response = self.client.post(reverse('manufacturing:bom_create'), {
            'finished_good': fg.pk,
            'entitas_bisnis': eb.pk,
            'tanggal_dibuat': '2025-01-01',
            'catatan': '',
            'rm_0': self.rm.pk,
            'qty_0': '2.0000',
        })
        self.assertEqual(BillOfMaterials.objects.count(), 1)
        bom = BillOfMaterials.objects.first()
        line = bom.lines.first()
        self.assertEqual(line.qty_required, Decimal('2.0000'))
        self.assertIsNone(line.input_uom_id)
        self.assertIsNone(line.input_qty)

    def test_production_create_view_converts_input_uom_to_base(self):
        """POST with input_uom on the production form must store
        qty_produced in the FG's base/stock_uom, and persist input_uom/
        input_qty on the ProductionOrder for audit."""
        from apps.uom.models import ItemUOM
        from apps.inventory.ledger import record_inflow

        user = _make_user()
        self.client.force_login(user)
        eb = _make_entitas()
        akun_wip = _make_akun('5901', 'WIP-UOM')
        akun_rm = _make_akun('1491', 'Persediaan RM UOM')
        akun_fg = _make_akun('1492', 'Persediaan FG UOM')
        fg = _make_item('FG-UOM-0003', 'FG-C', 'FG', akun_fg)
        fg.stock_uom = self.pcs
        fg.save()
        fg_box = self._get_or_create_uom('box-fg', 'Box FG', 'count')
        ItemUOM.objects.create(item=fg, uom=fg_box, qty_in_stock_uom=Decimal('10'))

        rm = _make_item('RM-UOM-0003', 'RM-C', 'RM', akun_rm)
        bom = _make_bom_with_line(eb, fg, rm, qty_per_unit=Decimal('2'))
        rm_batch = _seed_fifo(rm, [('2025-01-01', 1000, 5000)])[0]
        record_inflow(rm, eb, None, None, Decimal('1000'), Decimal('5000'),
                      '2025-01-01', 'purchase_in', legacy_fifo_batch=rm_batch)

        response = self.client.post(reverse('manufacturing:production_create'), {
            'tanggal': '2025-01-10',
            'entitas_bisnis': eb.pk,
            'bom': bom.pk,
            'qty_produced': '3',
            'input_uom': fg_box.pk,
            'status': 'completed',
            'coa_produksi': akun_wip.pk,
        })
        self.assertEqual(ProductionOrder.objects.count(), 1)
        order = ProductionOrder.objects.first()
        # 3 box x 10 pcs/box = 30 pcs (base qty)
        self.assertEqual(order.qty_produced, Decimal('30'))
        self.assertEqual(order.input_uom_id, fg_box.pk)
        self.assertEqual(order.input_qty, Decimal('3'))

    def test_production_create_view_without_input_uom_is_unchanged(self):
        """Regression: POST without input_uom must behave exactly as before
        this change — qty_produced is read directly as the base qty."""
        from apps.inventory.ledger import record_inflow

        user = _make_user()
        self.client.force_login(user)
        eb = _make_entitas()
        akun_wip = _make_akun('5902', 'WIP-UOM-2')
        akun_rm = _make_akun('1493', 'Persediaan RM UOM 2')
        akun_fg = _make_akun('1494', 'Persediaan FG UOM 2')
        fg = _make_item('FG-UOM-0004', 'FG-D', 'FG', akun_fg)
        rm = _make_item('RM-UOM-0004', 'RM-D', 'RM', akun_rm)
        bom = _make_bom_with_line(eb, fg, rm, qty_per_unit=Decimal('2'))
        rm_batch = _seed_fifo(rm, [('2025-01-01', 1000, 5000)])[0]
        record_inflow(rm, eb, None, None, Decimal('1000'), Decimal('5000'),
                      '2025-01-01', 'purchase_in', legacy_fifo_batch=rm_batch)

        response = self.client.post(reverse('manufacturing:production_create'), {
            'tanggal': '2025-01-10',
            'entitas_bisnis': eb.pk,
            'bom': bom.pk,
            'qty_produced': '5',
            'status': 'completed',
            'coa_produksi': akun_wip.pk,
        })
        self.assertEqual(ProductionOrder.objects.count(), 1)
        order = ProductionOrder.objects.first()
        self.assertEqual(order.qty_produced, Decimal('5'))
        self.assertIsNone(order.input_uom_id)
        self.assertIsNone(order.input_qty)

    @staticmethod
    def _get_or_create_uom(kode, nama, dimension):
        from apps.uom.models import UnitOfMeasure
        obj, _ = UnitOfMeasure.objects.get_or_create(
            kode=kode, defaults={'nama': nama, 'dimension': dimension, 'factor_to_base': None},
        )
        return obj

    def test_bom_create_get_renders_input_uom_select_markup(self):
        """The row-builder JS must emit an input_uom_<i> select per BOM line
        and expose the UOM catalogue as data for it to populate from."""
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:bom_create'))
        content = response.content.decode()
        self.assertIn("name=\"input_uom_'", content)
        self.assertIn('UOM_DATA', content)
        self.assertIn(self.ctn.kode, content)

    def test_bom_create_get_uom_data_is_ordered_list_not_dict(self):
        """UOM_DATA must be a JSON array (order-preserving), not an object
        keyed by numeric id — JS sorts numeric-string object keys ascending
        regardless of insertion order, which silently discarded the
        backend's dimension/kode ordering."""
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:bom_create'))
        content = response.content.decode()
        uom_data_start = content.index('var UOM_DATA = ') + len('var UOM_DATA = ')
        uom_data_json = content[uom_data_start:content.index(';', uom_data_start)]
        import json
        data = json.loads(uom_data_json)
        self.assertIsInstance(data, list)
        self.assertIn('dimension_label', data[0])

    def test_production_create_get_renders_input_uom_optgroups_in_order(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:production_create'))
        content = response.content.decode()
        count_pos = content.index('<optgroup label="Count / Jumlah">')
        weight_pos = content.index('<optgroup label="Berat">')
        volume_pos = content.index('<optgroup label="Volume">')
        length_pos = content.index('<optgroup label="Panjang">')
        area_pos = content.index('<optgroup label="Luas">')
        self.assertTrue(count_pos < weight_pos < volume_pos < length_pos < area_pos)

    def test_bom_update_get_prefills_existing_line_input_uom(self):
        """Editing a BOM line saved with a packaging input_uom must show the
        original input_qty/input_uom, not the converted base qty_required."""
        user = _make_user()
        self.client.force_login(user)
        eb = _make_entitas()
        fg = _make_item('FG-UOM-0005', 'FG-E', 'FG')
        bom = BillOfMaterials.objects.create(
            finished_good=fg, entitas_bisnis=eb, tanggal_dibuat='2025-01-01',
        )
        BOMLine.objects.create(
            bom=bom, raw_material=self.rm, qty_required=Decimal('48'),
            input_uom=self.ctn, input_qty=Decimal('2'),
        )

        response = self.client.get(reverse('manufacturing:bom_update', args=[bom.pk]))
        content = response.content.decode()
        match = re.search(
            r"addRow\('%s',\s*'([^']*)',\s*'([^']*)'\)" % re.escape(str(self.rm.pk)),
            content,
        )
        self.assertIsNotNone(match, 'addRow(...) call for existing line not found in rendered page')
        # Must be plain-numeric (unlocalized) — a comma decimal separator (id
        # locale default) would make the <input type="number"> silently blank.
        self.assertEqual(Decimal(match.group(1)), Decimal('2'))
        self.assertEqual(match.group(2), str(self.ctn.pk))

    def test_production_create_get_renders_input_uom_field(self):
        """The production order form's optional input_uom field must actually
        be rendered on the create page, not just exist on the ModelForm."""
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:production_create'))
        self.assertContains(response, 'id_input_uom')


class SimulateCostMethodTests(TestCase):
    def setUp(self):
        self.rm = _make_item('RM-M', 'RM Metode', 'RM')
        _seed_fifo(self.rm, [
            ('2026-01-01', 10, 100),
            ('2026-01-02', 10, 200),
        ])

    def test_fifo_default(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('12'))
        self.assertEqual(cost, Decimal('1400'))   # 10×100 + 2×200
        self.assertEqual(filled, Decimal('12'))

    def test_lifo(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('12'), metode='lifo')
        self.assertEqual(cost, Decimal('2200'))   # 10×200 + 2×100
        self.assertEqual(filled, Decimal('12'))

    def test_average(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('5'), metode='average')
        self.assertEqual(cost, Decimal('750'))     # 5 × 150
        self.assertEqual(filled, Decimal('5'))

