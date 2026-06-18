# Desain Modul Pajak — naveda_integra

**Tanggal:** 2026-06-19
**Status:** Disetujui — siap implementasi

---

## 1. Tujuan

Membangun `apps/pajak` sebagai **tax management hub** yang menjadi pusat seluruh logika perpajakan Indonesia dalam sistem naveda_integra. Modul ini:

- Menyimpan master data tarif pajak (editable tanpa deploy ulang)
- Menghitung pajak secara otomatis saat transaksi dikonfirmasi di modul lain
- Menyimpan ledger pajak per transaksi (`PajakTransaksi`)
- Membuat jurnal pajak terpisah (auditability)
- Mengizinkan intervensi manual jika diperlukan
- Menjadi titik integrasi semua modul yang mengandung komponen pajak

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

### Pola integrasi: Explicit Service Call (Opsi B)

Modul lain memanggil `pajak.services` secara eksplisit dari dalam service-nya sendiri. Tidak ada Django signal. Alur:

```
[Modul Asal].services.confirm_*()
  └─ for each item bertanda pajak:
       1. Buat jurnal utama (sudah ada di modul asal)
       2. pajak_trx = sync_pajak(source_type, item, tanggal)
       3. confirm_pajak(pajak_trx)  →  jurnal pajak dibuat
```

Saat void:
```
[Modul Asal].services.void_*()
  └─ for each PajakTransaksi terkait:
       batal_pajak(pajak_trx)  →  jurnal pajak di-reverse
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
jenis_pajak   CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
nama          CharField(max_length=100)
tarif_persen  DecimalField(max_digits=7, decimal_places=4)
berlaku_mulai DateField
berlaku_sampai DateField(null=True, blank=True)  # null = masih berlaku
keterangan    TextField(blank=True)
```

Query aktif: `TarifPajak.objects.filter(jenis_pajak=x, berlaku_mulai__lte=tgl).filter(Q(berlaku_sampai__gte=tgl) | Q(berlaku_sampai__isnull=True)).latest('berlaku_mulai')`

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
source_type   CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
              # 'pendapatan_kp', 'sales_item', 'purchase_item', 'piutang_item', ...
source_id     PositiveIntegerField(db_index=True)

# Masa pajak
masa_pajak    DateField(db_index=True)  # selalu disimpan sebagai YYYY-MM-01

# Pajak
jenis_pajak   CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
dpp           DecimalField(max_digits=19, decimal_places=4)
tarif_persen  DecimalField(max_digits=7, decimal_places=4)
jumlah_pajak  DecimalField(max_digits=19, decimal_places=4)

# Status
status        CharField(choices=['draft','final','disetor','dibatalkan'], default='draft')
is_overridden BooleanField(default=False)

# Akun
akun_pajak    FK → master_data.Akun
entitas_bisnis FK → entitas_bisnis.EntitasBisnis (null=True)

# Jurnal
jurnal_header FK → jurnal.JurnalHeader (null=True)

# Audit
created_at    DateTimeField(auto_now_add=True)
modified_by   FK → AUTH_USER_MODEL (null=True)
modified_at   DateTimeField(null=True)
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

`MasaPajak` dibuat otomatis (get_or_create) oleh `sync_pajak` saat pertama ada transaksi di masa tersebut.

---

## 5. Services

### 5.1 `get_tarif(jenis_pajak: str, tanggal: date) → Decimal`
Ambil `tarif_persen` aktif dari `TarifPajak`. Raise `TarifPajakTidakDitemukan` jika tidak ada.

### 5.2 `compute_pajak(jenis_pajak, dpp, tanggal, extra=None) → dict`
Engine kalkulasi sentral. Returns `{dpp_efektif, tarif_persen, jumlah_pajak}`.

Logika per jenis:
```
ppn_umum:
  dpp_efektif = Decimal('11') / Decimal('12') * dpp
  jumlah = dpp_efektif * Decimal('0.12')  # = 11% dari DPP asli

ppn_mewah:
  dpp_efektif = dpp
  jumlah = dpp * Decimal('0.12')

ppn_ekspor:
  jumlah = Decimal('0')

ppn_bm:
  tarif = get_tarif('ppn_bm', tanggal)  # varies by goods type
  jumlah = dpp * tarif / 100

pph_23_*:
  tarif = get_tarif(jenis_pajak, tanggal)
  jumlah = dpp * tarif / 100

pph_4_2_*:
  tarif = get_tarif(jenis_pajak, tanggal)
  jumlah = dpp * tarif / 100

pph_21_bukan_pegawai:
  pkp = dpp * Decimal('0.50')          # 50% × bruto
  jumlah = hitung_progresif(pkp, tanggal)

pph_umkm:
  jumlah = dpp * Decimal('0.005')      # 0.5%
  # Logika threshold Rp 500jt kumulatif (OP) dihandle di caller
```

### 5.3 `hitung_progresif(pkp, tanggal) → Decimal`
Iterasi `BracketPPhOP` yang berlaku pada `tanggal`, potong PKP per layer, sum hasilnya.

### 5.4 `sync_pajak(source_type, source_obj, tanggal) → PajakTransaksi`
Entry point generik. Dipanggil modul lain.

- Baca `jenis_pajak`, `dpp`, `akun_pajak` dari `source_obj`
- Jika `source_obj` sudah punya nilai pajak manual → gunakan sebagai `jumlah_pajak` dan set `is_overridden=True`
- Jika tidak → panggil `compute_pajak`
- `get_or_create` `MasaPajak` untuk bulan tersebut
- Buat `PajakTransaksi` status `draft`
- Return `PajakTransaksi`

### 5.5 `confirm_pajak(pajak_trx) → JurnalHeader`
- Set status `draft → final`
- Panggil `post_jurnal_pajak(pajak_trx)`
- Return `JurnalHeader` yang dibuat

### 5.6 `batal_pajak(pajak_trx)`
- Set status → `dibatalkan`
- Jika `jurnal_header` sudah ada: buat jurnal pembalik (reverse entry)

### 5.7 `override_pajak(pajak_trx, jumlah_baru, modified_by) → PajakTransaksi`
Intervensi manual:
- Reverse jurnal lama (jika ada)
- Update `jumlah_pajak = jumlah_baru`, `is_overridden = True`
- Set `modified_by`, `modified_at`
- Buat jurnal baru dengan nilai yang dioverride
- Return `PajakTransaksi`

### 5.8 `post_jurnal_pajak(pajak_trx) → JurnalHeader`
Buat `JurnalHeader` + `JurnalDetail` dengan mapping:

| Jenis Pajak | Debit | Kredit |
|-------------|-------|--------|
| PPN Keluaran (ppn_umum / ppn_mewah) | Piutang PPN / Kas | Utang PPN (`akun_pajak`) |
| PPh 23 dipotong oleh lawan (kita yang dipotong) | Piutang PPh 23 | Pendapatan (offset) |
| PPh 23 kita memotong | Beban jasa / biaya (bruto) | Utang PPh 23 (`akun_pajak`) |
| PPh 21 bukan pegawai | Beban honorarium | Utang PPh 21 (`akun_pajak`) |
| PPh 4(2) | Beban sewa/bunga (bruto) | Utang PPh 4(2) (`akun_pajak`) |
| PPh UMKM | Beban PPh | Utang PPh UMKM (`akun_pajak`) |

`akun_pajak` diambil dari `PajakTransaksi.akun_pajak` (diset oleh `sync_pajak` dari field `tax_account` source_obj, atau dari `TarifPajak.default_akun` jika tersedia).

---

## 6. Integrasi Modul

### 6.1 `apps/pendapatan` (phase ini)
`KewajibabPelaksanaan` sudah punya `tax`, `tax_type`, `tax_account`.

Mapping `tax_type` → `jenis_pajak`:
```python
TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}
```

Di `pendapatan.services.confirm_pendapatan(header)`:
```python
from apps.pajak.services import sync_pajak, confirm_pajak
for kp in header_kps_with_tax:
    pajak_trx = sync_pajak('pendapatan_kp', kp, header.tanggal)
    confirm_pajak(pajak_trx)
```

Di `pendapatan.services.void_pendapatan(header)`:
```python
from apps.pajak.services import batal_pajak
from apps.pajak.models import PajakTransaksi
for pt in PajakTransaksi.objects.filter(source_type='pendapatan_kp', source_id__in=kp_ids):
    batal_pajak(pt)
```

### 6.2 Modul lain (antrian)
Urutan integrasi yang direncanakan:
1. `apps/pendapatan` — phase ini
2. `apps/sales` — berikutnya
3. `apps/purchase`
4. `apps/piutang`
5. `apps/utang`

Setiap modul baru hanya perlu: menambahkan `source_type` baru ke `SOURCE_TYPE_CHOICES` dan memanggil `sync_pajak` / `confirm_pajak` / `batal_pajak` di service-nya.

---

## 7. Views & URL

| View | URL | Deskripsi |
|------|-----|-----------|
| `PajakTransaksiListView` | `/pajak/transaksi/` | Ledger, filter masa/jenis/status |
| `PajakTransaksiEditView` | `/pajak/transaksi/<id>/edit/` | Form intervensi manual (override) |
| `MasaPajakListView` | `/pajak/masa/` | Daftar masa pajak + status |
| `MasaPajakDetailView` | `/pajak/masa/<tahun>/<bulan>/` | Summary masa pajak, tombol lock |
| `TarifPajakListView` | `/pajak/tarif/` | Daftar tarif aktif |
| `TarifPajakCreateView` | `/pajak/tarif/tambah/` | Tambah tarif baru |

URL prefix: `/pajak/` didaftarkan di `naveda_integra/urls.py`.

---

## 8. Data Seed

Perlu initial data (migration atau fixture) untuk:

**`TarifPajak` (berlaku_mulai = 2025-01-01):**
- `ppn_umum` → 12% (dengan DPP nilai lain 11/12, efektif 11%)
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

- `test_compute_pajak_ppn_umum` — verifikasi 11/12 × DPP logic
- `test_compute_pajak_pph_21_bukan_pegawai` — verifikasi 50% × PKP progresif
- `test_sync_pajak_pendapatan_kp` — integrasi: KP confirmed → PajakTransaksi terbuat
- `test_override_pajak` — verifikasi reverse jurnal + nilai baru
- `test_batal_pajak` — verifikasi jurnal pembalik
- `test_tarif_berlaku_historis` — tarif lama tetap dipakai untuk tanggal lama
- `test_masa_pajak_autocreate` — MasaPajak dibuat otomatis

---

## 10. Keputusan Desain & Alasan

| Keputusan | Alasan |
|-----------|--------|
| Explicit service call, bukan signal | Mudah di-trace, di-test, konsisten dengan pola existing |
| `source_type + source_id` bukan `GenericFK` | Konsisten dengan codebase, tidak perlu `contenttypes` framework |
| Jurnal pajak terpisah dari jurnal utama | Auditability: jurnal utama dan pajak cross-reference via `PajakTransaksi.jurnal_header` |
| `TarifPajak` di DB bukan hardcode | Perubahan regulasi (e.g. tarif PMK baru) tidak butuh deploy |
| PPh 21 pegawai tetap out of scope | Modul HR/penggajian belum ada; akan diintegrasikan di phase HR |
