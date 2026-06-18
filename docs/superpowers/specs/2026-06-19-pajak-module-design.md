# Desain Modul Pajak — naveda_integra

**Tanggal:** 2026-06-19
**Revisi:** 2 — 2026-06-19 (koreksi post_jurnal_pajak, tambah akun_lawan + sifat_pajak, sentralisasi total)
**Status:** Disetujui — siap implementasi

---

## 1. Tujuan

Membangun `apps/pajak` sebagai **tax management hub** yang menjadi pusat seluruh logika perpajakan Indonesia dalam sistem naveda_integra.

### Prinsip Sentralisasi Total
**Semua logika pajak — kalkulasi, jurnal, pelaporan — hanya ada di modul pajak.** Modul lain (pendapatan, sales, purchase, piutang, utang) tidak boleh membuat jurnal pajak sendiri. Modul lain hanya bertanggung jawab atas:
1. Jurnal utama transaksi (DPP saja, tanpa komponen pajak)
2. Memanggil `pajak.services.sync_pajak(...)` dan `confirm_pajak(...)`

Ini berarti **existing code di modul lain yang saat ini menangani pajak akan di-refactor** untuk menyerahkan semua tax logic ke modul pajak.

Modul ini:
- Menyimpan master data tarif pajak (editable tanpa deploy ulang)
- Menghitung pajak secara otomatis saat transaksi dikonfirmasi di modul lain
- Menyimpan ledger pajak per transaksi (`PajakTransaksi`)
- Membuat jurnal pajak terpisah (auditability)
- Mengizinkan intervensi manual jika diperlukan

**Regulasi dasar:** UU No. 7/2021 (HPP), PP No. 55/2022, PP No. 58/2023, PP No. 20/2026, PMK No. 131/2024, PMK No. 11/2025.

---

## 2. Scope Pajak

### Dalam scope (phase ini)
| Kode | Nama | Dasar Hukum |
|------|------|-------------|
| `ppn_umum` | PPN BKP/JKP non-mewah (11% efektif) | PMK 131/2024 Pasal 3 |
| `ppn_mewah` | PPN BKP mewah (12%) | PMK 131/2024 Pasal 2 |
| `ppn_ekspor` | PPN Ekspor (0%) | UU PPN |
| `ppn_bm` | PPnBM (10%–200%) | UU No. 42/2009 |
| `pph_23_jasa` | PPh 23 Jasa (2%) | Pasal 23 UU PPh |
| `pph_23_royalti` | PPh 23 Royalti (15%) | Pasal 23 UU PPh |
| `pph_23_dividen` | PPh 23 Dividen (15%) | Pasal 23 UU PPh |
| `pph_21_bukan_pegawai` | PPh 21 Tenaga Ahli/Bukan Pegawai | PP 58/2023, PMK 168/2023 |
| `pph_4_2_sewa` | PPh 4(2) Sewa Tanah/Bangunan (10%) | PP 29/1996 |
| `pph_4_2_bunga` | PPh 4(2) Bunga Deposito (20%) | PP 131/2000 |
| `pph_umkm` | PPh Final UMKM (0,5%) | PP 55/2022, PP 20/2026 |

### Luar scope (dijadwalkan phase berikutnya)
- **PPh 21 Pegawai Tetap** — menunggu modul HR/penggajian
- **PPh Badan tahunan** — modul pelaporan tahunan terpisah
- **PPh OP tahunan** — sama

---

## 3. Arsitektur

### Pola integrasi: Explicit Service Call

Modul lain memanggil `pajak.services` secara eksplisit. Tidak ada Django signal.

**Alur konfirmasi:**
```
[Modul Asal].services.confirm_*()
  └─ for each item:
       1. Buat jurnal utama (DPP saja — tanpa komponen pajak)
       2. if item.tax_type:
            pajak_trx = sync_pajak(source_type, item, tanggal)
            confirm_pajak(pajak_trx)  →  buat jurnal pajak terpisah
```

**Alur void:**
```
[Modul Asal].services.void_*()
  └─ PajakTransaksi.objects.filter(source_type=..., source_id__in=ids)
       → batal_pajak(pt) untuk setiap record  →  reverse jurnal pajak
```

### Struktur file
```
apps/pajak/
├── models.py
├── services.py
├── views.py
├── urls.py
├── forms.py
├── admin.py
└── migrations/
```

---

## 4. Models

### 4.1 `TarifPajak`
Master data tarif. Mendukung perubahan regulasi dengan `berlaku_mulai/sampai`.

```python
jenis_pajak    CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
nama           CharField(max_length=100)
tarif_persen   DecimalField(max_digits=7, decimal_places=4)
berlaku_mulai  DateField
berlaku_sampai DateField(null=True, blank=True)  # null = masih berlaku
keterangan     TextField(blank=True)
```

Query aktif:
```python
TarifPajak.objects
    .filter(jenis_pajak=x, berlaku_mulai__lte=tgl)
    .filter(Q(berlaku_sampai__gte=tgl) | Q(berlaku_sampai__isnull=True))
    .latest('berlaku_mulai')
```

### 4.2 `BracketPPhOP`
Layer tarif progresif Pasal 17 untuk perhitungan PPh 21 bukan pegawai.

```python
batas_bawah   DecimalField(max_digits=19, decimal_places=0)
batas_atas    DecimalField(max_digits=19, decimal_places=0, null=True)  # null = tak terbatas
tarif_persen  DecimalField(max_digits=5, decimal_places=2)
berlaku_mulai DateField
```

Data seed (berlaku mulai 2022-01-01):
- 0 – 60.000.000 → 5%
- 60.000.001 – 250.000.000 → 15%
- 250.000.001 – 500.000.000 → 25%
- 500.000.001 – 5.000.000.000 → 30%
- > 5.000.000.000 → 35%

### 4.3 `PajakTransaksi`
Ledger pajak per line item. Satu record per komponen pajak per item transaksi.

```python
# Source reference (lightweight generic FK)
source_type    CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
               # 'pendapatan_kp', 'sales_item', 'purchase_item', 'piutang_item', ...
source_id      PositiveIntegerField(db_index=True)

# Masa pajak
masa_pajak     DateField(db_index=True)  # selalu disimpan sebagai YYYY-MM-01

# Pajak
jenis_pajak    CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
dpp            DecimalField(max_digits=19, decimal_places=4)
tarif_persen   DecimalField(max_digits=7, decimal_places=4)
jumlah_pajak   DecimalField(max_digits=19, decimal_places=4)

# Sifat pajak — menentukan arah jurnal
sifat_pajak    CharField(max_length=20, choices=[
                   ('potong_pungut', 'Potong/Pungut'),   # Dr akun_lawan | Cr akun_pajak
                   ('prepaid', 'Prepaid/Dipotong Lawan'), # Dr akun_pajak  | Cr akun_lawan
               ])

# Status
status         CharField(choices=['draft','final','disetor','dibatalkan'], default='draft')
is_overridden  BooleanField(default=False)

# Akun — keduanya wajib diisi oleh sync_pajak
akun_pajak     FK → master_data.Akun  # sisi pajak: Utang PPN, Utang PPh, Uang Muka PPh
akun_lawan     FK → master_data.Akun  # sisi offset: Piutang, Utang Usaha, Kas, Beban

entitas_bisnis FK → entitas_bisnis.EntitasBisnis (null=True)

# Jurnal
jurnal_header  FK → jurnal.JurnalHeader (null=True)

# Audit
created_at     DateTimeField(auto_now_add=True)
modified_by    FK → AUTH_USER_MODEL (null=True)
modified_at    DateTimeField(null=True)
```

Index: `(source_type, source_id)`, `(masa_pajak, jenis_pajak)`, `(status,)`

### 4.4 `MasaPajak`
Container period. Dipakai untuk lock dan summary reporting.

```python
tahun   PositiveSmallIntegerField
bulan   PositiveSmallIntegerField  # 1–12
status  CharField(choices=['open','locked'], default='open')

class Meta:
    unique_together = ('tahun', 'bulan')
```

`MasaPajak` dibuat otomatis (get_or_create) oleh `sync_pajak`.

---

## 5. Services

### 5.1 `get_tarif(jenis_pajak: str, tanggal: date) → Decimal`
Ambil `tarif_persen` aktif dari `TarifPajak`. Raise `TarifPajakTidakDitemukan` jika tidak ada.

### 5.2 `compute_pajak(jenis_pajak, dpp, tanggal) → dict`
Engine kalkulasi sentral. Returns `{dpp_efektif, tarif_persen, jumlah_pajak}`.

```
ppn_umum:
  dpp_efektif = Decimal('11') / Decimal('12') * dpp
  jumlah = dpp_efektif * Decimal('0.12')         # = 11% efektif dari DPP asli

ppn_mewah:
  dpp_efektif = dpp
  jumlah = dpp * Decimal('0.12')

ppn_ekspor:
  jumlah = Decimal('0')

ppn_bm / pph_23_* / pph_4_2_*:
  tarif = get_tarif(jenis_pajak, tanggal)
  jumlah = dpp * tarif / 100

pph_21_bukan_pegawai:
  pkp = dpp * Decimal('0.50')                    # 50% × bruto
  jumlah = hitung_progresif(pkp, tanggal)

pph_umkm:
  jumlah = dpp * Decimal('0.005')                # 0.5%
```

### 5.3 `hitung_progresif(pkp, tanggal) → Decimal`
Iterasi `BracketPPhOP` yang berlaku pada `tanggal`, potong PKP per layer, sum hasilnya.

### 5.4 `sync_pajak(source_type, source_obj, tanggal, akun_pajak, akun_lawan, sifat_pajak) → PajakTransaksi`
Entry point generik. Dipanggil modul lain saat konfirmasi.

- Baca `jenis_pajak`, `dpp` dari `source_obj`
- Jika `source_obj` sudah punya nilai pajak manual (`kp.tax > 0`) → gunakan sebagai `jumlah_pajak`, set `is_overridden=True`
- Jika tidak → panggil `compute_pajak`
- `get_or_create` `MasaPajak` untuk bulan transaksi
- Buat dan return `PajakTransaksi` status `draft`

Akun pajak dan akun lawan dikirim eksplisit oleh caller (modul asal yang tahu konteks akun transaksinya).

### 5.5 `confirm_pajak(pajak_trx) → JurnalHeader`
- Validasi status `draft`
- Set status → `final`
- Panggil `post_jurnal_pajak(pajak_trx)`
- Return `JurnalHeader`

### 5.6 `batal_pajak(pajak_trx)`
- Set status → `dibatalkan`
- Jika `jurnal_header` sudah ada: buat `JurnalHeader` pembalik (swap debit/kredit)

### 5.7 `override_pajak(pajak_trx, jumlah_baru, modified_by) → PajakTransaksi`
Intervensi manual:
1. Jika jurnal sudah ada → batal_pajak (reverse)
2. Update `jumlah_pajak = jumlah_baru`, `is_overridden = True`, `modified_by`, `modified_at`
3. Set status → `final`
4. Buat jurnal baru dengan nilai yang dioverride
5. Return `PajakTransaksi`

### 5.8 `post_jurnal_pajak(pajak_trx) → JurnalHeader`
Membuat `JurnalHeader` + dua `JurnalDetail`. Arah jurnal dikontrol oleh `sifat_pajak`:

```python
if pajak_trx.sifat_pajak == 'potong_pungut':
    akun_debit  = pajak_trx.akun_lawan   # Kas, Piutang, Utang Usaha, Beban
    akun_kredit = pajak_trx.akun_pajak   # Utang PPN, Utang PPh
else:  # 'prepaid'
    akun_debit  = pajak_trx.akun_pajak   # Uang Muka PPh
    akun_kredit = pajak_trx.akun_lawan   # Piutang Usaha
```

Hasilnya:
```
Dr. akun_debit   jumlah_pajak
  Cr. akun_kredit  jumlah_pajak
```

#### Tabel mapping per konteks

| Konteks | jenis_pajak | sifat_pajak | akun_pajak | akun_lawan |
|---------|-------------|-------------|------------|------------|
| Pendapatan — PPN tagih ke klien | ppn_umum / ppn_mewah | potong_pungut | Utang PPN | Kas / Piutang |
| Pendapatan — PPh 23 dipotong klien | pph_23_jasa | prepaid | Uang Muka PPh 23 | Piutang Usaha |
| Pendapatan — PPh 21 dipotong klien | pph_21_bukan_pegawai | prepaid | Uang Muka PPh 21 | Piutang Usaha |
| Pendapatan — PPh 4(2) dipotong klien | pph_4_2_sewa | prepaid | Uang Muka PPh 4(2) | Piutang Usaha |
| Purchase — PPh 23 kita potong vendor | pph_23_jasa | potong_pungut | Utang PPh 23 | Utang Usaha |
| Purchase — PPh 21 kita potong vendor | pph_21_bukan_pegawai | potong_pungut | Utang PPh 21 | Utang Usaha |
| Purchase — PPh 4(2) kita potong | pph_4_2_sewa | potong_pungut | Utang PPh 4(2) | Utang Usaha |
| UMKM — PPh atas pendapatan sendiri | pph_umkm | potong_pungut | Utang PPh UMKM | Beban PPh Final |
| Ekspor | ppn_ekspor | potong_pungut | — | — (jumlah=0, no journal) |

**Catatan:** Untuk `ppn_ekspor`, `jumlah_pajak = 0` sehingga tidak ada `JurnalDetail` yang dibuat, tapi `PajakTransaksi` tetap dibuat untuk kelengkapan laporan.

---

## 6. Integrasi Modul & Refactoring Existing Code

### Prinsip umum
Setiap modul yang di-refactor harus:
1. Menghapus semua tax logic dari `confirm_*` service-nya
2. Memastikan jurnal utama hanya booking DPP (tanpa pajak)
3. Memanggil `sync_pajak + confirm_pajak` setelah jurnal utama selesai

### 6.1 `apps/pendapatan` (phase ini — refactoring required)

**Yang harus diubah di `pendapatan/services.py`:**

`_create_kp_journal` saat ini:
```python
# SEBELUM — tax embedded dalam jurnal utama:
debit_total = amount + tax_amount
Dr. debit_acct  (amount + tax)
  Cr. credit_acct (amount)
  Cr. tax_account (tax)         # ← HAPUS ini
```

`_create_kp_journal` setelah refactor:
```python
# SESUDAH — jurnal utama hanya DPP:
Dr. debit_acct  (amount)
  Cr. credit_acct (amount)
# Hapus parameter include_tax, hapus blok if has_tax
```

**Mapping `tax_type` lama → `jenis_pajak` baru:**
```python
TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}
```

**Penentuan `sifat_pajak` di context pendapatan:**
- `ppn_keluaran` → `potong_pungut` (kita pungut PPN dari klien)
- `pph_23`, `pph_21`, `pph_4_2` → `prepaid` (klien memotong dari pembayaran ke kita)

**Panggilan di `confirm_pendapatan`:**
```python
from apps.pajak.services import sync_pajak, confirm_pajak

# Setelah _create_kp_journal:
if kp.tax_type and kp.tax_account_id:
    jenis = TAX_TYPE_MAP.get(kp.tax_type)
    sifat = 'potong_pungut' if kp.tax_type == 'ppn_keluaran' else 'prepaid'
    akun_lawan = pay_acct  # Kas/Piutang — sama dengan debit_acct jurnal utama
    pajak_trx = sync_pajak(
        source_type='pendapatan_kp',
        source_obj=kp,
        tanggal=header.tanggal,
        akun_pajak=kp.tax_account,
        akun_lawan=akun_lawan,
        sifat_pajak=sifat,
    )
    confirm_pajak(pajak_trx)
```

**Panggilan di `void_pendapatan`:**
```python
from apps.pajak.services import batal_pajak
from apps.pajak.models import PajakTransaksi

kp_ids = list(KewajibabPelaksanaan.objects.filter(
    pendapatan_eb__pendapatan_header=header
).values_list('id', flat=True))

for pt in PajakTransaksi.objects.filter(source_type='pendapatan_kp', source_id__in=kp_ids):
    batal_pajak(pt)
```

### 6.2 Modul lain (antrian integrasi)

| Urutan | Modul | Catatan |
|--------|-------|---------|
| 1 | `apps/pendapatan` | Phase ini |
| 2 | `apps/sales` | PPh 23 / PPN atas penjualan |
| 3 | `apps/purchase` | PPh 21/23/4(2) kita memotong |
| 4 | `apps/piutang` | PPN terkait piutang usaha |
| 5 | `apps/utang` | PPh terkait utang usaha |

Setiap modul baru hanya perlu:
- Tambah `source_type` ke `SOURCE_TYPE_CHOICES` di `pajak/models.py`
- Panggil `sync_pajak / confirm_pajak / batal_pajak` di service-nya
- Hapus tax logic yang ada dari service-nya sendiri

---

## 7. Views & URL

| View | URL | Deskripsi |
|------|-----|-----------|
| `PajakTransaksiListView` | `/pajak/transaksi/` | Ledger, filter masa/jenis/status/sifat |
| `PajakTransaksiEditView` | `/pajak/transaksi/<id>/edit/` | Form intervensi manual (override) |
| `MasaPajakListView` | `/pajak/masa/` | Daftar masa pajak + status |
| `MasaPajakDetailView` | `/pajak/masa/<tahun>/<bulan>/` | Summary masa pajak, tombol lock |
| `TarifPajakListView` | `/pajak/tarif/` | Daftar tarif aktif |
| `TarifPajakCreateView` | `/pajak/tarif/tambah/` | Tambah tarif baru |

URL prefix: `/pajak/` didaftarkan di `naveda_integra/urls.py`.

---

## 8. Data Seed

Perlu initial data (migration data) untuk:

**`TarifPajak` (berlaku_mulai = 2025-01-01):**
- `ppn_umum` → 12% (DPP nilai lain 11/12, efektif 11%)
- `ppn_mewah` → 12%
- `pph_23_jasa` → 2%
- `pph_23_royalti` → 15%
- `pph_23_dividen` → 15%
- `pph_4_2_sewa` → 10%
- `pph_4_2_bunga` → 20%
- `pph_umkm` → 0.5%

**`BracketPPhOP` (berlaku_mulai = 2022-01-01):**
Lima layer sesuai Pasal 17 UU PPh jo. UU HPP.

---

## 9. Testing

- `test_compute_pajak_ppn_umum` — verifikasi 11/12 × DPP logic, jumlah = 11% dari DPP asli
- `test_compute_pajak_pph_21_bukan_pegawai` — verifikasi 50% × PKP progresif
- `test_sync_pajak_pendapatan_kp_ppn` — KP confirmed → PajakTransaksi potong_pungut terbuat
- `test_sync_pajak_pendapatan_kp_pph23` — KP confirmed → PajakTransaksi prepaid terbuat
- `test_post_jurnal_potong_pungut` — Dr akun_lawan, Cr akun_pajak
- `test_post_jurnal_prepaid` — Dr akun_pajak, Cr akun_lawan
- `test_override_pajak` — reverse jurnal + nilai baru + jurnal baru
- `test_batal_pajak` — jurnal pembalik (swap debit/kredit)
- `test_tarif_berlaku_historis` — tarif lama dipakai untuk tanggal lama
- `test_masa_pajak_autocreate` — MasaPajak dibuat otomatis
- `test_pendapatan_confirm_no_double_journal` — jurnal utama DPP saja, jurnal pajak terpisah, total balance

---

## 10. Keputusan Desain & Alasan

| Keputusan | Alasan |
|-----------|--------|
| Sentralisasi total — semua pajak di modul pajak | Konsistensi, auditability, single source of truth untuk kewajiban pajak |
| Refactor `_create_kp_journal` hapus `include_tax` | Jurnal utama hanya DPP; mencegah double-count saat pajak module aktif |
| `akun_pajak` + `akun_lawan` + `sifat_pajak` | Tiga field ini cukup untuk menentukan arah jurnal apapun tanpa conditional logic kompleks |
| `sifat_pajak`: `potong_pungut` vs `prepaid` | Membedakan liability (Utang PPh) dari prepaid asset (Uang Muka PPh) — kritis untuk balance sheet |
| Jurnal pajak terpisah dari jurnal utama | Cross-reference via `PajakTransaksi.jurnal_header`; memudahkan rekonsiliasi masa pajak |
| Explicit service call, bukan signal | Mudah di-trace, di-test, konsisten dengan pola existing |
| `source_type + source_id` bukan `GenericFK` | Konsisten dengan codebase, tidak perlu `contenttypes` framework |
| `TarifPajak` di DB bukan hardcode | Perubahan regulasi tidak butuh deploy ulang |
| PPh 21 pegawai tetap out of scope | Modul HR/penggajian belum ada; akan diintegrasikan di phase HR |
