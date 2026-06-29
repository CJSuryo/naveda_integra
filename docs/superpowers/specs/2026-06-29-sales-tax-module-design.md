# Desain Modul Pajak di Sales — naveda_integra

**Tanggal:** 2026-06-29
**Status:** Disetujui — siap implementasi

---

## 1. Tujuan

Mengintegrasikan modul pajak (`apps.pajak`) ke dalam modul sales (`apps.sales`) dengan pola yang identik dengan modul pendapatan (`apps.pendapatan`).

Sebelumnya modul sales menangani pajak secara inline (jurnal debit/kredit langsung di `create_sales_automated_journals()`). Setelah implementasi ini, semua logika pajak di modul sales diserahkan sepenuhnya ke `apps.pajak` sesuai prinsip sentralisasi di [desain modul pajak](./2026-06-19-pajak-module-design.md).

---

## 2. Keputusan Desain

| Keputusan | Pilihan | Alasan |
|---|---|---|
| Model pajak | `SalesTaxLine` terpisah (FK ke `SalesItem`) | Identik dengan `KPTaxLine` di pendapatan |
| Tax lines per item | Banyak (many-to-one) | Satu item bisa kena PPN + PPh 23 sekaligus |
| Status tracking | Via `PajakTransaksi.status` saja | Sesuai prinsip sentralisasi modul pajak |
| Field lama di `SalesItem` | Tetap ada (deprecated, tidak dihapus) | Backward compat untuk data lama |
| TAX_TYPE_MAP | Didefinisikan di `sales/services.py` | Konteks per-modul, tidak dicampur ke pajak |

---

## 3. Model

### `SalesTaxLine` (baru di `apps/sales/models.py`)

Mirror persis `KPTaxLine` di pendapatan. Ditempatkan setelah `SalesItem`.

```python
TAX_TYPE_CHOICES = [
    ('ppn_keluaran', 'PPN Keluaran'),
    ('pph_23', 'PPh 23'),
    ('pph_21', 'PPh 21'),
    ('pph_4_2', 'PPh 4(2)'),
]

class SalesTaxLine(models.Model):
    sales_item = models.ForeignKey(
        SalesItem, on_delete=models.CASCADE, related_name='tax_lines',
    )
    tax_type = models.CharField(max_length=30, choices=TAX_TYPE_CHOICES, verbose_name='Tipe Pajak')
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

### Field deprecated di `SalesItem`

Field berikut tetap ada di DB tapi tidak digunakan oleh logic baru:
- `tax` (DecimalField)
- `tax_type` (CharField)
- `tax_account` (FK)
- `tax_payment` (CharField)
- `tax_payment_account` (FK)

---

## 4. Services (`apps/sales/services.py`)

### 4.1 Konstanta baru

```python
from apps.pajak.models import PajakTransaksi
from apps.pajak.services import sync_pajak, confirm_pajak as confirm_pajak_trx, batal_pajak as batal_pajak_trx

TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}

SIFAT_PAJAK_MAP = {
    'ppn_keluaran': 'potong_pungut',  # kita pungut PPN dari pembeli → Utang PPN
    'pph_23':       'prepaid',        # pembeli memotong dari pembayaran → Uang Muka PPh
    'pph_21':       'prepaid',
    'pph_4_2':      'prepaid',
}
```

### 4.2 Helper baru: `_sync_confirm_sales_tax_line()`

Mirror `_sync_confirm_tax_line()` di pendapatan. DPP = `si.total_sales`.

```python
def _sync_confirm_sales_tax_line(si, sales_header, tax_line, entitas_bisnis=None):
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

### 4.3 Helper baru: `_cancel_sales_pajak()`

Mirror `_cancel_kp_pajak()` di pendapatan.

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

### 4.4 Perubahan `create_sales_automated_journals()`

Hapus blok `# 3. Tax entry` (inline tax journal). Ganti dengan loop tax lines via `sync_pajak + confirm_pajak`:

```python
# Di dalam loop `for si in items:`, setelah revenue entry:
for tax_line in si.tax_lines.select_related('tax_account', 'tax_payment_account').all():
    _sync_confirm_sales_tax_line(
        si, sales_header, tax_line,
        entitas_bisnis=eb_group.entitas_bisnis,
    )
```

Jurnal utama tetap hanya booking DPP (`total_sales`) — tidak ada komponen pajak di jurnal sales. Konsisten dengan prinsip pajak module design.

### 4.5 `reverse_sales_automated_journals()` — tidak berubah

Reversal jurnal utama tetap sama. Pajak dibatalkan secara terpisah via `_cancel_sales_pajak()` yang dipanggil dari views.

---

## 5. Views (`apps/sales/views.py`)

### 5.1 Format JSON item_data (diperluas)

Tambah field `tax_lines` (array) di JSON per item yang dikirim dari form:

```json
{
  "item_id": 1,
  "quantity": "2",
  "selling_price": "100000",
  "tax_lines": [
    {
      "tax_type": "ppn_keluaran",
      "tax": "",
      "is_manual": false,
      "tax_account_id": 42,
      "tax_payment_account_id": 55
    }
  ]
}
```

Field lama (`tax`, `tax_type`, `tax_account_id`, `tax_payment`, `tax_payment_account_id`) tetap diterima untuk backward compat saat edit record lama.

### 5.2 `_handle_sales_save()` — perubahan

Setelah `SalesItem.objects.create(...)`, tambah loop membuat `SalesTaxLine`:

```python
from .models import SalesTaxLine

for tl in item_data.get('tax_lines', []):
    tax_val = tl.get('tax')
    SalesTaxLine.objects.create(
        sales_item=si,
        tax_type=tl['tax_type'],
        tax=Decimal(str(tax_val)) if tax_val else None,
        is_manual=bool(tl.get('is_manual', False)),
        tax_account_id=tl['tax_account_id'],
        tax_payment_account_id=tl['tax_payment_account_id'],
    )
```

### 5.3 `sales_update` view — perubahan

Saat membangun `items_data` untuk JS, prefetch `tax_lines` dan sertakan dalam output:

```python
for si in eg.items.select_related(...).prefetch_related('tax_lines').all():
    items_data.append({
        ...
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

### 5.4 `sales_delete` view — perubahan

Tambah `_cancel_sales_pajak(sales)` di dalam `transaction.atomic()` sebelum `reverse_sales_automated_journals()`:

```python
with transaction.atomic():
    _cancel_sales_pajak(sales)          # ← batal semua PajakTransaksi
    reverse_sales_automated_journals(sales)
    reverse_sales_fifo(sales)
    ...
```

### 5.5 `sales_detail` view — perubahan

Tambah prefetch tax lines:

```python
.prefetch_related(
    'items__tax_lines__tax_account',
    'items__tax_lines__tax_payment_account',
    ...
)
```

### 5.6 `sales_invoice` view — perubahan

Tambah prefetch `items__tax_lines` di queryset `eb_groups` (sama seperti `sales_detail`).

Ganti `si.tax or 0` dengan sum dari `tax_lines`, fallback ke `si.tax` untuk record lama yang belum punya tax lines:

```python
tax_lines_list = list(si.tax_lines.all())  # sudah di-prefetch, tidak ada query tambahan
if tax_lines_list:
    tax_total += sum(tl.tax or Decimal('0') for tl in tax_lines_list)
else:
    tax_total += si.tax or Decimal('0')
```

---

## 6. Admin (`apps/sales/admin.py`)

Tambah `SalesTaxLineInline` sebagai inline di `SalesItemAdmin`:

```python
class SalesTaxLineInline(admin.TabularInline):
    model = SalesTaxLine
    extra = 0
    raw_id_fields = ('tax_account', 'tax_payment_account')

@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    ...
    inlines = (SalesTaxLineInline,)
```

---

## 7. Template (`sales/sales_form.html`)

Tiap item row ditambah UI tax lines:
- Tombol **"+ Tambah Pajak"** di bawah row item
- Sub-baris tax line berisi: dropdown `tax_type`, input nominal `tax` (opsional — kosong = auto-hitung dari tarif), dropdown `tax_account`, dropdown `tax_payment_account`, tombol hapus
- Styling **mengikuti CSS existing modul sales** (bukan pendapatan) — class, border, spacing, dll

Data tax lines disimpan di JS state per item dan disertakan dalam JSON saat submit.

---

## 8. Migration

Satu migration baru: `apps/sales/migrations/0008_salestaxline.py`

- Membuat tabel `sales_salestaxline`
- FK ke `sales_salesitem`, `master_data_akun` (x2)
- Tidak ada perubahan kolom pada tabel `sales_salesitem` yang sudah ada

---

## 9. Alur Lengkap

### Create/Edit Sales

```
_handle_sales_save()
  └─ SalesItem.objects.create(...)
  └─ for tl in tax_lines_data:
       SalesTaxLine.objects.create(...)
  └─ process_sales_fifo(sales)
  └─ create_sales_automated_journals(sales)
       └─ jurnal utama: Dr payment_account | Cr revenue_account  (DPP saja)
       └─ for tax_line in si.tax_lines.all():
            sync_pajak(source_type='sales_item', ...)  →  PajakTransaksi (draft)
            confirm_pajak(pajak_trx)                   →  PajakTransaksi (final) + TRX-PAJ-XXXXXXXX
```

### Delete Sales

```
sales_delete()
  └─ _cancel_sales_pajak(sales)
       └─ batal_pajak(pt) untuk setiap PajakTransaksi source_type='sales_item'
            └─ reverse jurnal pajak (TRX-PAJ-XXXXXXXX)
  └─ reverse_sales_automated_journals(sales)
       └─ hapus jurnal utama
  └─ reverse_sales_fifo(sales)
  └─ sales.delete()
```

---

## 10. Testing

- `test_salestaxline_created_with_sales_item` — SalesTaxLine terbuat saat save sales
- `test_pajak_transaksi_created_on_journal` — `create_sales_automated_journals()` menghasilkan `PajakTransaksi` dengan `source_type='sales_item'`
- `test_no_inline_tax_journal` — jurnal utama tidak memiliki entry pajak inline
- `test_cancel_pajak_on_delete` — `sales_delete()` membatalkan semua `PajakTransaksi` dan membuat reversal journal pajak
- `test_multiple_tax_lines_per_item` — satu `SalesItem` dengan PPN + PPh 23 menghasilkan dua `PajakTransaksi`
- `test_is_manual_override` — `is_manual=True` + `tax=5000` → `PajakTransaksi.is_overridden=True`, `jumlah_pajak=5000`
- `test_invoice_tax_total_from_tax_lines` — invoice menghitung tax dari `tax_lines`, bukan `si.tax`
- `test_backward_compat_old_record` — record lama tanpa tax_lines → invoice fallback ke `si.tax`
