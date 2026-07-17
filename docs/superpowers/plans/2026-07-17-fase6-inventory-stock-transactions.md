# Fase 6 — Transaksi & Kontrol Stok — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun Stock Adjustment, Stock Opname, Transfer antar gudang/cabang, Retur pelanggan & supplier (terhubung dokumen asal), dan Reorder Point per item+gudang di atas `StockMovement` ledger — serta membuang stub `MutasiInventory`.

**Architecture:** Semua transaksi memakai engine ledger existing (`record_inflow` untuk kenaikan, `consume_stock` untuk penurunan) tanpa ledger baru. Tiap transaksi = header/detail model + service posting (movement + jurnal balance-checked) + view/form/template pola `aset_tetap`. Akun jurnal lawan dipilih user per transaksi. Semua reversible via `reverse_movements`/`reverse_inflow_movements`.

**Tech Stack:** Django, `apps/inventory`, `apps/jurnal` (JurnalHeader/JurnalDetail), `apps/master_data.Akun`, pytest via Django `manage.py test`.

**Spec:** [docs/superpowers/specs/2026-07-17-fase6-inventory-stock-transactions-design.md](../specs/2026-07-17-fase6-inventory-stock-transactions-design.md)

**Test command (Windows):** `env/Scripts/python.exe manage.py test <path> -v 2 --keepdb` (jalankan dari `naveda_integra/`). Ganti `env/Scripts/python.exe` dengan `python` bila venv sudah aktif.

**Konvensi yang diikuti:**
- Header punya: `nomor` auto `TRX-<PREFIX>-NNN` (pola `_next_journal_number`), `tanggal`, `entitas_bisnis`(+lv2/lv3 nullable), `status` (`draft`/`posted`), `jurnal_header` FK nullable, `keterangan`, `created_at`.
- Jurnal: `JurnalHeader(tanggal, nomor_transaksi, uraian_transaksi, entitas_bisnis, is_penyesuaian)` + `JurnalDetail(jurnal_header, akun, debit, kredit)`; selalu cek `sum(debit) == sum(kredit)` sebelum commit.
- Reversal jurnal: `from apps.jurnal.utils import log_jurnal_terhapus; log_jurnal_terhapus(header, 'inventory', request)` lalu `header.details.all().delete(); header.delete()`.
- Akun persediaan item = `item.coa_account`. Metode costing = `item.metode_biaya_persediaan`.

---

## FASE 0 — Fondasi Ledger & Pembersihan Stub

### Task 0.1: Tambah movement types baru ke StockMovement

**Files:**
- Modify: `apps/inventory/models.py:246-252` (`MOVEMENT_TYPE_CHOICES`)
- Test: `apps/inventory/tests_fase6.py` (Create)

- [ ] **Step 1: Tulis test yang gagal**

Create `apps/inventory/tests_fase6.py`:

```python
"""Tests Fase 6 — transaksi & kontrol stok."""
from decimal import Decimal
from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import StockMovement


class MovementTypeChoicesTests(TestCase):
    def test_new_movement_types_registered(self):
        codes = {c for c, _ in StockMovement.MOVEMENT_TYPE_CHOICES}
        for expected in {
            'adjustment_in', 'adjustment_out', 'opname_in', 'opname_out',
            'transfer_in', 'transfer_out', 'return_customer', 'return_supplier',
        }:
            self.assertIn(expected, codes)
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.MovementTypeChoicesTests -v 2 --keepdb`
Expected: FAIL (`adjustment_in` not in codes).

- [ ] **Step 3: Tambah choices**

Di `apps/inventory/models.py`, `MOVEMENT_TYPE_CHOICES` menjadi:

```python
    MOVEMENT_TYPE_CHOICES = [
        ('purchase_in', 'Pembelian Masuk'),
        ('sale_out', 'Penjualan Keluar'),
        ('production_in', 'Produksi Masuk (FG)'),
        ('production_out', 'Produksi Keluar (RM)'),
        ('saldo_awal', 'Saldo Awal'),
        ('adjustment_in', 'Penyesuaian Masuk'),
        ('adjustment_out', 'Penyesuaian Keluar'),
        ('opname_in', 'Opname Surplus'),
        ('opname_out', 'Opname Minus'),
        ('transfer_in', 'Transfer Masuk'),
        ('transfer_out', 'Transfer Keluar'),
        ('return_customer', 'Retur Pelanggan (Masuk)'),
        ('return_supplier', 'Retur Supplier (Keluar)'),
    ]
```

- [ ] **Step 4: Buat migrasi & jalankan test**

Run: `env/Scripts/python.exe manage.py makemigrations inventory && env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.MovementTypeChoicesTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/models.py apps/inventory/migrations apps/inventory/tests_fase6.py
git commit -m "feat(inventory): tambah movement types Fase 6"
```

### Task 0.2: Perluas set reversal di ledger engine

**Files:**
- Modify: `apps/inventory/ledger.py:14` (`OUTFLOW_MOVEMENT_TYPES`) dan `:466` (`INFLOW_MOVEMENT_TYPES`)
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan di `apps/inventory/tests_fase6.py`:

```python
from apps.inventory import ledger


class ReversalSetTests(TestCase):
    def test_outflow_set_includes_fase6(self):
        for t in {'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier'}:
            self.assertIn(t, ledger.OUTFLOW_MOVEMENT_TYPES)

    def test_inflow_set_includes_fase6(self):
        for t in {'adjustment_in', 'opname_in', 'transfer_in', 'return_customer'}:
            self.assertIn(t, ledger.INFLOW_MOVEMENT_TYPES)
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ReversalSetTests -v 2 --keepdb`
Expected: FAIL.

- [ ] **Step 3: Perluas set**

Di `apps/inventory/ledger.py` ganti baris `OUTFLOW_MOVEMENT_TYPES = {'sale_out', 'production_out'}` menjadi:

```python
OUTFLOW_MOVEMENT_TYPES = {
    'sale_out', 'production_out',
    'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier',
}
```

Dan ganti `INFLOW_MOVEMENT_TYPES = {'purchase_in', 'production_in', 'saldo_awal'}` menjadi:

```python
INFLOW_MOVEMENT_TYPES = {
    'purchase_in', 'production_in', 'saldo_awal',
    'adjustment_in', 'opname_in', 'transfer_in', 'return_customer',
}
```

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ReversalSetTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests_fase6.py
git commit -m "feat(inventory): masukkan movement Fase 6 ke set reversal"
```

### Task 0.3: Buang stub MutasiInventoryHeader/Detail

**Files:**
- Modify: `apps/inventory/models.py:9-38` (hapus dua class)
- Modify: `apps/inventory/tests.py:7` (hapus import stub) dan hapus test yang memakainya bila ada
- Modify: `apps/inventory/admin.py` (hapus registrasi bila ada)
- Migrate: migrasi drop-table

- [ ] **Step 1: Verifikasi tidak ada referensi lain**

Run: `env/Scripts/python.exe -c "print('grep')"` lalu gunakan Grep tool untuk pola `MutasiInventory` di seluruh `apps/`. Expected: hanya muncul di `inventory/models.py`, `inventory/admin.py`, `inventory/tests.py`, dan migrasi lama. Jika ada modul lain, STOP dan laporkan.

- [ ] **Step 2: Hapus dua class model**

Hapus `class MutasiInventoryHeader` (`apps/inventory/models.py:9-26`) dan `class MutasiInventoryDetail` (`:29-38`) seluruhnya.

- [ ] **Step 3: Hapus referensi admin & test**

Di `apps/inventory/admin.py` hapus baris `admin.site.register(MutasiInventoryHeader...)`/`MutasiInventoryDetail` dan importnya bila ada. Di `apps/inventory/tests.py:7` ubah import menjadi:

```python
from .models import InventoryRecord
```

Hapus class test apa pun di `tests.py` yang mereferensikan `MutasiInventoryHeader`/`MutasiInventoryDetail` (mis. test membuat header/detail stub).

- [ ] **Step 4: Buat migrasi & migrasikan**

Run: `env/Scripts/python.exe manage.py makemigrations inventory`
Expected: migrasi berisi `DeleteModel` untuk kedua model.
Run: `env/Scripts/python.exe manage.py migrate inventory`

- [ ] **Step 5: Jalankan test app**

Run: `env/Scripts/python.exe manage.py test apps.inventory -v 1 --keepdb`
Expected: PASS (tidak ada ImportError).

- [ ] **Step 6: Commit**

```bash
git add apps/inventory/models.py apps/inventory/admin.py apps/inventory/tests.py apps/inventory/migrations
git commit -m "chore(inventory): buang stub MutasiInventory"
```

---

## FASE 1 — Stock Adjustment (pola acuan untuk fitur lain)

### Task 1.1: Model StockAdjustment + StockAdjustmentItem

**Files:**
- Modify: `apps/inventory/models.py` (tambah di akhir)
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
from apps.master_data.models import Akun


class StockAdjustmentModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='Gudang 1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.akun = Akun.objects.create(kode_akun='5.9.1', nama='Selisih Persediaan')

    def test_create_header_generates_nomor(self):
        from apps.inventory.models import StockAdjustment
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.akun,
        )
        self.assertTrue(h.nomor.startswith('TRX-ADJ-'))
        self.assertEqual(h.status, 'draft')

    def test_item_signed_qty(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.akun,
        )
        d = StockAdjustmentItem.objects.create(
            adjustment=h, item=self.item, qty=Decimal('-3'), unit_cost=Decimal('5'),
        )
        self.assertEqual(d.qty, Decimal('-3'))
```

> Catatan: `Akun` memakai field `kode_akun` & `nama` (bukan `nama_akun`) — sudah diverifikasi di `apps/master_data/models.py:180-207`.

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.StockAdjustmentModelTests -v 2 --keepdb`
Expected: FAIL (ImportError StockAdjustment).

- [ ] **Step 3: Tambah model**

Di akhir `apps/inventory/models.py`:

```python
class _NomorMixin:
    """Helper penghasil nomor TRX-<PREFIX>-NNN, aman-konkuren."""
    NOMOR_PREFIX = ''

    def _generate_nomor(self):
        from django.db import transaction as _t
        with _t.atomic():
            last = (
                type(self).objects.select_for_update()
                .filter(nomor__startswith=self.NOMOR_PREFIX)
                .order_by('-nomor').values_list('nomor', flat=True).first()
            )
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
            except (ValueError, IndexError):
                seq = 1
            return f'{self.NOMOR_PREFIX}{seq:03d}'


class StockAdjustment(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-ADJ-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='stock_adjustments')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments')
    akun_selisih = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='stock_adjustments', verbose_name='Akun Selisih Persediaan')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Adjustment'
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockAdjustmentItem(models.Model):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4, help_text='Bertanda: + naik, - turun')
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0, help_text='Untuk kenaikan')
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f'{self.item.item_id} × {self.qty}'
```

- [ ] **Step 4: Migrasi & test**

Run: `env/Scripts/python.exe manage.py makemigrations inventory && env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.StockAdjustmentModelTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/models.py apps/inventory/migrations apps/inventory/tests_fase6.py
git commit -m "feat(inventory): model StockAdjustment"
```

### Task 1.2: Service posting adjustment (movement + jurnal)

**Files:**
- Create: `apps/inventory/services.py`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
class ProcessAdjustmentTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih Persediaan')

    def _header(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih,
        )
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item,
                                           qty=Decimal('10'), unit_cost=Decimal('5'))
        return h

    def test_increase_creates_inflow_and_balanced_journal(self):
        from apps.inventory.services import process_adjustment
        from apps.inventory.ledger import get_available_stock
        h = self._header()
        header = process_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'posted')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('10'))
        deb = sum(d.debit for d in header.details.all())
        kre = sum(d.kredit for d in header.details.all())
        self.assertEqual(deb, kre)
        self.assertEqual(deb, Decimal('50'))

    def test_decrease_consumes_stock(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment
        record_inflow(self.item, self.eb, None, None, Decimal('20'), Decimal('4'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = StockAdjustment.objects.create(tanggal='2026-02-02', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item, qty=Decimal('-5'))
        process_adjustment(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('15'))
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ProcessAdjustmentTests -v 2 --keepdb`
Expected: FAIL (module services tidak ada).

- [ ] **Step 3: Implementasi service**

Create `apps/inventory/services.py`:

```python
"""Inventory transaction services Fase 6 — movement + jurnal balance-checked."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from . import ledger
from .models import StockAdjustment


def _next_nomor_jurnal(prefix: str) -> str:
    last = (JurnalHeader.objects.filter(nomor_transaksi__startswith=prefix)
            .order_by('-nomor_transaksi').values_list('nomor_transaksi', flat=True).first())
    try:
        seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
    except (ValueError, IndexError):
        seq = 1
    return f'{prefix}{seq:03d}'


def _post_journal(tanggal, prefix, uraian, entitas_bisnis, lines):
    """lines = [(akun, debit, kredit), ...]. Balance-checked, satu JurnalHeader."""
    total_d = sum((d for _, d, _ in lines), Decimal('0'))
    total_k = sum((k for _, _, k in lines), Decimal('0'))
    if total_d != total_k:
        raise ValueError(f'Jurnal tidak balance: debit {total_d} != kredit {total_k}.')
    header = JurnalHeader.objects.create(
        tanggal=tanggal, nomor_transaksi=_next_nomor_jurnal(prefix),
        uraian_transaksi=uraian, entitas_bisnis=entitas_bisnis, is_penyesuaian=True,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
        for akun, d, k in lines
    ])
    return header


@transaction.atomic
def process_adjustment(adj: StockAdjustment) -> JurnalHeader:
    """Posting adjustment: tiap item + qty → inflow, - qty → consume; satu jurnal."""
    if adj.status == 'posted':
        raise ValueError('Adjustment sudah diposting.')
    items = list(adj.items.select_related('item').all())
    if not items:
        raise ValueError('Adjustment tanpa item.')
    if not adj.akun_selisih_id:
        raise ValueError('Akun selisih wajib dipilih.')

    naik = Decimal('0')   # total nilai persediaan bertambah
    turun = Decimal('0')  # total nilai persediaan berkurang
    for d in items:
        akun_persediaan = d.item.coa_account
        if akun_persediaan is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account (persediaan).')
        if d.qty > 0:
            mv = ledger.record_inflow(
                d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2, adj.entitas_bisnis_lv3,
                d.qty, d.unit_cost, adj.tanggal, 'adjustment_in', source=adj,
                warehouse=adj.warehouse,
            )
            naik += d.qty * d.unit_cost
        elif d.qty < 0:
            result = ledger.consume_stock(
                d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2, adj.entitas_bisnis_lv3,
                -d.qty, adj.tanggal, 'adjustment_out', source=adj,
                metode=d.item.metode_biaya_persediaan, warehouse=adj.warehouse,
            )
            mv = result.out_movement
            turun += result.total_cost
        else:
            continue
        d.movement = mv
        d.save(update_fields=['movement'])

    lines = []
    akun_persediaan = items[0].item.coa_account  # asumsi 1 akun persediaan per dokumen
    if naik > 0:
        lines.append((akun_persediaan, naik, Decimal('0')))
        lines.append((adj.akun_selisih, Decimal('0'), naik))
    if turun > 0:
        lines.append((adj.akun_selisih, turun, Decimal('0')))
        lines.append((akun_persediaan, Decimal('0'), turun))

    header = _post_journal(adj.tanggal, 'TRX-ADJ-',
                           f'Penyesuaian Stok {adj.nomor}', adj.entitas_bisnis, lines)
    adj.jurnal_header = header
    adj.status = 'posted'
    adj.save(update_fields=['jurnal_header', 'status'])
    return header
```

> Catatan desain: bila satu dokumen memuat item dengan `coa_account` persediaan berbeda, jurnal harus dipecah per akun persediaan. Untuk v1 dokumen diasumsikan satu gudang/kelompok akun; validasi ini ditambahkan di Task 1.3 (form) dengan membatasi satu akun persediaan per dokumen, atau iterasi per item. Jika perlu multi-akun, ganti akumulasi `naik/turun` menjadi dict per `akun_persediaan`.

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ProcessAdjustmentTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/services.py apps/inventory/tests_fase6.py
git commit -m "feat(inventory): service posting Stock Adjustment"
```

### Task 1.3: Reversal adjustment

**Files:**
- Modify: `apps/inventory/services.py`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
class ReverseAdjustmentTests(ProcessAdjustmentTests):
    def test_reverse_restores_stock_and_removes_journal(self):
        from apps.inventory.services import process_adjustment, reverse_adjustment
        from apps.inventory.ledger import get_available_stock
        from apps.jurnal.models import JurnalHeader
        h = self._header()  # +10
        header = process_adjustment(h)
        reverse_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('0'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header.pk).exists())
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ReverseAdjustmentTests -v 2 --keepdb`
Expected: FAIL (reverse_adjustment tidak ada).

- [ ] **Step 3: Implementasi reversal**

Tambah di `apps/inventory/services.py`:

```python
def _reverse_journal(header, request=None):
    if header is None:
        return
    from apps.jurnal.utils import log_jurnal_terhapus
    log_jurnal_terhapus(header, 'inventory', request)
    header.details.all().delete()
    header.delete()


@transaction.atomic
def reverse_adjustment(adj: StockAdjustment, request=None) -> None:
    """Batalkan posting: pulihkan layer (inflow) & konsumsi (outflow), hapus jurnal."""
    if adj.status != 'posted':
        raise ValueError('Adjustment belum diposting.')
    # outflow (adjustment_out) → pulihkan layer yang dikonsumsi
    ledger.reverse_movements(adj)
    # inflow (adjustment_in) → hapus layer (ProtectedError bila sudah dikonsumsi)
    ledger.reverse_inflow_movements(adj)
    _reverse_journal(adj.jurnal_header, request)
    adj.items.update(movement=None)
    adj.jurnal_header = None
    adj.status = 'draft'
    adj.save(update_fields=['jurnal_header', 'status'])
```

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.ReverseAdjustmentTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/services.py apps/inventory/tests_fase6.py
git commit -m "feat(inventory): reversal Stock Adjustment"
```

### Task 1.4: Form + formset adjustment

**Files:**
- Create/Modify: `apps/inventory/forms.py`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
class AdjustmentFormTests(TestCase):
    def test_form_fields(self):
        from apps.inventory.forms import StockAdjustmentForm
        f = StockAdjustmentForm()
        for name in ('tanggal', 'entitas_bisnis', 'warehouse', 'akun_selisih', 'keterangan'):
            self.assertIn(name, f.fields)
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.AdjustmentFormTests -v 2 --keepdb`
Expected: FAIL.

- [ ] **Step 3: Implementasi form**

Di `apps/inventory/forms.py` (buat bila belum ada, ikuti pola `apps/aset_tetap/forms.py` untuk widget `ni-input`):

```python
from django import forms
from django.forms import inlineformset_factory

from .models import StockAdjustment, StockAdjustmentItem


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ('tanggal', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }


StockAdjustmentItemFormSet = inlineformset_factory(
    StockAdjustment, StockAdjustmentItem,
    fields=('item', 'qty', 'unit_cost'), extra=1, can_delete=True,
    widgets={
        'item': forms.Select(attrs={'class': 'ni-input'}),
        'qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        'unit_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
    },
)
```

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.AdjustmentFormTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/forms.py apps/inventory/tests_fase6.py
git commit -m "feat(inventory): form StockAdjustment"
```

### Task 1.5: Views + URLs + template adjustment

**Files:**
- Modify (append): `apps/inventory/views.py` (sudah ada — banyak view existing), `apps/inventory/urls.py` (sudah ada, `app_name = 'inventory'`, sudah di-`include` di `naveda_integra/urls.py:20` — **hanya tambah path baru**, jangan buat file/wiring baru)
- Create: `templates/inventory/adjustment_list.html`, `adjustment_form.html`, `adjustment_delete_confirm.html`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class AdjustmentViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(username='u', password='p')
        self.client.force_login(self.user)

    def test_list_renders(self):
        resp = self.client.get(reverse('inventory:adjustment_list'))
        self.assertEqual(resp.status_code, 200)

    def test_create_get_renders(self):
        resp = self.client.get(reverse('inventory:adjustment_create'))
        self.assertEqual(resp.status_code, 200)
```

> Verifikasi nama namespace URL app inventory (`app_name = 'inventory'`) sudah ada di `apps/inventory/urls.py`; bila file belum ada, buat dengan `app_name = 'inventory'`.

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.AdjustmentViewTests -v 2 --keepdb`
Expected: FAIL (NoReverseMatch).

- [ ] **Step 3: Implementasi views**

Tambahkan di `apps/inventory/views.py` (file sudah ada dengan view existing; tambah import bila belum ada di puncak file, lalu append fungsi. Ikuti pola `apps/aset_tetap/views.py`: `@login_required`, `render`, `redirect`, `messages`):

```python
# --- tambah di bagian import (bila belum ada) ---
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import StockAdjustmentForm, StockAdjustmentItemFormSet
from .services import process_adjustment, reverse_adjustment
# StockAdjustment di-import bersama model inventory existing

# --- append fungsi ---
@login_required
def adjustment_list(request):
    rows = StockAdjustment.objects.select_related(
        'entitas_bisnis', 'warehouse', 'akun_selisih').all()
    return render(request, 'inventory/adjustment_list.html', {'rows': rows})


@login_required
def adjustment_create(request):
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            adj = form.save()
            formset.instance = adj
            formset.save()
            try:
                header = process_adjustment(adj)
            except ValueError as e:
                adj.delete()
                messages.error(request, str(e))
                return redirect('inventory:adjustment_create')
            messages.success(request, f'Adjustment {adj.nomor} diposting. Jurnal {header.nomor_transaksi}.')
            return redirect('inventory:adjustment_list')
    else:
        form = StockAdjustmentForm()
        formset = StockAdjustmentItemFormSet()
    return render(request, 'inventory/adjustment_form.html', {'form': form, 'formset': formset})


@login_required
def adjustment_delete(request, pk):
    adj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            reverse_adjustment(adj, request)
            adj.delete()
            messages.success(request, f'Adjustment {adj.nomor} dibatalkan.')
        except Exception as e:
            messages.error(request, f'Gagal membatalkan: {e}')
        return redirect('inventory:adjustment_list')
    return render(request, 'inventory/adjustment_delete_confirm.html', {'adj': adj})
```

- [ ] **Step 4: Implementasi URLs**

`apps/inventory/urls.py` sudah ada (`app_name = 'inventory'`, sudah di-`include`). **Tambahkan** 3 path ke dalam `urlpatterns` yang sudah ada (jangan buat ulang file):

```python
    path('adjustment/', views.adjustment_list, name='adjustment_list'),
    path('adjustment/create/', views.adjustment_create, name='adjustment_create'),
    path('adjustment/<int:pk>/delete/', views.adjustment_delete, name='adjustment_delete'),
```

- [ ] **Step 5: Buat template**

Create `templates/inventory/adjustment_list.html`, `adjustment_form.html`, `adjustment_delete_confirm.html` mengikuti struktur `templates/aset_tetap/aset_tetap_list.html` dan `disposal_delete_confirm.html` (extend base yang sama, kelas `ni-*`). Minimal `adjustment_form.html`:

```html
{% extends "base.html" %}
{% block content %}
<h2 class="ni-page-title">Stock Adjustment Baru</h2>
<form method="post">
  {% csrf_token %}
  <div class="ni-card">{{ form.as_p }}</div>
  <h3>Item</h3>
  {{ formset.management_form }}
  <table class="ni-table">
    {% for f in formset %}
    <tr>{{ f.item }} {{ f.qty }} {{ f.unit_cost }} {{ f.DELETE }}</tr>
    {% endfor %}
  </table>
  <button type="submit" class="ni-btn ni-btn--primary"
          onclick="return confirm('Proses & posting adjustment ini?')">Proses</button>
</form>
{% endblock %}
```

> Verifikasi nama base template (`base.html` atau lainnya) dari `templates/aset_tetap/aset_tetap_list.html` baris `{% extends %}` dan samakan.

- [ ] **Step 6: Jalankan test — pastikan lulus**

Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.AdjustmentViewTests -v 2 --keepdb`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/views.py apps/inventory/urls.py templates/inventory
git commit -m "feat(inventory): UI Stock Adjustment (list/create/batal)"
```

---

## FASE 2 — Stock Opname

### Task 2.1: Model StockOpname + StockOpnameItem

**Files:**
- Modify: `apps/inventory/models.py`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
class StockOpnameModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.akun = Akun.objects.create(kode_akun='5.9.2', nama='Selisih Opname')

    def test_selisih_autocompute(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.akun)
        d = StockOpnameItem.objects.create(opname=h, item=self.item,
                                           qty_sistem=Decimal('10'), qty_fisik=Decimal('8'),
                                           unit_cost=Decimal('5'))
        self.assertEqual(d.selisih, Decimal('-2'))
        self.assertTrue(h.nomor.startswith('TRX-OPN-'))
```

- [ ] **Step 2: Jalankan — gagal.** Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.StockOpnameModelTests -v 2 --keepdb` → FAIL.

- [ ] **Step 3: Tambah model**

Di `apps/inventory/models.py`:

```python
class StockOpname(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-OPN-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='stock_opnames')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames')
    akun_selisih = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='stock_opnames')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockOpnameItem(models.Model):
    opname = models.ForeignKey(StockOpname, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty_sistem = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    qty_fisik = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    selisih = models.DecimalField(max_digits=15, decimal_places=4, default=0, editable=False)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def save(self, *args, **kwargs):
        self.selisih = (self.qty_fisik or 0) - (self.qty_sistem or 0)
        super().save(*args, **kwargs)
```

- [ ] **Step 4: Migrasi & test.** Run: `env/Scripts/python.exe manage.py makemigrations inventory && env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.StockOpnameModelTests -v 2 --keepdb` → PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/models.py apps/inventory/migrations apps/inventory/tests_fase6.py
git commit -m "feat(inventory): model StockOpname"
```

### Task 2.2: Service posting opname

**Files:**
- Modify: `apps/inventory/services.py`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test yang gagal**

```python
class ProcessOpnameTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.selisih = Akun.objects.create(kode_akun='5.9.2', nama='Selisih Opname')

    def test_posting_minus_consumes_and_balances(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=h, item=self.item, qty_sistem=Decimal('10'),
                                       qty_fisik=Decimal('8'), unit_cost=Decimal('5'))
        header = process_opname(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('8'))
        self.assertEqual(sum(d.debit for d in header.details.all()),
                         sum(d.kredit for d in header.details.all()))

    def test_zero_selisih_no_movement(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=h, item=self.item, qty_sistem=Decimal('5'),
                                       qty_fisik=Decimal('5'), unit_cost=Decimal('5'))
        header = process_opname(h)
        self.assertIsNone(header)  # tidak ada selisih → tidak ada jurnal
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Implementasi**

Tambah di `apps/inventory/services.py`:

```python
from .models import StockOpname


@transaction.atomic
def process_opname(opn: StockOpname):
    """Posting selisih opname. Kembalikan JurnalHeader atau None bila semua selisih 0."""
    if opn.status == 'posted':
        raise ValueError('Opname sudah diposting.')
    items = list(opn.items.select_related('item').all())
    naik = Decimal('0')
    turun = Decimal('0')
    akun_persediaan = None
    for d in items:
        if d.selisih == 0:
            continue
        if d.item.coa_account is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        akun_persediaan = d.item.coa_account
        if d.selisih > 0:
            mv = ledger.record_inflow(
                d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2, opn.entitas_bisnis_lv3,
                d.selisih, d.unit_cost, opn.tanggal, 'opname_in', source=opn,
                warehouse=opn.warehouse)
            naik += d.selisih * d.unit_cost
        else:
            result = ledger.consume_stock(
                d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2, opn.entitas_bisnis_lv3,
                -d.selisih, opn.tanggal, 'opname_out', source=opn,
                metode=d.item.metode_biaya_persediaan, warehouse=opn.warehouse)
            mv = result.out_movement
            turun += result.total_cost
        d.movement = mv
        d.save(update_fields=['movement'])

    header = None
    if naik > 0 or turun > 0:
        lines = []
        if naik > 0:
            lines.append((akun_persediaan, naik, Decimal('0')))
            lines.append((opn.akun_selisih, Decimal('0'), naik))
        if turun > 0:
            lines.append((opn.akun_selisih, turun, Decimal('0')))
            lines.append((akun_persediaan, Decimal('0'), turun))
        header = _post_journal(opn.tanggal, 'TRX-OPN-',
                               f'Opname Stok {opn.nomor}', opn.entitas_bisnis, lines)
        opn.jurnal_header = header
    opn.status = 'posted'
    opn.save(update_fields=['jurnal_header', 'status'])
    return header


@transaction.atomic
def reverse_opname(opn: StockOpname, request=None) -> None:
    if opn.status != 'posted':
        raise ValueError('Opname belum diposting.')
    ledger.reverse_movements(opn)
    ledger.reverse_inflow_movements(opn)
    _reverse_journal(opn.jurnal_header, request)
    opn.items.update(movement=None)
    opn.jurnal_header = None
    opn.status = 'draft'
    opn.save(update_fields=['jurnal_header', 'status'])
```

- [ ] **Step 4: Jalankan — lulus.** → PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/services.py apps/inventory/tests_fase6.py
git commit -m "feat(inventory): service posting & reversal Stock Opname"
```

### Task 2.3: Form + Views + URLs + template opname

**Files:**
- Modify: `apps/inventory/forms.py`, `views.py`, `urls.py`
- Create: `templates/inventory/opname_*.html`
- Test: `apps/inventory/tests_fase6.py`

- [ ] **Step 1: Tulis test view yang gagal**

```python
class OpnameViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u2', password='p')
        self.client.force_login(self.user)

    def test_list_and_create_render(self):
        self.assertEqual(self.client.get(reverse('inventory:opname_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:opname_create')).status_code, 200)
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL (NoReverseMatch).

- [ ] **Step 3: Form** — tambah di `apps/inventory/forms.py`, pola identik Task 1.4 tapi model `StockOpname` (fields header sama) dan formset `StockOpnameItem` fields `('item', 'qty_sistem', 'qty_fisik', 'unit_cost')`.

```python
from .models import StockOpname, StockOpnameItem


class StockOpnameForm(forms.ModelForm):
    class Meta:
        model = StockOpname
        fields = ('tanggal', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }


StockOpnameItemFormSet = inlineformset_factory(
    StockOpname, StockOpnameItem,
    fields=('item', 'qty_sistem', 'qty_fisik', 'unit_cost'), extra=1, can_delete=True,
    widgets={
        'item': forms.Select(attrs={'class': 'ni-input'}),
        'qty_sistem': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        'qty_fisik': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        'unit_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
    },
)
```

- [ ] **Step 4: Views + URLs** — tambah di `views.py` fungsi `opname_list`, `opname_create`, `opname_delete` identik pola Task 1.5 (ganti model/form/service ke opname; `process_opname`/`reverse_opname`). Tambah 3 path di `urls.py`:

```python
    path('opname/', views.opname_list, name='opname_list'),
    path('opname/create/', views.opname_create, name='opname_create'),
    path('opname/<int:pk>/delete/', views.opname_delete, name='opname_delete'),
```

Views:

```python
from .forms import StockOpnameForm, StockOpnameItemFormSet
from .models import StockOpname
from .services import process_opname, reverse_opname


@login_required
def opname_list(request):
    rows = StockOpname.objects.select_related('entitas_bisnis', 'warehouse').all()
    return render(request, 'inventory/opname_list.html', {'rows': rows})


@login_required
def opname_create(request):
    if request.method == 'POST':
        form = StockOpnameForm(request.POST)
        formset = StockOpnameItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            opn = form.save()
            formset.instance = opn
            formset.save()
            try:
                header = process_opname(opn)
            except ValueError as e:
                opn.delete()
                messages.error(request, str(e))
                return redirect('inventory:opname_create')
            msg = f'Opname {opn.nomor} diposting.'
            if header:
                msg += f' Jurnal {header.nomor_transaksi}.'
            messages.success(request, msg)
            return redirect('inventory:opname_list')
    else:
        form = StockOpnameForm()
        formset = StockOpnameItemFormSet()
    return render(request, 'inventory/opname_form.html', {'form': form, 'formset': formset})


@login_required
def opname_delete(request, pk):
    opn = get_object_or_404(StockOpname, pk=pk)
    if request.method == 'POST':
        try:
            reverse_opname(opn, request)
            opn.delete()
            messages.success(request, f'Opname {opn.nomor} dibatalkan.')
        except Exception as e:
            messages.error(request, f'Gagal: {e}')
        return redirect('inventory:opname_list')
    return render(request, 'inventory/opname_delete_confirm.html', {'opn': opn})
```

- [ ] **Step 5: Templates** — `templates/inventory/opname_list.html`, `opname_form.html`, `opname_delete_confirm.html` mengikuti pola template adjustment (Task 1.5 Step 5). Form opname menampilkan kolom `qty_sistem`, `qty_fisik`, `unit_cost`.

- [ ] **Step 6: Jalankan — lulus.** Run: `env/Scripts/python.exe manage.py test apps.inventory.tests_fase6.OpnameViewTests -v 2 --keepdb` → PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/forms.py apps/inventory/views.py apps/inventory/urls.py templates/inventory apps/inventory/tests_fase6.py
git commit -m "feat(inventory): UI Stock Opname"
```

---

## FASE 3 — Transfer antar Gudang/Cabang

### Task 3.1: Model StockTransfer + StockTransferItem

**Files:** Modify `apps/inventory/models.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class StockTransferModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_transfer(self):
        from apps.inventory.models import StockTransfer, StockTransferItem
        h = StockTransfer.objects.create(
            tanggal='2026-04-01', eb_asal=self.eb, warehouse_asal=self.wh1,
            eb_tujuan=self.eb, warehouse_tujuan=self.wh2)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('5'))
        self.assertTrue(h.nomor.startswith('TRX-TRF-'))
        self.assertFalse(h.is_cross_entity)
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Tambah model**

```python
class StockTransfer(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-TRF-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    eb_asal = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='transfers_asal')
    eb_asal_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_asal_lv2')
    eb_asal_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_asal_lv3')
    warehouse_asal = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='transfers_out')
    eb_tujuan = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='transfers_tujuan')
    eb_tujuan_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_tujuan_lv2')
    eb_tujuan_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_tujuan_lv3')
    warehouse_tujuan = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='transfers_in')
    akun_perantara = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers', help_text='Wajib bila lintas entitas (EB lv1 berbeda).')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header_asal = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    jurnal_header_tujuan = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    @property
    def is_cross_entity(self):
        return self.eb_asal_id != self.eb_tujuan_id

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement_out = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    movement_in = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
```

- [ ] **Step 4: Migrasi & test** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): model StockTransfer"`

### Task 3.2: Service posting transfer (intra & lintas entitas)

**Files:** Modify `apps/inventory/services.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ProcessTransferTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        self.wh3 = Warehouse.objects.create(entitas_bisnis=self.eb2, nama='G3')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.perantara = Akun.objects.create(kode_akun='1.1.9', nama='Perantara Transfer')

    def test_intra_entity_moves_stock_no_journal(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-01', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb,
                                         warehouse_tujuan=self.wh2)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh1), Decimal('6'))
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh2), Decimal('4'))
        self.assertIsNone(h.jurnal_header_asal)

    def test_cross_entity_creates_two_balanced_journals(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-01', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb2,
                                         warehouse_tujuan=self.wh3, akun_perantara=self.perantara)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        h.refresh_from_db()
        self.assertEqual(get_available_stock(self.item, self.eb2, warehouse=self.wh3), Decimal('4'))
        for hdr in (h.jurnal_header_asal, h.jurnal_header_tujuan):
            self.assertIsNotNone(hdr)
            self.assertEqual(sum(d.debit for d in hdr.details.all()),
                             sum(d.kredit for d in hdr.details.all()))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Implementasi**

Tambah di `apps/inventory/services.py`:

```python
from .models import StockTransfer


@transaction.atomic
def process_transfer(trf: StockTransfer) -> None:
    if trf.status == 'posted':
        raise ValueError('Transfer sudah diposting.')
    if trf.is_cross_entity and not trf.akun_perantara_id:
        raise ValueError('Transfer lintas entitas wajib mengisi Akun Perantara.')
    items = list(trf.items.select_related('item').all())
    if not items:
        raise ValueError('Transfer tanpa item.')

    total_value = Decimal('0')
    akun_persediaan = None
    for d in items:
        if d.item.coa_account is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        akun_persediaan = d.item.coa_account
        result = ledger.consume_stock(
            d.item, trf.eb_asal, trf.eb_asal_lv2, trf.eb_asal_lv3, d.qty,
            trf.tanggal, 'transfer_out', source=trf,
            metode=d.item.metode_biaya_persediaan, warehouse=trf.warehouse_asal)
        unit_cost = (result.total_cost / d.qty) if d.qty else Decimal('0')
        mv_in = ledger.record_inflow(
            d.item, trf.eb_tujuan, trf.eb_tujuan_lv2, trf.eb_tujuan_lv3, d.qty,
            unit_cost, trf.tanggal, 'transfer_in', source=trf,
            warehouse=trf.warehouse_tujuan)
        d.unit_cost = unit_cost
        d.movement_out = result.out_movement
        d.movement_in = mv_in
        d.save(update_fields=['unit_cost', 'movement_out', 'movement_in'])
        total_value += result.total_cost

    if trf.is_cross_entity and total_value > 0:
        # Jurnal sisi asal: barang keluar dari EB asal
        trf.jurnal_header_asal = _post_journal(
            trf.tanggal, 'TRX-TRF-', f'Transfer Keluar {trf.nomor}', trf.eb_asal,
            [(trf.akun_perantara, total_value, Decimal('0')),
             (akun_persediaan, Decimal('0'), total_value)])
        # Jurnal sisi tujuan: barang masuk ke EB tujuan
        trf.jurnal_header_tujuan = _post_journal(
            trf.tanggal, 'TRX-TRF-', f'Transfer Masuk {trf.nomor}', trf.eb_tujuan,
            [(akun_persediaan, total_value, Decimal('0')),
             (trf.akun_perantara, Decimal('0'), total_value)])
    trf.status = 'posted'
    trf.save(update_fields=['jurnal_header_asal', 'jurnal_header_tujuan', 'status'])


@transaction.atomic
def reverse_transfer(trf: StockTransfer, request=None) -> None:
    if trf.status != 'posted':
        raise ValueError('Transfer belum diposting.')
    ledger.reverse_movements(trf)          # hapus transfer_out, pulihkan layer asal
    ledger.reverse_inflow_movements(trf)   # hapus transfer_in
    _reverse_journal(trf.jurnal_header_asal, request)
    _reverse_journal(trf.jurnal_header_tujuan, request)
    trf.items.update(movement_out=None, movement_in=None)
    trf.jurnal_header_asal = None
    trf.jurnal_header_tujuan = None
    trf.status = 'draft'
    trf.save(update_fields=['jurnal_header_asal', 'jurnal_header_tujuan', 'status'])
```

- [ ] **Step 4: Jalankan — lulus.** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): service posting & reversal Transfer"`

### Task 3.3: Form + Views + URLs + template transfer

**Files:** Modify `forms.py`, `views.py`, `urls.py`; Create `templates/inventory/transfer_*.html`; Test.

- [ ] **Step 1: Test view gagal** — pola identik Task 2.3 Step 1, reverse `inventory:transfer_list` & `inventory:transfer_create`.

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Form** — `StockTransferForm` (fields: `tanggal, eb_asal, eb_asal_lv2, eb_asal_lv3, warehouse_asal, eb_tujuan, eb_tujuan_lv2, eb_tujuan_lv3, warehouse_tujuan, akun_perantara, keterangan`, semua widget `ni-input`) + `StockTransferItemFormSet` fields `('item', 'qty')`, pola inlineformset seperti Task 1.4.

- [ ] **Step 4: Views + URLs** — `transfer_list/create/delete` pola Task 2.3 Step 4 (service `process_transfer`/`reverse_transfer`; `transfer_create` menampilkan pesan sukses tanpa asumsi satu jurnal). Path:

```python
    path('transfer/', views.transfer_list, name='transfer_list'),
    path('transfer/create/', views.transfer_create, name='transfer_create'),
    path('transfer/<int:pk>/delete/', views.transfer_delete, name='transfer_delete'),
```

- [ ] **Step 5: Templates** — `transfer_list/form/delete_confirm.html` pola adjustment. Form menampilkan blok asal (EB+gudang) dan tujuan (EB+gudang) + `akun_perantara`.

- [ ] **Step 6: Jalankan — lulus.** → PASS.

- [ ] **Step 7: Commit** `git commit -m "feat(inventory): UI Transfer stok"`

---

## FASE 4 — Retur Pelanggan & Retur Supplier

> **Prasyarat verifikasi:** sebelum Task 4.1, konfirmasi struktur `SalesHeader`→`SalesEntitasGroup`→`SalesItem` dan `PurchaseHeader`→`PurchaseItem` (nama related_name, field `warehouse`, `entitas_bisnis` per grup) dengan membaca `apps/sales/models.py` dan `apps/purchase/models.py`. Sesuaikan FK & pengambilan akun/harga di service sesuai temuan.

### Task 4.1: Model ReturCustomer + ReturCustomerItem

**Files:** Modify `apps/inventory/models.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ReturCustomerModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_header(self):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturCustomerItem.objects.create(retur=h, item=self.item, qty=Decimal('2'),
                                         unit_cost=Decimal('5'), harga_jual=Decimal('9'))
        self.assertTrue(h.nomor.startswith('TRX-RTC-'))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Tambah model** (di `apps/inventory/models.py`):

```python
class ReturCustomer(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-RTC-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    sales_header = models.ForeignKey('sales.SalesHeader', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers')
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='retur_customers')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class ReturCustomerItem(models.Model):
    retur = models.ForeignKey(ReturCustomer, on_delete=models.CASCADE, related_name='items')
    sales_item = models.ForeignKey('sales.SalesItem', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0, help_text='Biaya HPP asli')
    harga_jual = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
```

- [ ] **Step 4: Migrasi & test** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): model ReturCustomer"`

### Task 4.2: Model ReturSupplier + ReturSupplierItem

**Files:** Modify `apps/inventory/models.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ReturSupplierModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_header(self):
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        self.assertTrue(h.nomor.startswith('TRX-RTS-'))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Tambah model** — struktur identik `ReturCustomer` tetapi:
  - `NOMOR_PREFIX = 'TRX-RTS-'`, related_name `retur_suppliers*`.
  - Ganti `sales_header` → `purchase_header = models.ForeignKey('purchase.PurchaseHeader', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers')`.
  - `ReturSupplierItem` punya `purchase_item = models.ForeignKey('purchase.PurchaseItem', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_items')`, `item`, `qty`, `movement` (tanpa `harga_jual`; `unit_cost` diisi dari `consume_stock`).

```python
class ReturSupplier(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-RTS-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    purchase_header = models.ForeignKey('purchase.PurchaseHeader', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers')
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='retur_suppliers')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers')
    akun_lawan = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_suppliers', help_text='Hutang/Kas yang dikreditkan balik')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class ReturSupplierItem(models.Model):
    retur = models.ForeignKey(ReturSupplier, on_delete=models.CASCADE, related_name='items')
    purchase_item = models.ForeignKey('purchase.PurchaseItem', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
```

> Untuk retur pelanggan akun diambil dari `sales_item` asal (revenue/offset/payment). Untuk retur supplier akun lawan (`akun_lawan`) dipilih user (hutang/kas) karena mapping akun pembelian bervariasi; akun persediaan tetap `item.coa_account`.

- [ ] **Step 4: Migrasi & test** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): model ReturSupplier"`

### Task 4.3: Service retur pelanggan

**Files:** Modify `apps/inventory/services.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ProcessReturCustomerTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        self.pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        self.piutang = Akun.objects.create(kode_akun='1.1.2', nama='Piutang')

    def test_customer_return_restores_stock_and_two_journal_pairs(self):
        from apps.inventory.ledger import get_available_stock
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        d = ReturCustomerItem.objects.create(
            retur=h, item=self.item, qty=Decimal('2'), unit_cost=Decimal('5'),
            harga_jual=Decimal('9'))
        # akun retur diberikan langsung (tanpa sales_item) untuk unit test service
        header = process_retur_customer(h, akun_pendapatan=self.pendapatan,
                                        akun_piutang=self.piutang, akun_hpp=self.hpp)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('2'))
        deb = sum(x.debit for x in header.details.all())
        kre = sum(x.kredit for x in header.details.all())
        self.assertEqual(deb, kre)
        # pendapatan 2*9=18 + HPP 2*5=10 di masing-masing sisi
        self.assertEqual(deb, Decimal('28'))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Implementasi**

Tambah di `apps/inventory/services.py`:

```python
from .models import ReturCustomer


@transaction.atomic
def process_retur_customer(rtc: ReturCustomer, akun_pendapatan=None,
                           akun_piutang=None, akun_hpp=None) -> JurnalHeader:
    """Retur pelanggan: barang masuk (inflow biaya HPP asli) + balik pendapatan & HPP.

    Bila item punya sales_item asal, akun diambil dari sana; parameter akun
    hanya dipakai bila sales_item kosong (mis. unit test / retur manual).
    """
    if rtc.status == 'posted':
        raise ValueError('Retur sudah diposting.')
    items = list(rtc.items.select_related('item', 'sales_item').all())
    if not items:
        raise ValueError('Retur tanpa item.')

    total_pendapatan = Decimal('0')
    total_hpp = Decimal('0')
    ap = api = ahpp = None
    akun_persediaan = None
    for d in items:
        akun_persediaan = d.item.coa_account
        if akun_persediaan is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        si = d.sales_item
        ap = (si.revenue_account if si else None) or akun_pendapatan
        api = (si.payment_account if si else None) or akun_piutang
        ahpp = (si.offset_coa_account if si else None) or akun_hpp
        mv = ledger.record_inflow(
            d.item, rtc.entitas_bisnis, rtc.entitas_bisnis_lv2, rtc.entitas_bisnis_lv3,
            d.qty, d.unit_cost, rtc.tanggal, 'return_customer', source=rtc,
            warehouse=rtc.warehouse)
        d.movement = mv
        d.save(update_fields=['movement'])
        total_pendapatan += d.qty * d.harga_jual
        total_hpp += d.qty * d.unit_cost

    if not (ap and api and ahpp):
        raise ValueError('Akun pendapatan/piutang/HPP retur tidak lengkap.')
    lines = [
        (ap, total_pendapatan, Decimal('0')),          # D Pendapatan (balik)
        (api, Decimal('0'), total_pendapatan),         # K Piutang/Kas
        (akun_persediaan, total_hpp, Decimal('0')),    # D Persediaan (balik HPP)
        (ahpp, Decimal('0'), total_hpp),               # K HPP
    ]
    header = _post_journal(rtc.tanggal, 'TRX-RTC-',
                           f'Retur Pelanggan {rtc.nomor}', rtc.entitas_bisnis, lines)
    rtc.jurnal_header = header
    rtc.status = 'posted'
    rtc.save(update_fields=['jurnal_header', 'status'])
    return header


@transaction.atomic
def reverse_retur_customer(rtc: ReturCustomer, request=None) -> None:
    if rtc.status != 'posted':
        raise ValueError('Retur belum diposting.')
    ledger.reverse_inflow_movements(rtc)  # hapus layer return_customer
    _reverse_journal(rtc.jurnal_header, request)
    rtc.items.update(movement=None)
    rtc.jurnal_header = None
    rtc.status = 'draft'
    rtc.save(update_fields=['jurnal_header', 'status'])
```

- [ ] **Step 4: Jalankan — lulus.** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): service retur pelanggan"`

### Task 4.4: Service retur supplier

**Files:** Modify `apps/inventory/services.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ProcessReturSupplierTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.hutang = Akun.objects.create(kode_akun='2.1.1', nama='Hutang Usaha')

    def test_supplier_return_consumes_and_balances(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        from apps.inventory.services import process_retur_supplier
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_lawan=self.hutang)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        header = process_retur_supplier(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('7'))
        self.assertEqual(sum(x.debit for x in header.details.all()),
                         sum(x.kredit for x in header.details.all()))
        self.assertEqual(sum(x.debit for x in header.details.all()), Decimal('15'))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Implementasi**

Tambah di `apps/inventory/services.py`:

```python
from .models import ReturSupplier


@transaction.atomic
def process_retur_supplier(rts: ReturSupplier, request=None) -> JurnalHeader:
    """Retur supplier: barang keluar (consume via metode) + K Persediaan / D Hutang-Kas."""
    if rts.status == 'posted':
        raise ValueError('Retur sudah diposting.')
    if not rts.akun_lawan_id:
        raise ValueError('Akun lawan (Hutang/Kas) wajib dipilih.')
    items = list(rts.items.select_related('item').all())
    if not items:
        raise ValueError('Retur tanpa item.')

    total_value = Decimal('0')
    akun_persediaan = None
    for d in items:
        akun_persediaan = d.item.coa_account
        if akun_persediaan is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        result = ledger.consume_stock(
            d.item, rts.entitas_bisnis, rts.entitas_bisnis_lv2, rts.entitas_bisnis_lv3,
            d.qty, rts.tanggal, 'return_supplier', source=rts,
            metode=d.item.metode_biaya_persediaan, warehouse=rts.warehouse)
        d.unit_cost = (result.total_cost / d.qty) if d.qty else Decimal('0')
        d.movement = result.out_movement
        d.save(update_fields=['unit_cost', 'movement'])
        total_value += result.total_cost

    lines = [
        (rts.akun_lawan, total_value, Decimal('0')),      # D Hutang/Kas
        (akun_persediaan, Decimal('0'), total_value),     # K Persediaan
    ]
    header = _post_journal(rts.tanggal, 'TRX-RTS-',
                           f'Retur Supplier {rts.nomor}', rts.entitas_bisnis, lines)
    rts.jurnal_header = header
    rts.status = 'posted'
    rts.save(update_fields=['jurnal_header', 'status'])
    return header


@transaction.atomic
def reverse_retur_supplier(rts: ReturSupplier, request=None) -> None:
    if rts.status != 'posted':
        raise ValueError('Retur belum diposting.')
    ledger.reverse_movements(rts)  # pulihkan layer yang dikonsumsi return_supplier
    _reverse_journal(rts.jurnal_header, request)
    rts.items.update(movement=None)
    rts.jurnal_header = None
    rts.status = 'draft'
    rts.save(update_fields=['jurnal_header', 'status'])
```

- [ ] **Step 4: Jalankan — lulus.** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): service retur supplier"`

### Task 4.5: UI retur pelanggan & supplier

**Files:** Modify `forms.py`, `views.py`, `urls.py`; Create `templates/inventory/retur_*.html`; Test.

- [ ] **Step 1: Test view gagal** — reverse `inventory:retur_customer_list/create` & `inventory:retur_supplier_list/create` (pola Task 2.3 Step 1). → FAIL.

- [ ] **Step 2: Forms** — `ReturCustomerForm` (fields `tanggal, sales_header, entitas_bisnis(+lv2/lv3), warehouse, keterangan`) + formset item `('item', 'qty', 'unit_cost', 'harga_jual')`; `ReturSupplierForm` (fields `tanggal, purchase_header, entitas_bisnis(+lv2/lv3), warehouse, akun_lawan, keterangan`) + formset `('item', 'qty')`. Pola inlineformset seperti Task 1.4.

- [ ] **Step 3: Views + URLs** — 6 view (`retur_customer_list/create/delete`, `retur_supplier_list/create/delete`) pola Task 2.3 Step 4 memakai `process_retur_customer`/`reverse_retur_customer` dan `process_retur_supplier`/`reverse_retur_supplier`. `retur_customer_create` memanggil service tanpa argumen akun tambahan (akun diambil dari `sales_item`; bila header tanpa sales_item, form wajib mengisi akun — tambahkan field opsional `akun_pendapatan/akun_piutang/akun_hpp` pada form bila `sales_header` kosong). Path:

```python
    path('retur-pelanggan/', views.retur_customer_list, name='retur_customer_list'),
    path('retur-pelanggan/create/', views.retur_customer_create, name='retur_customer_create'),
    path('retur-pelanggan/<int:pk>/delete/', views.retur_customer_delete, name='retur_customer_delete'),
    path('retur-supplier/', views.retur_supplier_list, name='retur_supplier_list'),
    path('retur-supplier/create/', views.retur_supplier_create, name='retur_supplier_create'),
    path('retur-supplier/<int:pk>/delete/', views.retur_supplier_delete, name='retur_supplier_delete'),
```

- [ ] **Step 4: Templates** — `retur_customer_*.html` & `retur_supplier_*.html` pola adjustment.

- [ ] **Step 5: Jalankan — lulus.** → PASS.

- [ ] **Step 6: Commit** `git commit -m "feat(inventory): UI retur pelanggan & supplier"`

---

## FASE 5 — Reorder Point / Minimum Stock + Indikator

### Task 5.1: Model ItemReorderSetting

**Files:** Modify `apps/inventory/models.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ReorderSettingTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_unique_item_warehouse(self):
        from django.db import IntegrityError
        from apps.inventory.models import ItemReorderSetting
        ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                          minimum_stock=Decimal('5'), reorder_point=Decimal('10'))
        with self.assertRaises(IntegrityError):
            ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                              minimum_stock=Decimal('3'), reorder_point=Decimal('8'))
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Tambah model**

```python
class ItemReorderSetting(models.Model):
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.CASCADE, related_name='reorder_settings')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.CASCADE, related_name='reorder_settings')
    minimum_stock = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    reorder_point = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    reorder_qty = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    class Meta:
        unique_together = (('item', 'warehouse'),)
        verbose_name = 'Pengaturan Reorder'

    def __str__(self):
        return f'{self.item.item_id} @ {self.warehouse.kode}'
```

- [ ] **Step 4: Migrasi & test** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): model ItemReorderSetting"`

### Task 5.2: Helper indikator status stok

**Files:** Modify `apps/inventory/services.py`; Test `tests_fase6.py`.

- [ ] **Step 1: Tulis test yang gagal**

```python
class ReorderIndicatorTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_status_levels(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import ItemReorderSetting
        from apps.inventory.services import reorder_status
        ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                          minimum_stock=Decimal('5'), reorder_point=Decimal('10'))
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('1'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'critical')  # <=5
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('1'),
                      '2026-01-02', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'warning')   # 8, <=10
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('1'),
                      '2026-01-03', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'ok')        # 18
```

- [ ] **Step 2: Jalankan — gagal.** → FAIL.

- [ ] **Step 3: Implementasi**

Tambah di `apps/inventory/services.py`:

```python
from .models import ItemReorderSetting


def reorder_status(item, eb_lv1, warehouse, eb_lv2=None, eb_lv3=None) -> str:
    """Kembalikan 'critical' (<=minimum), 'warning' (<=reorder_point), atau 'ok'.

    'none' bila belum ada setting untuk (item, warehouse).
    """
    setting = ItemReorderSetting.objects.filter(item=item, warehouse=warehouse).first()
    if setting is None:
        return 'none'
    available = ledger.get_available_stock(item, eb_lv1, eb_lv2, eb_lv3, warehouse=warehouse)
    if available <= setting.minimum_stock:
        return 'critical'
    if available <= setting.reorder_point:
        return 'warning'
    return 'ok'
```

- [ ] **Step 4: Jalankan — lulus.** → PASS.

- [ ] **Step 5: Commit** `git commit -m "feat(inventory): helper indikator reorder"`

### Task 5.3: UI reorder — kelola setting + badge indikator

**Files:** Modify `forms.py`, `views.py`, `urls.py`; Create `templates/inventory/reorder_*.html`; Test.

- [ ] **Step 1: Test view gagal** — reverse `inventory:reorder_list` (200). → FAIL.

- [ ] **Step 2: Form** — `ItemReorderSettingForm` ModelForm fields `('item', 'warehouse', 'minimum_stock', 'reorder_point', 'reorder_qty')`, widget `ni-input`. Boleh formset/CRUD sederhana.

- [ ] **Step 3: Views + URLs** — `reorder_list` (tampilkan tiap setting + `reorder_status` badge), `reorder_create`, `reorder_delete`. Path:

```python
    path('reorder/', views.reorder_list, name='reorder_list'),
    path('reorder/create/', views.reorder_create, name='reorder_create'),
    path('reorder/<int:pk>/delete/', views.reorder_delete, name='reorder_delete'),
```

```python
from .forms import ItemReorderSettingForm
from .models import ItemReorderSetting
from .services import reorder_status


@login_required
def reorder_list(request):
    rows = []
    for s in ItemReorderSetting.objects.select_related('item', 'warehouse', 'warehouse__entitas_bisnis'):
        rows.append({'setting': s,
                     'status': reorder_status(s.item, s.warehouse.entitas_bisnis, s.warehouse)})
    return render(request, 'inventory/reorder_list.html', {'rows': rows})


@login_required
def reorder_create(request):
    if request.method == 'POST':
        form = ItemReorderSettingForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pengaturan reorder disimpan.')
            return redirect('inventory:reorder_list')
    else:
        form = ItemReorderSettingForm()
    return render(request, 'inventory/reorder_form.html', {'form': form})


@login_required
def reorder_delete(request, pk):
    s = get_object_or_404(ItemReorderSetting, pk=pk)
    if request.method == 'POST':
        s.delete()
        messages.success(request, 'Pengaturan reorder dihapus.')
        return redirect('inventory:reorder_list')
    return render(request, 'inventory/reorder_delete_confirm.html', {'setting': s})
```

- [ ] **Step 4: Templates** — `reorder_list.html` menampilkan badge: `critical`→`ni-badge--danger` (merah), `warning`→`ni-badge--warning` (kuning), `ok`→`ni-badge--success`. `reorder_form.html` & `reorder_delete_confirm.html` pola adjustment.

- [ ] **Step 5: Jalankan — lulus.** → PASS.

- [ ] **Step 6: Commit** `git commit -m "feat(inventory): UI reorder point + indikator"`

---

## FASE 6 — Integrasi, Regresi & Navigasi

### Task 6.1: Registrasi admin (opsional tapi disarankan)

**Files:** Modify `apps/inventory/admin.py`.

- [ ] **Step 1:** Daftarkan `StockAdjustment`, `StockOpname`, `StockTransfer`, `ReturCustomer`, `ReturSupplier`, `ItemReorderSetting` ke admin dengan `list_display` ringkas (`nomor`/`item`, `tanggal`/`warehouse`, `status`). Ikuti pola registrasi admin existing di app lain.

- [ ] **Step 2: Commit** `git commit -m "chore(inventory): registrasi admin transaksi Fase 6"`

### Task 6.2: Menu navigasi

**Files:** Modify template navigasi (cari `href` ke `aset_tetap:list` untuk menemukan file menu, mis. `templates/base.html` atau partial sidebar).

- [ ] **Step 1:** Tambah entri menu modul Inventory → sub-menu: Adjustment, Opname, Transfer, Retur Pelanggan, Retur Supplier, Reorder. Gunakan `{% url 'inventory:adjustment_list' %}` dst.

- [ ] **Step 2: Commit** `git commit -m "feat(inventory): menu navigasi transaksi Fase 6"`

### Task 6.3: Regresi penuh & migrasi bersih

- [ ] **Step 1: Cek migrasi konsisten**

Run: `env/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 2: Jalankan seluruh test suite terdampak**

Run: `env/Scripts/python.exe manage.py test apps.inventory apps.sales apps.purchase apps.aset_tetap -v 1 --keepdb`
Expected: semua PASS (tidak ada regresi dari perubahan movement types / penghapusan stub).

- [ ] **Step 3: Commit (bila ada perbaikan)** `git commit -m "test(inventory): regresi Fase 6 hijau"`

---

## Self-Review — Cakupan Spec

| Requirement spec | Task |
|------------------|------|
| Movement types baru + set reversal | 0.1, 0.2 |
| Buang stub MutasiInventory | 0.3 |
| Stock Adjustment (model/service/jurnal/reversal/UI) | 1.1–1.5 |
| Stock Opname (snapshot sistem, fisik, selisih, UI) | 2.1–2.3 |
| Transfer intra & lintas-entitas (2 jurnal) | 3.1–3.3 |
| Retur pelanggan (dokumen asal, balik pendapatan+HPP) | 4.1, 4.3, 4.5 |
| Retur supplier (dokumen asal, K persediaan/D hutang) | 4.2, 4.4, 4.5 |
| Reorder point per item+gudang + indikator | 5.1–5.3 |
| Isolasi EB & kunci warehouse | teruji di 1.2, 2.2, 3.2, 4.3, 4.4 |
| Balance jurnal | teruji di tiap ProcessTests |
| Regresi purchase/sales/POS | 6.3 |
| Navigasi & admin | 6.1, 6.2 |

**Catatan verifikasi saat eksekusi (bukan placeholder — asumsi yang wajib dicek pada file nyata):**
1. Nama field `Akun` (`kode_akun`/`nama_akun`) — cek `apps/master_data/models.py`.
2. Struktur `SalesHeader→SalesEntitasGroup→SalesItem` & field akun (`revenue_account`, `offset_coa_account`, `payment_account`) — cek `apps/sales/models.py` (dikonfirmasi ada di §spec).
3. `PurchaseHeader`/`PurchaseItem` related_name & field — cek `apps/purchase/models.py`.
4. Nama base template & kelas badge (`ni-badge--*`) — cek `templates/aset_tetap/*.html`.
5. `naveda_integra/urls.py` sudah/belum `include('apps.inventory.urls')`.

Setiap asumsi di atas dipakai di kode task terkait; bila temuan berbeda, sesuaikan nama field/FK — logika movement & jurnal tidak berubah.
