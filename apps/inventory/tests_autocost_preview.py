"""Tests: auto unit cost (per metode costing) + preview jurnal & mutasi."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger
from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3
from apps.inventory.forms import StockAdjustmentForm


class CurrentUnitCostTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.item.coa_account = self.persediaan
        self.item.save()
        # dua layer harga berbeda: 100 (lebih tua), lalu 120 (lebih baru)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('120'), '2026-01-05', 'adjustment_in', warehouse=self.wh)

    def test_fifo_returns_oldest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='fifo')
        self.assertEqual(c, Decimal('100'))

    def test_lifo_returns_newest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='lifo')
        self.assertEqual(c, Decimal('120'))

    def test_average_returns_weighted_average(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='average')
        self.assertEqual(c, Decimal('110'))  # (10*100 + 10*120)/20

    def test_none_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        c = ledger.current_unit_cost(other, self.eb, warehouse=self.wh, metode='fifo')
        self.assertIsNone(c)

    def test_defaults_to_item_method(self):
        self.item.metode_biaya_persediaan = 'lifo'
        self.item.save()
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(c, Decimal('120'))


class StockAvailableEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='u1@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('4'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def test_returns_available_and_unit_cost(self):
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': self.item.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertEqual(Decimal(data['available']), Decimal('4'))
        self.assertEqual(Decimal(data['unit_cost']), Decimal('100'))

    def test_unit_cost_null_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': other.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertIsNone(data['unit_cost'])


class EbHierarkiResolveTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(nama='Divisi A', entitas_bisnis=self.eb)
        self.lv3 = EntitasBisnisLv3.objects.create(nama='Sub A1', parent_lv2=self.lv2)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')

    def _data(self, eb_hierarki):
        return {
            'tanggal': '2026-07-18', 'eb_hierarki': eb_hierarki,
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
        }

    def test_lv3_resolves_all_three_fks(self):
        form = StockAdjustmentForm(data=self._data(f'lv3:{self.lv3.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv2'], self.lv2)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv3'], self.lv3)

    def test_lv1_resolves_only_lv1(self):
        form = StockAdjustmentForm(data=self._data(f'lv1:{self.eb.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv2'])
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv3'])

    def test_default_tanggal_is_today(self):
        from django.utils import timezone
        form = StockAdjustmentForm()
        self.assertEqual(form.fields['tanggal'].initial, timezone.localdate())


class AdjustmentPreviewEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='u2@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def _post(self, qty):
        return self.client.post('/inventory/adjustment/preview/', {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty': qty, 'items-0-unit_cost': '100',
        })

    def test_preview_increase_returns_balanced_journal_and_mutation(self):
        data = self._post('5')
        self.assertTrue(data.status_code == 200)
        j = data.json()
        self.assertTrue(j['ok'])
        self.assertTrue(j['balance'])
        self.assertEqual(Decimal(j['total_debit']), Decimal(j['total_kredit']))
        self.assertEqual(Decimal(j['total_debit']), Decimal('500'))  # 5 * 100
        mut = j['mutasi'][0]
        self.assertEqual(mut['movement_type'], 'adjustment_in')
        self.assertEqual(Decimal(mut['stok_sebelum']), Decimal('10'))
        self.assertEqual(Decimal(mut['stok_sesudah']), Decimal('15'))

    def test_preview_does_not_persist(self):
        from apps.inventory.models import StockAdjustment, StockMovement
        before_adj = StockAdjustment.objects.count()
        before_mv = StockMovement.objects.count()
        self._post('5')
        self.assertEqual(StockAdjustment.objects.count(), before_adj)
        self.assertEqual(StockMovement.objects.count(), before_mv)

    def test_preview_decrease_fifo_cost_exact(self):
        # tambah layer kedua lebih mahal; turun 12 -> 10*100 + 2*120 = 1240
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('120'), '2026-01-05', 'adjustment_in', warehouse=self.wh)
        data = self._post('-12')
        j = data.json()
        self.assertEqual(Decimal(j['total_debit']), Decimal('1240'))
        self.assertEqual(j['mutasi'][0]['movement_type'], 'adjustment_out')


class PreviewEqualsPostingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='u3@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def test_opname_preview_and_real_posting_match(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        payload = {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty_sistem': '20',
            'items-0-qty_fisik': '18', 'items-0-unit_cost': '100',
        }
        prev = self.client.post('/inventory/opname/preview/', payload).json()
        # posting sungguhan
        opn = StockOpname.objects.create(tanggal='2026-07-18', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=opn, item=self.item,
                                       qty_sistem=Decimal('20'), qty_fisik=Decimal('18'),
                                       unit_cost=Decimal('100'))
        header = process_opname(opn)
        real_debit = sum(d.debit for d in header.details.all())
        self.assertEqual(Decimal(prev['total_debit']), real_debit)
        self.assertEqual(Decimal(prev['total_debit']), Decimal('200'))  # 2 * 100
        self.assertEqual(prev['mutasi'][0]['movement_type'], 'opname_out')
        self.assertEqual(Decimal(prev['mutasi'][0]['stok_sesudah']), Decimal('18'))


class LedgerUpdatedAfterPostTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='u4@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()

    def test_adjustment_create_updates_ledger(self):
        before = ledger.get_available_stock(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(before, Decimal('0'))
        resp = self.client.post('/inventory/adjustment/create/', {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty': '7', 'items-0-unit_cost': '100',
        })
        self.assertEqual(resp.status_code, 302)  # redirect ke list
        after = ledger.get_available_stock(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(after, Decimal('7'))
