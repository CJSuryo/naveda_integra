# Sales Tax Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrasikan modul pajak (`apps.pajak`) ke `apps.sales` via model `SalesTaxLine` (mirror `KPTaxLine` di pendapatan), gantikan inline tax journal dengan `sync_pajak + confirm_pajak`, dan tambah UI multi-tax-lines di form sales.

**Architecture:** `SalesTaxLine` (FK ke `SalesItem`) menyimpan konfigurasi pajak per item. Saat `create_sales_automated_journals()` dipanggil, setiap tax line memanggil `sync_pajak + confirm_pajak` dari `apps.pajak` — jurnal pajak terpisah dari jurnal utama. Void memanggil `batal_pajak` via `_cancel_sales_pajak()`. Field inline lama di `SalesItem` tetap ada (deprecated).

**Tech Stack:** Django 6.x, `apps.pajak.services` (`sync_pajak`, `confirm_pajak`, `batal_pajak`), `apps.pajak.models` (`PajakTransaksi`, `TarifPajak`), vanilla JS (no framework) sesuai pola existing sales form.

**Spec:** `docs/superpowers/specs/2026-06-29-sales-tax-module-design.md`

---

## File Map

| File | Aksi | Tanggung Jawab |
|---|---|---|
| `apps/sales/models.py` | Modify | Tambah `SalesTaxLine` model |
| `apps/sales/migrations/0008_salestaxline.py` | Create (via makemigrations) | Schema migration |
| `apps/sales/services.py` | Modify | TAX_TYPE_MAP, helpers, refactor journal function |
| `apps/sales/admin.py` | Modify | SalesTaxLineInline |
| `apps/sales/views.py` | Modify | _handle_sales_save, sales_update, sales_delete, sales_detail, sales_invoice |
| `apps/sales/tests.py` | Modify | Test SalesTaxLine model + pajak integration |
| `templates/sales/sales_form.html` | Modify | Multi-tax-line UI, collectFormData, onSTTChange, journal preview |

---

## Task 1: SalesTaxLine Model & Migration

**Files:**
- Modify: `apps/sales/models.py`
- Modify: `apps/sales/tests.py`
- Create: `apps/sales/migrations/0008_salestaxline.py` (via makemigrations)

- [ ] **Step 1.1: Tulis failing test untuk SalesTaxLine**

Tambahkan class berikut ke akhir `apps/sales/tests.py`:

```python
from .models import SalesTaxLine


class SalesTaxLineModelTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='Retail')
        eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=tipe)
        akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP', kode_akun='5.1.1')
        akun_rev = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4')
        item = ItemMasterPurchase.objects.create(nama='Barang A', tipe_item='FG', coa_account=akun_kas)
        stt = SubTransactionType.objects.create(
            nama='Penjualan', module='sales', direction='outflow',
            default_offset_account=akun_hpp,
        )
        header = SalesHeader.objects.create()
        eb_group = SalesEntitasBisnis.objects.create(sales_header=header, entitas_bisnis=eb)
        self.si = SalesItem.objects.create(
            sales_eb=eb_group, item=item, sub_transaction_type=stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=akun_hpp, revenue_account=akun_rev,
        )
        self.akun_ppn = akun_ppn
        self.akun_lawan = akun_lawan

    def test_salestaxline_creation(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertEqual(tl.sales_item, self.si)
        self.assertEqual(tl.tax_type, 'ppn_keluaran')
        self.assertFalse(tl.is_manual)
        self.assertIsNone(tl.tax)

    def test_salestaxline_str(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='pph_23',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertIn('pph_23', str(tl))

    def test_salestaxline_cascade_delete(self):
        SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.si.delete()
        self.assertEqual(SalesTaxLine.objects.count(), 0)

    def test_salestaxline_is_manual(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax=Decimal('11000'),
            is_manual=True,
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertTrue(tl.is_manual)
        self.assertEqual(tl.tax, Decimal('11000'))
```

- [ ] **Step 1.2: Jalankan test, pastikan FAIL dengan ImportError**

```
python manage.py test apps.sales.tests.SalesTaxLineModelTests -v 2
```

Expected: `ImportError: cannot import name 'SalesTaxLine'`

- [ ] **Step 1.3: Tambah `SalesTaxLine` ke `apps/sales/models.py`**

Cari baris `class SalesItemFIFOAllocation` (baris ~286). Sisipkan model berikut tepat SEBELUM class itu (setelah `SalesItem`):

```python
# ── Tax Lines ─────────────────────────────────────────────────────────────────

TAX_TYPE_CHOICES_SALES = [
    ('ppn_keluaran', 'PPN Keluaran'),
    ('pph_23', 'PPh 23'),
    ('pph_21', 'PPh 21'),
    ('pph_4_2', 'PPh 4(2)'),
]


class SalesTaxLine(models.Model):
    sales_item = models.ForeignKey(
        SalesItem, on_delete=models.CASCADE, related_name='tax_lines',
        verbose_name='Sales Item',
    )
    tax_type = models.CharField(
        max_length=30, choices=TAX_TYPE_CHOICES_SALES, verbose_name='Tipe Pajak',
    )
    tax = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Pajak (Nominal)',
        help_text='Nominal pajak. Hasil hitung otomatis atau override manual (lihat is_manual).',
    )
    is_manual = models.BooleanField(
        default=False, verbose_name='Override Manual',
        help_text='True jika nominal pajak diisi/diubah manual. False = dihitung ulang dari tarif.',
    )
    tax_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='sales_tax_lines_pajak', verbose_name='Akun Pajak',
    )
    tax_payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='sales_tax_lines_lawan', verbose_name='Akun Lawan Pajak',
    )

    class Meta:
        verbose_name = 'Sales Tax Line'
        verbose_name_plural = 'Sales Tax Lines'
        ordering = ['id']

    def __str__(self) -> str:
        return f'SI-{self.sales_item_id} — {self.tax_type}'
```

Juga update import di bagian atas `tests.py`:
```python
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesEventLog, SalesTaxLine
```

- [ ] **Step 1.4: Jalankan test, pastikan PASS**

```
python manage.py test apps.sales.tests.SalesTaxLineModelTests -v 2
```

Expected: 4 tests PASS

- [ ] **Step 1.5: Generate migration**

```
python manage.py makemigrations sales --name salestaxline
```

Expected: `Migrations for 'sales': apps/sales/migrations/0008_salestaxline.py`

- [ ] **Step 1.6: Apply migration**

```
python manage.py migrate sales
```

Expected: `Applying sales.0008_salestaxline... OK`

- [ ] **Step 1.7: Commit**

```
git add apps/sales/models.py apps/sales/migrations/0008_salestaxline.py apps/sales/tests.py
git commit -m "feat(sales): add SalesTaxLine model + migration"
```

---

## Task 2: Services — Tax Integration

**Files:**
- Modify: `apps/sales/services.py`
- Modify: `apps/sales/tests.py`

- [ ] **Step 2.1: Tulis failing tests untuk pajak integration**

Tambahkan class berikut ke akhir `apps/sales/tests.py`:

```python
from datetime import date as dt_date
from apps.pajak.models import PajakTransaksi, TarifPajak
from apps.jurnal.models import JurnalHeader
from .services import create_sales_automated_journals, _cancel_sales_pajak


def _seed_tarif(jenis_pajak, tarif_persen, faktor_dpp='1.000000'):
    TarifPajak.objects.get_or_create(
        jenis_pajak=jenis_pajak,
        berlaku_mulai=dt_date(2025, 1, 1),
        defaults={
            'nama': jenis_pajak,
            'tarif_persen': Decimal(str(tarif_persen)),
            'faktor_dpp': Decimal(faktor_dpp),
        },
    )


class SalesTaxLineServiceTests(TestCase):
    def setUp(self):
        _seed_tarif('ppn_umum', '12.0000', '0.916667')
        _seed_tarif('pph_23_jasa', '2.0000')

        tipe = TipeEntitas.objects.create(nama='Retail')
        self.eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe)
        self.akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP', kode_akun='5.1.1')
        self.akun_rev = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        self.akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3')
        self.akun_pph = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4')
        self.item = ItemMasterPurchase.objects.create(
            nama='Barang A', tipe_item='FG', coa_account=self.akun_kas,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )

    def _make_sales_with_tax_line(self, tax_type='ppn_keluaran', tax=None, is_manual=False):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type=tax_type, tax=tax, is_manual=is_manual,
            tax_account=self.akun_ppn, tax_payment_account=self.akun_pph,
        )
        return header, si

    def test_pajak_transaksi_created_on_journal(self):
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.filter(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pt.count(), 1)
        self.assertEqual(pt.first().jenis_pajak, 'ppn_umum')
        self.assertEqual(pt.first().sifat_pajak, 'potong_pungut')
        self.assertEqual(pt.first().status, 'final')

    def test_no_inline_tax_in_main_journal(self):
        """Jurnal utama hanya DPP — tidak ada entry inline pajak."""
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        created = create_sales_automated_journals(header)
        # Main journal: only 2 detail lines (COGS + Revenue entries, each 2 lines)
        # Pajak journal beda header (TRX-PAJ-...)
        main_journal = created[0]
        self.assertFalse(main_journal.nomor_transaksi.startswith('TRX-PAJ'))
        # All detail akuns in main journal should NOT be tax accounts
        detail_akun_ids = set(main_journal.details.values_list('akun_id', flat=True))
        self.assertNotIn(self.akun_ppn.pk, detail_akun_ids)

    def test_multiple_tax_lines_create_multiple_pajak_transaksi(self):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type='ppn_keluaran',
            tax_account=self.akun_ppn, tax_payment_account=self.akun_pph,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type='pph_23',
            tax_account=self.akun_pph, tax_payment_account=self.akun_kas,
        )
        create_sales_automated_journals(header)
        pts = PajakTransaksi.objects.filter(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pts.count(), 2)
        jenis = set(pts.values_list('jenis_pajak', flat=True))
        self.assertIn('ppn_umum', jenis)
        self.assertIn('pph_23_jasa', jenis)

    def test_is_manual_override(self):
        header, si = self._make_sales_with_tax_line(
            tax_type='ppn_keluaran', tax=Decimal('5000'), is_manual=True,
        )
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.get(source_type='sales_item', source_id=si.pk)
        self.assertTrue(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('5000'))

    def test_cancel_sales_pajak_sets_dibatalkan(self):
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.get(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pt.status, 'final')

        _cancel_sales_pajak(header)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')

    def test_sales_item_without_tax_lines_no_pajak_transaksi(self):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        create_sales_automated_journals(header)
        self.assertEqual(PajakTransaksi.objects.count(), 0)
```

- [ ] **Step 2.2: Jalankan test, pastikan FAIL**

```
python manage.py test apps.sales.tests.SalesTaxLineServiceTests -v 2
```

Expected: FAIL — `ImportError: cannot import name '_cancel_sales_pajak'`

- [ ] **Step 2.3: Update `apps/sales/services.py`**

**2.3a — Tambah imports di bagian atas file (setelah imports yang sudah ada):**

```python
from apps.pajak.models import PajakTransaksi
from apps.pajak.services import (
    sync_pajak,
    confirm_pajak as confirm_pajak_trx,
    batal_pajak as batal_pajak_trx,
)
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesTaxLine, SalesItemFIFOAllocation
```

**2.3b — Tambah konstanta TAX_TYPE_MAP dan SIFAT_PAJAK_MAP setelah imports:**

```python
TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}

SIFAT_PAJAK_MAP = {
    'ppn_keluaran': 'potong_pungut',
    'pph_23':       'prepaid',
    'pph_21':       'prepaid',
    'pph_4_2':      'prepaid',
}
```

**2.3c — Tambah helper `_sync_confirm_sales_tax_line` sebelum `create_sales_automated_journals`:**

```python
def _sync_confirm_sales_tax_line(si: SalesItem, sales_header: SalesHeader, tax_line: SalesTaxLine, entitas_bisnis=None) -> None:
    jenis_pajak = TAX_TYPE_MAP.get(tax_line.tax_type)
    if not jenis_pajak:
        return
    sifat_pajak = SIFAT_PAJAK_MAP.get(tax_line.tax_type, 'potong_pungut')
    override_amount = tax_line.tax if tax_line.is_manual else None
    pajak_trx = sync_pajak(
        source_type='sales_item',
        source_obj=si,
        dpp=si.total_sales,
        tanggal=sales_header.tanggal,
        jenis_pajak=jenis_pajak,
        akun_pajak=tax_line.tax_account,
        akun_lawan=tax_line.tax_payment_account,
        sifat_pajak=sifat_pajak,
        override_amount=override_amount,
        entitas_bisnis_override=entitas_bisnis,
    )
    confirm_pajak_trx(pajak_trx)
```

**2.3d — Tambah helper `_cancel_sales_pajak` setelah `_sync_confirm_sales_tax_line`:**

```python
def _cancel_sales_pajak(sales_header: SalesHeader) -> None:
    si_ids = list(
        SalesItem.objects
        .filter(sales_eb__sales_header=sales_header)
        .values_list('id', flat=True)
    )
    qs = PajakTransaksi.objects.filter(
        source_type='sales_item',
        source_id__in=si_ids,
    ).exclude(status='dibatalkan')
    for pajak_trx in qs:
        batal_pajak_trx(pajak_trx)
```

**2.3e — Refactor `create_sales_automated_journals`:**

Dalam fungsi ini, hapus blok `# 3. Tax entry (if applicable)` (sekitar baris 138–153) yang berisi:
```python
# 3. Tax entry (if applicable)
if si.tax and si.tax > 0:
    tax_liability_account = si.tax_payment_account or si.tax_account
    if tax_liability_account:
        detail_lines.append(JurnalDetail(...))
        detail_lines.append(JurnalDetail(...))
```

Ganti dengan loop tax lines via pajak module. Letakkan SETELAH `JurnalDetail.objects.bulk_create(detail_lines)`:

```python
            JurnalDetail.objects.bulk_create(detail_lines)
            created_headers.append(header)

            # Tax lines: processed per SalesItem via pajak module (outside jurnal utama)
            for si in items:
                for tax_line in si.tax_lines.select_related(
                    'tax_account', 'tax_payment_account'
                ).all():
                    _sync_confirm_sales_tax_line(
                        si, sales_header, tax_line,
                        entitas_bisnis=eb_group.entitas_bisnis,
                    )
```

**Perhatian:** loop `for si in items:` yang pertama (untuk `detail_lines`) masih berjalan normal — hanya blok inline tax yang dihapus dari dalamnya. Loop kedua untuk tax lines ditambah SETELAH `bulk_create`.

Hasil akhir fungsi `create_sales_automated_journals` (bagian dalam `with transaction.atomic()`):

```python
def create_sales_automated_journals(sales_header: SalesHeader, user=None) -> list[JurnalHeader]:
    created_headers: list[JurnalHeader] = []

    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.select_related(
            'entitas_bisnis', 'payment_account',
        ).all():
            items = list(eb_group.items.select_related(
                'item', 'offset_coa_account', 'revenue_account',
                'inventory_account', 'tax_account', 'tax_payment_account',
                'sub_transaction_type',
            ).all())

            if not items:
                continue

            nomor = _next_sales_journal_number()
            header = JurnalHeader.objects.create(
                tanggal=sales_header.tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=f'Penjualan {sales_header.transaction_id} — {eb_group.entitas_bisnis.nama}',
                entitas_bisnis=eb_group.entitas_bisnis,
                is_penyesuaian=False,
            )

            detail_lines: list[JurnalDetail] = []

            for si in items:
                _payment_akun = si.payment_account or eb_group.payment_account

                # 1. COGS entry
                if si.cogs_amount > 0 and si.inventory_account_id:
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.offset_coa_account,
                        debit=si.cogs_amount,
                        kredit=Decimal('0'),
                    ))
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.inventory_account,
                        debit=Decimal('0'),
                        kredit=si.cogs_amount,
                    ))

                # 2. Revenue entry (DPP only — pajak handled separately)
                if si.total_sales > 0 and _payment_akun:
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=_payment_akun,
                        debit=si.total_sales,
                        kredit=Decimal('0'),
                    ))
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.revenue_account,
                        debit=Decimal('0'),
                        kredit=si.total_sales,
                    ))

            JurnalDetail.objects.bulk_create(detail_lines)
            created_headers.append(header)

            # Tax lines via pajak module (jurnal pajak terpisah)
            for si in items:
                for tax_line in si.tax_lines.select_related(
                    'tax_account', 'tax_payment_account'
                ).all():
                    _sync_confirm_sales_tax_line(
                        si, sales_header, tax_line,
                        entitas_bisnis=eb_group.entitas_bisnis,
                    )

        if sales_header.payment_type == 'credit':
            from apps.piutang.services import create_piutang_from_sales
            create_piutang_from_sales(sales_header, user=user)

    return created_headers
```

- [ ] **Step 2.4: Jalankan semua test services**

```
python manage.py test apps.sales.tests.SalesTaxLineServiceTests -v 2
```

Expected: 6 tests PASS

- [ ] **Step 2.5: Jalankan semua test sales untuk deteksi regresi**

```
python manage.py test apps.sales -v 2
```

Expected: semua test PASS (tidak ada regresi)

- [ ] **Step 2.6: Commit**

```
git add apps/sales/services.py apps/sales/tests.py
git commit -m "feat(sales): integrate pajak module via SalesTaxLine — sync/confirm/cancel"
```

---

## Task 3: Admin

**Files:**
- Modify: `apps/sales/admin.py`

- [ ] **Step 3.1: Update `apps/sales/admin.py`**

Ganti seluruh isi file dengan:

```python
"""Sales admin."""
from django.contrib import admin
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesTaxLine


class SalesEntitasBisnisInline(admin.TabularInline):
    model = SalesEntitasBisnis
    extra = 0
    raw_id_fields = ('entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
                     'payment_account')


class SalesTaxLineInline(admin.TabularInline):
    model = SalesTaxLine
    extra = 0
    raw_id_fields = ('tax_account', 'tax_payment_account')


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    raw_id_fields = ('item', 'sub_transaction_type', 'offset_coa_account',
                     'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')


@admin.register(SalesHeader)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'is_locked')
    list_filter = ('is_locked', 'tanggal')
    search_fields = ('transaction_id',)
    inlines = (SalesEntitasBisnisInline,)


@admin.register(SalesEntitasBisnis)
class SalesEntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                    'entitas_bisnis_lv3', 'payment_account')
    list_filter = ('entitas_bisnis',)
    search_fields = ('sales_header__transaction_id',)
    list_select_related = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                           'entitas_bisnis_lv3', 'payment_account')
    raw_id_fields = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                     'entitas_bisnis_lv3', 'payment_account')
    inlines = (SalesItemInline,)


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = ('sales_eb', 'item', 'quantity', 'selling_price', 'total_sales', 'cogs_amount')
    list_select_related = ('sales_eb', 'item')
    raw_id_fields = ('sales_eb', 'item', 'sub_transaction_type',
                     'offset_coa_account', 'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')
    inlines = (SalesTaxLineInline,)
```

- [ ] **Step 3.2: Verify admin loads tanpa error**

```
python manage.py check --deploy 2>&1 | head -20
```

Expected: tidak ada error terkait sales admin

- [ ] **Step 3.3: Commit**

```
git add apps/sales/admin.py
git commit -m "feat(sales): add SalesTaxLineInline to admin"
```

---

## Task 4: Views — Backend

**Files:**
- Modify: `apps/sales/views.py`
- Modify: `apps/sales/tests.py`

- [ ] **Step 4.1: Tulis failing test untuk view POST dengan tax lines**

Tambahkan ke akhir `apps/sales/tests.py`:

```python
from .services import _cancel_sales_pajak


class SalesTaxLineViewTests(TestCase):
    def setUp(self):
        _seed_tarif('ppn_umum', '12.0000', '0.916667')

        self.role = Role.objects.create(kode='admin2', nama='Admin2')
        self.user = User.objects.create_user(email='view@test.com', password='pass1234', role=self.role)
        self.client = Client()
        self.client.login(email='view@test.com', password='pass1234')

        tipe = TipeEntitas.objects.create(nama='FnB2')
        self.eb = EntitasBisnis.objects.create(nama='Cafe XYZ', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1a', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1a', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4a', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1a', nama='Pendapatan Usaha')
        self.akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='3a', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1a', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3.v')
        self.akun_lawan = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4.v')

        self.item = ItemMasterPurchase.objects.create(
            nama='Produk X', tipe_item='FG', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan View', module='sales', direction='outflow',
            default_offset_account=self.akun_persediaan,
        )
        FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )

    def _payload_with_tax_lines(self, tax_type='ppn_keluaran'):
        groups = [{
            'eb_selection': f'lv1:{self.eb.pk}',
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'quantity': '5',
                'selling_price': '20000',
                'offset_coa_account_id': self.akun_persediaan.pk,
                'revenue_account_id': self.akun_pendapatan.pk,
                'payment_account_id': self.akun_modal.pk,
                'tax_lines': [{
                    'tax_type': tax_type,
                    'tax': '',
                    'is_manual': False,
                    'tax_account_id': self.akun_ppn.pk,
                    'tax_payment_account_id': self.akun_lawan.pk,
                }],
            }],
        }]
        return json.dumps(groups)

    def test_create_sales_with_tax_lines_creates_salestaxline(self):
        resp = self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SalesTaxLine.objects.count(), 1)
        tl = SalesTaxLine.objects.first()
        self.assertEqual(tl.tax_type, 'ppn_keluaran')
        self.assertFalse(tl.is_manual)

    def test_create_sales_with_tax_lines_creates_pajak_transaksi(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        pts = PajakTransaksi.objects.filter(source_type='sales_item')
        self.assertEqual(pts.count(), 1)
        self.assertEqual(pts.first().status, 'final')

    def test_delete_sales_cancels_pajak_transaksi(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        header = SalesHeader.objects.first()
        pt = PajakTransaksi.objects.filter(source_type='sales_item').first()
        self.assertEqual(pt.status, 'final')

        self.client.post(reverse('sales:delete', args=[header.pk]))
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')
```

- [ ] **Step 4.2: Jalankan test, pastikan FAIL**

```
python manage.py test apps.sales.tests.SalesTaxLineViewTests -v 2
```

Expected: FAIL — `SalesTaxLine.objects.count() == 0` (view belum membuat SalesTaxLine)

- [ ] **Step 4.3: Update `apps/sales/views.py` — imports**

Di bagian atas file, update import dari `.models`:

```python
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesTaxLine, SalesItemFIFOAllocation, SalesEventLog
```

Update import dari `.services`:

```python
from .services import (
    get_available_stock,
    get_fifo_unit_cost,
    process_sales_fifo,
    create_sales_automated_journals,
    reverse_sales_automated_journals,
    reverse_sales_fifo,
    _cancel_sales_pajak,
)
```

- [ ] **Step 4.4: Update `_handle_sales_save()` — buat SalesTaxLine**

Di dalam `_handle_sales_save()`, cari blok `SalesItem.objects.create(...)`. Setelah baris `si = SalesItem.objects.create(...)` (sekarang hanya assign ke variabel `si`), tambahkan loop ini:

Pertama, ubah baris `SalesItem.objects.create(...)` menjadi `si = SalesItem.objects.create(...)` jika belum assign.

Lalu tambahkan setelah create:

```python
                # Buat SalesTaxLine dari tax_lines array (format baru)
                for tl_data in item_data.get('tax_lines', []):
                    tl_tax_type = tl_data.get('tax_type', '')
                    if not tl_tax_type:
                        continue
                    tl_tax_raw = tl_data.get('tax')
                    tl_tax_val = Decimal(str(tl_tax_raw)) if tl_tax_raw else None
                    tl_is_manual = bool(tl_data.get('is_manual', False)) or bool(tl_tax_val)
                    tl_tax_account_id = tl_data.get('tax_account_id') or None
                    tl_tax_payment_account_id = tl_data.get('tax_payment_account_id') or None
                    if not tl_tax_account_id or not tl_tax_payment_account_id:
                        continue
                    SalesTaxLine.objects.create(
                        sales_item=si,
                        tax_type=tl_tax_type,
                        tax=tl_tax_val,
                        is_manual=tl_is_manual,
                        tax_account_id=tl_tax_account_id,
                        tax_payment_account_id=tl_tax_payment_account_id,
                    )
```

Pastikan baris `SalesItem.objects.create(...)` sudah di-assign ke `si`:

```python
                si = SalesItem.objects.create(
                    sales_eb=eb_group,
                    item_id=item_data['item_id'],
                    ...
                )
```

- [ ] **Step 4.5: Update `sales_delete` view — tambah `_cancel_sales_pajak`**

Di dalam `sales_delete`, cari blok `with transaction.atomic():`. Tambahkan `_cancel_sales_pajak(sales)` sebagai baris PERTAMA di dalam block tersebut:

```python
    if request.method == 'POST':
        tid = sales.transaction_id
        with transaction.atomic():
            for journal in related_journals:
                log_jurnal_terhapus(journal, 'sales', request)
            _cancel_sales_pajak(sales)            # ← tambah di sini
            reverse_sales_automated_journals(sales)
            reverse_sales_fifo(sales)
            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='VOIDED',
                description=f'Transaksi {tid} dihapus.',
                actor=request.user,
            )
            sales.delete()
```

- [ ] **Step 4.6: Update `_handle_sales_save()` edit mode — cancel pajak lama sebelum reverse**

Di dalam `_handle_sales_save()`, cari blok `if existing:`. Tambahkan `_cancel_sales_pajak(existing)` sebelum `reverse_sales_automated_journals(existing)`:

```python
        if existing:
            _cancel_sales_pajak(existing)              # ← tambah di sini
            reverse_sales_automated_journals(existing)
            reverse_sales_fifo(existing)
            existing.entitas_groups.all().delete()
            ...
```

- [ ] **Step 4.7: Update `sales_update` view — sertakan tax_lines di items_data**

Di dalam `sales_update`, cari loop `for si in eg.items.select_related(...)`. Update select_related/prefetch untuk include tax_lines, dan tambah `tax_lines` di `items_data`:

Ganti:
```python
        for si in eg.items.select_related(
            'item', 'sub_transaction_type', 'offset_coa_account',
            'revenue_account', 'payment_account', 'tax_account', 'tax_payment_account',
        ).all():
            items_data.append({
                ...
                'tax_payment_account_id': si.tax_payment_account_id or '',
            })
```

Dengan:
```python
        for si in eg.items.select_related(
            'item', 'sub_transaction_type', 'offset_coa_account',
            'revenue_account', 'payment_account', 'tax_account', 'tax_payment_account',
        ).prefetch_related('tax_lines').all():
            items_data.append({
                'item_id': si.item_id,
                'item_name': f'{si.item.item_id} - {si.item.nama}',
                'tipe_item': si.item.tipe_item,
                'sub_transaction_type_id': si.sub_transaction_type_id,
                'quantity': str(si.quantity),
                'selling_price': str(si.selling_price),
                'hpp_terpakai': str(si.hpp_terpakai) if si.hpp_terpakai else str(si.cogs_amount or ''),
                'offset_coa_account_id': si.offset_coa_account_id,
                'revenue_account_id': si.revenue_account_id,
                'payment_account_id': si.payment_account_id or eg.payment_account_id or '',
                # Deprecated inline fields (backward compat for display only)
                'tax': str(si.tax) if si.tax else '',
                'tax_type': si.tax_type or '',
                'tax_account_id': si.tax_account_id or '',
                'tax_payment': si.tax_payment or '',
                'tax_payment_account_id': si.tax_payment_account_id or '',
                # New: tax lines array
                'tax_lines': [
                    {
                        'tax_type': tl.tax_type,
                        'tax': str(tl.tax) if tl.tax else '',
                        'is_manual': tl.is_manual,
                        'tax_account_id': tl.tax_account_id,
                        'tax_payment_account_id': tl.tax_payment_account_id,
                    }
                    for tl in si.tax_lines.all()
                ],
            })
```

- [ ] **Step 4.8: Update `sales_detail` view — prefetch tax_lines**

Ganti prefetch_related di `sales_detail`:

```python
    eb_groups = sales.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3', 'payment_account',
    ).prefetch_related(
        'items__item', 'items__sub_transaction_type',
        'items__offset_coa_account', 'items__revenue_account',
        'items__payment_account',
        'items__tax_account', 'items__tax_payment_account',
        'items__tax_lines__tax_account',
        'items__tax_lines__tax_payment_account',
    ).all()
```

- [ ] **Step 4.9: Update `sales_invoice` view — prefetch tax_lines + fix tax_total**

Update prefetch di `sales_invoice` (cari `sales.entitas_groups.select_related(...)`):

```python
    eb_groups = sales.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3', 'payment_account',
    ).prefetch_related(
        'items__item', 'items__sub_transaction_type',
        'items__offset_coa_account', 'items__revenue_account',
        'items__payment_account',
        'items__tax_account', 'items__tax_payment_account',
        'items__tax_lines',
    ).all()
```

Ganti komputasi `tax_total` di dalam loop items (cari `tax_total += si.tax or Decimal('0')`):

```python
            for si in eg.items.all():
                subtotal += si.total_sales or Decimal('0')
                # Use tax_lines (new) or fallback to deprecated si.tax (old records)
                tax_lines_list = list(si.tax_lines.all())
                if tax_lines_list:
                    tax_total += sum(tl.tax or Decimal('0') for tl in tax_lines_list)
                else:
                    tax_total += si.tax or Decimal('0')
```

- [ ] **Step 4.10: Jalankan semua view tests**

```
python manage.py test apps.sales.tests.SalesTaxLineViewTests -v 2
```

Expected: 3 tests PASS

- [ ] **Step 4.11: Jalankan semua sales tests untuk deteksi regresi**

```
python manage.py test apps.sales -v 2
```

Expected: semua test PASS

- [ ] **Step 4.12: Commit**

```
git add apps/sales/views.py apps/sales/tests.py
git commit -m "feat(sales): update views to create SalesTaxLine and cancel pajak on delete"
```

---

## Task 5: Template — Multi-Tax-Line UI

**Files:**
- Modify: `templates/sales/sales_form.html`

**Catatan:** Task ini tidak ada automated test — verifikasi manual di browser.

- [ ] **Step 5.1: Tambah CSS untuk tax line rows**

Di dalam blok `<style>` (sebelum `</style>`), tambahkan:

```css
  /* ── Tax Lines ── */
  .ni-tax-line-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
  .ni-tax-line-row .ni-sales-input { flex: 1; min-width: 100px; }
  .ni-tax-lines-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .ni-tax-lines-header span { font-size: 0.78rem; color: var(--ni-text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }
  @media (max-width: 767px) {
    .ni-tax-line-row { flex-direction: column; align-items: stretch; }
    .ni-tax-line-row .ni-sales-input { min-width: unset; font-size: 16px; min-height: 40px; }
  }
```

- [ ] **Step 5.2: Ganti fungsi `addItemRow` — bagian `trAdv` (advanced row)**

Cari blok mulai dari `// Advanced tax row (hidden by default)` hingga `tbody.appendChild(trAdv);` (sekitar baris 503–560).

Ganti seluruh blok `trAdv` dengan struktur multi-tax-line:

```javascript
    // Advanced tax lines container (hidden by default)
    var hasTaxLines = prefill && prefill.tax_lines && prefill.tax_lines.length > 0;
    var trAdv = document.createElement('tr');
    trAdv.id = rid + '_adv';
    trAdv.className = 'advanced-row';
    trAdv.style.display = hasTaxLines ? '' : 'none';
    trAdv.innerHTML =
      '<td colspan="10" style="padding:8px 10px;background:var(--ni-bg);">' +
        '<div class="ni-tax-lines-header">' +
          '<span><i data-lucide="receipt" style="width:12px;height:12px;vertical-align:middle;"></i> Tax Lines</span>' +
          '<button type="button" class="ni-btn ni-btn--secondary ni-btn--sm" onclick="addTaxLine(\'' + rid + '\')" style="padding:4px 10px;">' +
            '<i data-lucide="plus" style="width:12px;height:12px"></i> Tambah Pajak' +
          '</button>' +
        '</div>' +
        '<div id="' + rid + '_tax_lines_list"></div>' +
      '</td>';

    tbody.appendChild(tr);
    tbody.appendChild(trAdv);
```

- [ ] **Step 5.3: Tambah fungsi `addTaxLine` dan `removeTaxLine`**

Di dalam `<script>`, setelah fungsi `toggleAdvanced` (sekitar baris 640), tambahkan:

```javascript
  // ── Tax Line Management ───────────────────────────────────────────────────
  window.addTaxLine = function (rid, prefill) {
    var list = document.getElementById(rid + '_tax_lines_list');
    if (!list) return;

    var taxTypeOptions =
      '<option value="">— Tipe Pajak —</option>' +
      '<option value="ppn_keluaran"' + (prefill && prefill.tax_type === 'ppn_keluaran' ? ' selected' : '') + '>PPN Keluaran</option>' +
      '<option value="pph_23"' + (prefill && prefill.tax_type === 'pph_23' ? ' selected' : '') + '>PPh 23</option>' +
      '<option value="pph_21"' + (prefill && prefill.tax_type === 'pph_21' ? ' selected' : '') + '>PPh 21</option>' +
      '<option value="pph_4_2"' + (prefill && prefill.tax_type === 'pph_4_2' ? ' selected' : '') + '>PPh 4(2)</option>';

    var taxAccountOptions = '<option value="">— Akun Pajak —</option>';
    akunList.forEach(function (a) {
      var sel = (prefill && prefill.tax_account_id == a.id) ? ' selected' : '';
      taxAccountOptions += '<option value="' + a.id + '"' + sel + '>' + esc(a.text) + '</option>';
    });

    var taxPaymentAccountOptions = '<option value="">— Akun Lawan —</option>';
    akunList.forEach(function (a) {
      var sel = (prefill && prefill.tax_payment_account_id == a.id) ? ' selected' : '';
      taxPaymentAccountOptions += '<option value="' + a.id + '"' + sel + '>' + esc(a.text) + '</option>';
    });

    var div = document.createElement('div');
    div.className = 'ni-tax-line-row';
    div.innerHTML =
      '<select class="ni-sales-input tax-type-sel" style="flex:1.2;min-width:110px;">' + taxTypeOptions + '</select>' +
      '<input type="number" class="ni-sales-input tax-nominal-inp" placeholder="Nominal (kosong=auto)" step="any" min="0" value="' + (prefill && prefill.tax ? esc(String(prefill.tax)) : '') + '" style="flex:1;min-width:90px;" title="Kosongkan agar dihitung otomatis dari tarif">' +
      '<select class="ni-sales-input tax-account-sel" style="flex:2;min-width:130px;">' + taxAccountOptions + '</select>' +
      '<select class="ni-sales-input tax-payment-account-sel" style="flex:2;min-width:130px;">' + taxPaymentAccountOptions + '</select>' +
      '<button type="button" class="ni-btn ni-btn--outline-danger ni-btn--sm" onclick="this.closest(\'.ni-tax-line-row\').remove()" style="padding:4px 8px;flex-shrink:0;" title="Hapus tax line">' +
        '<i data-lucide="x" style="width:12px;height:12px"></i>' +
      '</button>';

    list.appendChild(div);
    lucide.createIcons();
  };

  function collectTaxLines(rid) {
    var list = document.getElementById(rid + '_tax_lines_list');
    if (!list) return [];
    var lines = [];
    list.querySelectorAll('.ni-tax-line-row').forEach(function (row) {
      var taxType = row.querySelector('.tax-type-sel') ? row.querySelector('.tax-type-sel').value : '';
      if (!taxType) return;
      var nominalVal = row.querySelector('.tax-nominal-inp') ? row.querySelector('.tax-nominal-inp').value.trim() : '';
      var taxAccountId = row.querySelector('.tax-account-sel') ? row.querySelector('.tax-account-sel').value : '';
      var taxPaymentAccountId = row.querySelector('.tax-payment-account-sel') ? row.querySelector('.tax-payment-account-sel').value : '';
      lines.push({
        tax_type: taxType,
        tax: nominalVal || '',
        is_manual: !!nominalVal,
        tax_account_id: taxAccountId,
        tax_payment_account_id: taxPaymentAccountId,
      });
    });
    return lines;
  }
```

- [ ] **Step 5.4: Update `addItemRow` — prefill tax_lines saat edit**

Di dalam `addItemRow`, setelah `tbody.appendChild(trAdv);`, tambahkan prefill tax lines:

```javascript
    // Prefill tax lines dari data server (edit mode)
    if (hasTaxLines) {
      prefill.tax_lines.forEach(function (tl) {
        addTaxLine(rid, tl);
      });
    }
```

- [ ] **Step 5.5: Update `onSTTChange` — gunakan `addTaxLine` alih-alih field inline lama**

Cari blok `// Tax fields — show advanced row if tax_type is set` (sekitar baris 815):

Ganti:
```javascript
        // Tax fields — show advanced row if tax_type is set
        if (data.tax_type) {
          var advRow = document.getElementById(rid + '_adv');
          if (advRow) advRow.style.display = '';
          var taxTypeSel = document.getElementById(rid + '_tax_type');
          if (taxTypeSel) taxTypeSel.value = data.tax_type;
          var taxAccountSel = document.getElementById(rid + '_tax_account');
          if (taxAccountSel && data.tax_account_id) taxAccountSel.value = data.tax_account_id;
        }
```

Dengan:
```javascript
        // Jika STT memiliki default tax type, tambah tax line (hanya jika belum ada)
        if (data.tax_type) {
          var advRow = document.getElementById(rid + '_adv');
          if (advRow) advRow.style.display = '';
          var list = document.getElementById(rid + '_tax_lines_list');
          if (list && list.querySelectorAll('.ni-tax-line-row').length === 0) {
            addTaxLine(rid, {
              tax_type: data.tax_type,
              tax_account_id: data.tax_account_id || '',
              tax_payment_account_id: '',
              tax: '',
            });
          }
        }
```

- [ ] **Step 5.6: Update `collectFormData` — ambil `tax_lines` bukan field inline**

Cari blok `items.push({...})` di dalam `collectFormData`. Ganti field tax inline dengan `tax_lines`:

```javascript
        items.push({
          item_id: itemVal,
          item_name: itemText,
          sub_transaction_type_id: sttSel ? sttSel.value : '',
          quantity: isBulk ? '0' : (document.getElementById(rid + '_qty').value || '0'),
          selling_price: document.getElementById(rid + '_price').value || '0',
          hpp_terpakai: isBulk ? (document.getElementById(rid + '_hpp').value || '0') : '0',
          is_bulk: isBulk ? '1' : '0',
          offset_coa_account_id: document.getElementById(rid + '_offset').value || '',
          revenue_account_id: document.getElementById(rid + '_revenue').value || '',
          payment_account_id: document.getElementById(rid + '_payment') ? document.getElementById(rid + '_payment').value : '',
          tax_lines: collectTaxLines(rid),
          // Deprecated inline fields (kept empty — logic now in tax_lines)
          tax: '',
          tax_type: '',
          tax_account_id: '',
          tax_payment: '',
          tax_payment_account_id: '',
        });
```

- [ ] **Step 5.7: Update journal preview — tampilkan tax lines**

Di dalam `showJournalPreview`, cari blok `// Tax entries if present` (sekitar baris 882):

Ganti:
```javascript
        // Tax entries if present
        var tax = parseFloat(item.tax || 0);
        if (tax > 0 && item.tax_account_id) {
          ...
        }
```

Dengan:
```javascript
        // Tax lines preview
        if (item.tax_lines && item.tax_lines.length > 0) {
          item.tax_lines.forEach(function (tl) {
            if (!tl.tax_type || !tl.tax_account_id) return;
            var nominalRaw = parseFloat(tl.tax || 0);
            var taxName = 'Tax Account';
            var tMatch = akunList.find(function (a) { return a.id == tl.tax_account_id; });
            if (tMatch) taxName = tMatch.text;
            var nominalDisplay = nominalRaw > 0 ? formatNum(nominalRaw) : '<em style="color:var(--ni-text-muted);">auto</em>';
            rowNum++;
            tbody.innerHTML += '<tr><td>' + rowNum + '</td><td>' + esc(ebLabel) + '</td>' +
              '<td>' + esc(taxName) + ' <span style="color:var(--ni-text-muted);font-size:0.8em;">(' + esc(tl.tax_type) + ')</span></td>' +
              '<td style="text-align:right;">' + nominalDisplay + '</td><td></td></tr>';
            if (tl.tax_payment_account_id && nominalRaw > 0) {
              rowNum++;
              var tpMatch = akunList.find(function (a) { return a.id == tl.tax_payment_account_id; });
              var tpText = tpMatch ? tpMatch.text : 'Akun Lawan';
              tbody.innerHTML += '<tr><td>' + rowNum + '</td><td>' + esc(ebLabel) + '</td>' +
                '<td>' + esc(tpText) + '</td><td></td><td style="text-align:right;">' + formatNum(nominalRaw) + '</td></tr>';
            }
          });
        }
```

- [ ] **Step 5.8: Verifikasi manual di browser**

Jalankan dev server:
```
python manage.py runserver
```

Cek:
1. Buka `/sales/tambah/` — tombol "Advanced (Pajak)" muncul di footer tiap EB group
2. Klik "Advanced (Pajak)" → tax lines container muncul dengan tombol "+ Tambah Pajak"
3. Klik "+ Tambah Pajak" → baris tax line muncul dengan 4 field (Tax Type, Nominal, Akun Pajak, Akun Lawan)
4. Isi tax line + simpan → sales tersimpan, cek `/admin/sales/salesitem/` → `SalesTaxLine` terbuat
5. Edit sales lama (tanpa tax lines) → tidak crash, tax lines section kosong
6. Edit sales baru (dengan tax lines) → tax lines ter-prefill dari data server
7. Pilih Sub-Trx Type yang punya `default_tax_type` → tax line otomatis ditambah
8. Journal Preview menampilkan tax lines (nominal "auto" jika kosong)

- [ ] **Step 5.9: Commit**

```
git add templates/sales/sales_form.html
git commit -m "feat(sales): multi-tax-line UI in sales form (addTaxLine, collectTaxLines)"
```

---

## Task 6: Final Integration Test

- [ ] **Step 6.1: Jalankan seluruh test suite sales**

```
python manage.py test apps.sales -v 2
```

Expected: semua test PASS, tidak ada regresi

- [ ] **Step 6.2: Jalankan seluruh test suite pajak untuk pastikan tidak ada regresi**

```
python manage.py test apps.pajak -v 2
```

Expected: semua test PASS

- [ ] **Step 6.3: Jalankan full test suite**

```
python manage.py test --parallel 2>&1 | tail -5
```

Expected: `OK` atau daftar failure yang tidak terkait sales/pajak

- [ ] **Step 6.4: Commit final (jika ada perubahan kecil)**

```
git add -p
git commit -m "fix(sales): integration test fixes"
```

---

## Catatan Penting

**backward compat:** Field `tax`, `tax_type`, `tax_account`, `tax_payment`, `tax_payment_account` di `SalesItem` tetap ada di DB. Data lama yang punya `si.tax` masih ditampilkan di `sales_invoice` melalui fallback. Data baru menggunakan `SalesTaxLine`.

**`source_type='sales_item'`** sudah ada di `SOURCE_TYPE_CHOICES` di `apps/pajak/models.py` — tidak perlu migration pajak.

**`_next_sales_journal_number()`** tidak perlu di-wrap `select_for_update` karena jurnal pajak menggunakan `_next_pajak_journal_number()` milik modul pajak sendiri.

**Edit mode:** Saat edit, `_cancel_sales_pajak(existing)` dipanggil sebelum `reverse_sales_automated_journals(existing)` — ini membatalkan jurnal pajak lama, lalu jurnal utama lama di-reverse, kemudian semuanya dibuat ulang.
