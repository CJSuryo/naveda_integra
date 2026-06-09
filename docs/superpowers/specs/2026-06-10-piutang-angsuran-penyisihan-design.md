# Piutang: Angsuran Jangka Panjang + Aging Fix + Penyisihan Piutang

**Date:** 2026-06-10  
**Status:** Approved  
**Scope:** `apps/piutang/`

---

## 1. Latar Belakang

Modul piutang perlu tiga perbaikan utama:

1. **Installment (Bunga & Angsuran)** — Piutang jangka panjang (wesel tagih) belum mendukung jenis bunga, suku bunga, dan tabel angsuran seperti di modul utang.
2. **Aging Fix** — `get_piutang_aging()` saat ini hanya menggunakan `jatuh_tempo` header. Untuk piutang berangsuran, setiap baris angsuran harus masuk ke bucket aging berdasarkan tanggal angsurannya masing-masing.
3. **Penyisihan Piutang** — Belum ada mekanisme jurnal cadangan kerugian piutang (allowance for doubtful accounts) sesuai SAK. Rate per bucket harus configurable, dengan dua mode: per-piutang manual dan batch akhir periode.

---

## 2. Keputusan Desain

| Topik | Keputusan |
|-------|-----------|
| Schedule computation | Computed on-the-fly (mirror utang pattern), tidak persisted ke DB |
| Aging basis | Per-baris angsuran untuk long_term; fallback ke `jatuh_tempo` header untuk short_term |
| Penyisihan rate | Configurable via `PenyisihanRateConfig` model (1 baris per bucket) |
| Jurnal penyisihan | Keduanya: per-piutang (manual) dan batch akhir periode |
| Batch logic | Delta adjustment: target saldo − saldo existing akun cadangan |
| Double-counting prevention | Flag `is_specifically_impaired` pada `PiutangHeader` |

---

## 3. Data Model

### 3.1 `PiutangHeader` — tambah field

```python
jenis_bunga = CharField(
    max_length=20,
    choices=[('tanpa_bunga','Tanpa Bunga'),('flat','Flat'),('anuitas','Anuitas (Efektif)')],
    default='tanpa_bunga',
)
suku_bunga = DecimalField(max_digits=8, decimal_places=4, default=0)  # % per tahun
periode_angsuran = CharField(
    max_length=20,
    choices=[('bulanan','Bulanan'),('triwulanan','Triwulanan'),('semesteran','Semesteran'),('tahunan','Tahunan')],
    default='bulanan',
)
is_specifically_impaired = BooleanField(default=False)
```

`jumlah_angsuran` tidak disimpan — di-derive dari rentang (`tanggal` → `jatuh_tempo`) dibagi `periode_angsuran` saat runtime, konsisten dengan `utang/services.py`.

Fields bunga/angsuran hanya relevan saat `jenis_jangka_waktu == 'long_term'` dan `jatuh_tempo` diisi.

### 3.2 `PenyisihanRateConfig` — model baru

```python
class PenyisihanRateConfig(models.Model):
    bucket_key   = CharField(max_length=20, unique=True)
    # values: 'current','1_30','31_60','61_90','91_180','181_365','over_365'
    label        = CharField(max_length=100)
    rate_percent = DecimalField(max_digits=5, decimal_places=2)  # 0.00–100.00
    urutan       = PositiveSmallIntegerField()  # ordering
```

Default seeded via data migration:

| bucket_key | label | rate_percent |
|------------|-------|-------------|
| current | Belum Jatuh Tempo | 0.00 |
| 1_30 | Lewat 1–30 Hari | 5.00 |
| 31_60 | Lewat 31–60 Hari | 15.00 |
| 61_90 | Lewat 61–90 Hari | 25.00 |
| 91_180 | Lewat 91–180 Hari | 50.00 |
| 181_365 | Lewat 181–365 Hari | 75.00 |
| over_365 | Lewat > 365 Hari | 100.00 |

### 3.3 `PiutangPenyisihan` — model baru

```python
class PiutangPenyisihan(models.Model):
    JENIS_CHOICES = [('manual','Manual (Per-Piutang)'), ('batch','Batch Akhir Periode')]

    piutang_header  = FK(PiutangHeader, null=True, blank=True, related_name='penyisihan_entries')
    # null = batch entry
    tanggal         = DateField()
    jenis           = CharField(max_length=10, choices=JENIS_CHOICES)
    jumlah          = DecimalField(max_digits=19, decimal_places=4)
    # positif = beban penyisihan, negatif = pemulihan
    allowance_account = FK(Akun, related_name='piutang_penyisihan_allowance')
    expense_account   = FK(Akun, related_name='piutang_penyisihan_expense')
    jurnal_header   = FK(JurnalHeader, null=True, blank=True)
    catatan         = CharField(max_length=512, blank=True)
    created_by      = FK(User, null=True, blank=True)
    created_at      = DateTimeField(auto_now_add=True)
```

### 3.4 `PiutangAuditLog` — tambah action

Tambah `'PENYISIHAN'` ke `ACTION_CHOICES`.

---

## 4. Service Logic (`piutang/services.py`)

### 4.1 `compute_angsuran_schedule(piutang)` — fungsi baru

Mirror `utang/services.py::compute_angsuran_schedule()`:

- Input: `PiutangHeader`
- Return: `list[dict]` dengan keys: `{no, tanggal, pokok, bunga, angsuran, sisa_pokok, paid, sisa_bayar, status}`
- Status per-baris: `'lunas' | 'sebagian' | 'jatuh_tempo' | 'akan_datang'`
- Support `jenis_bunga`: `tanpa_bunga` (flat principal), `flat` (flat interest), `anuitas`
- Payment matching: direct via `PiutangPenerimaan.angsuran_no`; unallocated pool fills in order
- Helper `_add_months()` dan `_PERIODE_MONTHS_MAP` dicopy dari utang services

Fungsi ini **tidak** dipanggil di list view — hanya di detail view dan saat compute penyisihan.

### 4.2 `get_piutang_aging()` — refactor

```
Output: dict[bucket_key → list[AgingEntry]]
AgingEntry: {piutang, angsuran_no, tanggal_angsuran, jumlah, hari_lewat}
```

Logika:
```
for piutang in PiutangHeader.filter(status in ['open','partial','overdue']):
    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        schedule = compute_angsuran_schedule(piutang)
        for row in schedule:
            if row['status'] != 'lunas':
                bucket = _classify_bucket(row['tanggal'], today)
                buckets[bucket].append(AgingEntry(piutang, row['no'], row['tanggal'], row['sisa_bayar']))
    else:
        # fallback: short_term atau tidak ada schedule
        bucket = _classify_bucket(piutang.jatuh_tempo, today)
        buckets[bucket].append(AgingEntry(piutang, None, piutang.jatuh_tempo, piutang.sisa_piutang))
```

`_classify_bucket(tanggal, today)` → 7-bucket classification berdasarkan hari lewat dari `tanggal`.

### 4.3 `compute_penyisihan_for_piutang(piutang)` — fungsi baru

```
- Ambil rates dari PenyisihanRateConfig (cache in-memory per request)
- Untuk tiap unpaid entry dari aging logic:
    penyisihan += jumlah * rate_percent / 100
- Return: {total_penyisihan, breakdown: [{bucket_key, label, jumlah_piutang, rate, penyisihan}]}
```

### 4.4 `create_penyisihan_journal(piutang, allowance_account, expense_account, tanggal, catatan, user)` — fungsi baru

```
1. compute_penyisihan_for_piutang(piutang) → total
2. Buat JurnalHeader nomor 'TRX-PIU-PSH-XXXX'
3. JurnalDetail: Dr expense_account / Cr allowance_account, jumlah = total
4. Buat PiutangPenyisihan(jenis='manual', piutang_header=piutang, ...)
5. Set piutang.is_specifically_impaired = True
6. _log(piutang, 'PENYISIHAN', ...)
```

### 4.5 `compute_batch_penyisihan(tanggal, allowance_account)` — fungsi baru

```
1. Ambil semua piutang aktif WHERE is_specifically_impaired=False
2. Expand per-angsuran via aging logic
3. Sum semua → target_saldo
4. Baca saldo akun allowance_account dari JurnalDetail sampai tanggal
   (sum(debit) - sum(kredit) untuk akun kontra-aset, atau sesuai normal balance akun)
5. delta = target_saldo - saldo_existing
6. Return {target_saldo, saldo_existing, delta, breakdown_per_bucket, piutang_count}
```

### 4.6 `create_batch_penyisihan_journal(batch_data, allowance_account, expense_account, tanggal, catatan, user)` — fungsi baru

```
1. Validasi batch_data.delta != 0
2. Jika delta > 0: Dr expense_account / Cr allowance_account (tambah cadangan)
   Jika delta < 0: Dr allowance_account / Cr expense_account (pemulihan)
3. Buat JurnalHeader nomor 'TRX-PIU-PSH-B-XXXX'
4. Buat PiutangPenyisihan(jenis='batch', piutang_header=None, jumlah=delta, ...)
```

### 4.7 `get_piutang_dashboard_kpi()` — modifikasi

Tambah ke return dict:
- `total_penyisihan_target` — sum penyisihan semua piutang aktif
- `piutang_neto` — total_outstanding − total_penyisihan_target
- `aging_summary` — `{bucket_key: {total_outstanding, rate, penyisihan}}` untuk dashboard chart

---

## 5. Views & URLs

### 5.1 URL Baru

```python
path('<int:pk>/penyisihan/', views.piutang_penyisihan_create, name='penyisihan_create'),
path('<int:pk>/penyisihan/<int:ppk>/cancel/', views.piutang_penyisihan_cancel, name='penyisihan_cancel'),
path('reports/penyisihan/', views.piutang_report_penyisihan, name='report_penyisihan'),
path('settings/penyisihan-rates/', views.piutang_settings_rates, name='settings_rates'),
```

### 5.2 Views Baru

**`piutang_penyisihan_create(request, pk)`**
- POST only
- Validasi: piutang harus status aktif, belum `is_specifically_impaired`
- Call `create_penyisihan_journal()`
- Redirect ke detail

**`piutang_penyisihan_cancel(request, pk, ppk)`**
- POST only
- Reverse jurnal (Dr/Cr swap), hapus `PiutangPenyisihan` record
- Set `is_specifically_impaired=False` jika tidak ada manual penyisihan lain
- Redirect ke detail

**`piutang_report_penyisihan(request)`**
- GET: render preview batch (compute_batch_penyisihan preview)
- POST: call `create_batch_penyisihan_journal()`
- Context: `batch_preview`, `form`, `history` (recent batch entries)

**`piutang_settings_rates(request)`**
- GET/POST: edit `PenyisihanRateConfig` formset (semua 7 baris)

### 5.3 Views Modifikasi

**`piutang_detail`** — tambah context:
```python
angsuran_schedule = (
    compute_angsuran_schedule(piutang)
    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo
    else []
)
penyisihan_preview = compute_penyisihan_for_piutang(piutang)
penyisihan_form = PiutangPenyisihanForm()
penyisihan_history = piutang.penyisihan_entries.select_related('jurnal_header').order_by('-tanggal')
```

**`piutang_create` / `piutang_update`** — tambah `jenis_bunga`, `suku_bunga`, `periode_angsuran` ke form handling.

---

## 6. Forms

### `PiutangHeaderForm` — tambah fields
```python
fields += ['jenis_bunga', 'suku_bunga', 'periode_angsuran']
# jenis_bunga: Select widget
# suku_bunga: NumberInput, step=0.01, min=0
# periode_angsuran: Select widget
```

### `PiutangPenyisihanForm` — baru
```python
fields: [tanggal, allowance_account, expense_account, catatan]
allowance_account queryset: Akun.filter(kategori_id='kewajiban')
expense_account queryset: Akun.filter(kategori_id='beban')
```

### `BatchPenyisihanForm` — baru
```python
fields: [tanggal, allowance_account, expense_account, catatan]
# Sama struktur dengan PiutangPenyisihanForm
```

### `PenyisihanRateConfigFormSet` — baru
```python
modelformset_factory(PenyisihanRateConfig, fields=['rate_percent'], extra=0)
```

---

## 7. Templates

### `piutang/form.html` — modifikasi
Tambah section "Bunga & Angsuran" yang hanya tampil saat `jenis_jangka_waktu == 'long_term'`:
- `jenis_bunga` select
- `suku_bunga` input (hide jika `jenis_bunga == 'tanpa_bunga'`)
- `periode_angsuran` select
- JS show/hide: `DOMContentLoaded` + `change` event pada `jenis_jangka_waktu` dan `jenis_bunga`

### `piutang/detail.html` — modifikasi
Tambah 2 card section:

**Tabel Angsuran** (conditional: `angsuran_schedule` not empty):
- Header: "Tabel Angsuran — N angsuran — Periode"
- Tabel: No, Tanggal, Pokok, Bunga, Angsuran, Sisa Pokok, Status
- Row class: `ni-row--success` (lunas), `ni-row--danger` (jatuh_tempo)

**Penyisihan Piutang** (selalu tampil untuk piutang aktif):
- Badge `is_specifically_impaired` jika sudah disisihkan khusus
- Preview estimasi: tabel bucket → jumlah, rate%, estimasi penyisihan
- Tombol "Buat Jurnal Penyisihan" → modal form (disable jika `is_specifically_impaired`)
- Riwayat: tabel `penyisihan_history` dengan link ke jurnal

### `piutang/report_aging.html` — rombak total
- Tabel per-bucket dengan detail per-row (piutang, no angsuran, tanggal, jumlah, hari lewat)
- Summary footer per bucket: subtotal outstanding, rate%, estimasi penyisihan
- Grand total row
- Tombol "Buat Jurnal Penyisihan Batch" → redirect ke `report_penyisihan`

### `piutang/report_penyisihan.html` — baru
- Tabel preview batch: per-bucket summary + delta calculation
- Form `BatchPenyisihanForm`
- Riwayat batch entries (recent `PiutangPenyisihan.objects.filter(jenis='batch')`)

### `piutang/settings_rates.html` — baru
- Tabel edit `PenyisihanRateConfig` formset
- Kolom: Bucket, Label, Rate (%)

---

## 8. Migrations

1. `0001` (atau next) — AddField ke `PiutangHeader`: `jenis_bunga`, `suku_bunga`, `periode_angsuran`, `is_specifically_impaired`
2. `0002` — CreateModel `PenyisihanRateConfig` + `PiutangPenyisihan`
3. `0003` — Data migration: seed 7 baris default `PenyisihanRateConfig`

---

## 9. Constraints & Business Rules

1. **Schedule hanya computed** untuk `jenis_jangka_waktu == 'long_term'` dan `jatuh_tempo` tidak null.
2. **`is_specifically_impaired`** — set `True` saat manual penyisihan dibuat; set `False` saat dibatalkan (jika tidak ada entry lain). Piutang dengan flag ini dikecualikan dari batch calculation.
3. **Batch delta** — batch journal = target_saldo − saldo_existing. Bisa positif (beban) atau negatif (pemulihan). Jika delta = 0, tidak ada jurnal yang dibuat.
4. **Saldo akun cadangan** — dibaca dari `JurnalDetail` aggregate (sum kredit − sum debit untuk akun kontra-aset) sampai tanggal perhitungan.
5. **Penyisihan per-piutang** hanya bisa dibuat untuk piutang status `open`, `partial`, atau `overdue`.
6. **Rate config** tidak boleh < 0 atau > 100. `over_365` default 100% sesuai SAK; pemilik bisnis bisa ubah tapi form memberi warning jika di-set < 100%.

---

## 10. Out of Scope

- Effective dating untuk `PenyisihanRateConfig` (bisa ditambah fase berikutnya)
- Multi-dimensional rates (per kategori pelanggan / cabang)
- Export laporan aging ke PDF/Excel
- Auto-trigger batch penyisihan via cron/scheduler
