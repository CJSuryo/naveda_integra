# Posting Engine — Jenis Transaksi, Baris Jurnal, dan Pemetaan Akun

Date: 2026-07-15
Status: **Menggantikan** `2026-07-14-account-mapping-engine-design.md`
Dasar review: `2026-07-15-mapping-engine-design-review.md`

## Ringkasan perubahan dari spec 2026-07-14

| | Spec lama (2026-07-14) | Spec ini |
|---|---|---|
| Unit kerja | Akun (`role → akun`) | **Baris jurnal** (akun + arah + angka) |
| Jenis transaksi | Didefinisikan di kode (Pendekatan A) | **Disusun superuser lewat UI** (Pendekatan C) |
| Scope | Satu FK `entitas_bisnis` | **Rantai scope** (global → EB → Lv2/Lv3 → metode bayar → alasan) |
| Kunci | `(module, transaction_type, role)` | `(jenis_transaksi, baris)` — `module` hanya label UI |
| Generator jurnal | Tidak disentuh (tetap hardcoded) | **Dibongkar** jadi perulangan yang membaca konfigurasi |
| Riwayat perubahan | Tidak ada (`update_or_create` menimpa) | **Effective-dated, wajib** |
| Akses | `settings_view` (bisa diberikan ke user biasa) | **Superuser (vendor) saja** |

Yang **dipertahankan** dari spec lama: resolver sebagai satu-satunya pintu baca, strangler + fallback, STT tidak disentuh, tidak memindahkan FK yang genuinely per-record.

---

## 1. Model operasi

- **Superuser = vendor** (pemilik aplikasi Naveda). Ia yang menyusun jenis transaksi dan memetakan akun.
- **Klien = Entitas Bisnis.** Klien **tidak** menyentuh konfigurasi ini.
- Vendor memelihara **preset per jenis usaha** (F&B / Retail / Jasa) sebagai titik awal onboarding klien baru.

## 2. Pembagian tanggung jawab (batas keras)

> **Kode menyediakan bahan (angka). Superuser meracik resep (baris jurnal) lewat UI.**

| Pihak | Tanggung jawab |
|---|---|
| **Kode modul** | Memancarkan event; **mengumumkan angka apa saja yang tersedia**; menulis `JurnalDetail` dengan membaca konfigurasi |
| **Superuser (UI)** | Menyusun jenis transaksi: baris apa saja, tiap baris pakai **angka mana**, **debit/kredit**, dan **akun apa** |

Alasan batas ini: **setiap baris jurnal butuh angka, dan angka harus dihitung**. `service_charge = subtotal × pct`, `hpp = biaya batch FIFO`. Rumus tidak dapat diketik ke dropdown tanpa membangun bahasa pemrograman kedua di dalam UI — **ditolak** (tanpa debugger, tanpa tes, tidak dapat diaudit).

Yang **di luar** engine ini (tetap milik modul): Buy 1 Get 1, bundling, happy hour, voucher, loyalty, membership, cashback. Engine baru bekerja **setelah** modul memutuskan apa yang terjadi dan berapa angkanya.

## 3. Model data

### 3.1 Katalog angka (di kode)

Tiap modul mengumumkan angka yang bisa ia sediakan. Ini satu-satunya bagian yang butuh programmer saat menambah kemampuan baru.

```python
# apps/sales/posting.py
register_amounts(
    module='sales',
    label='Penjualan / Kasir',
    amounts=[
        Amount('subtotal',       'Subtotal Penjualan'),
        Amount('diskon',         'Diskon Penjualan'),
        Amount('service_charge', 'Service Charge'),
        Amount('tip',            'Tips'),
        Amount('pajak',          'PPN Keluaran'),
        Amount('pembulatan',     'Pembulatan',  signed=True),
        Amount('hpp',            'Harga Pokok Penjualan'),
        Amount('nilai_bayar',    'Nilai Pembayaran'),
    ],
    contexts=['entitas_bisnis', 'outlet', 'metode_bayar', 'item'],
)
```

`signed=True` → nilainya bisa positif atau negatif (pembulatan, selisih kas, laba/rugi pelepasan).

### 3.2 `JenisTransaksi` (tabel — disusun superuser)

| kolom | keterangan |
|---|---|
| `kode` | unik global, mis. `penjualan_kasir_fnb` |
| `label` | bahasa bisnis, mis. "Penjualan Kasir F&B" |
| `grup` | label pengelompokan UI, mis. "Penjualan" — **bukan** nama app Django |
| `module` | modul yang memancarkan; informasional, **bukan** bagian kunci |
| `entitas_bisnis` | null = template global vendor; terisi = khusus klien |
| `aktif` | |

**Catatan kunci:** `module` sengaja **bukan** bagian dari kunci. "Perolehan Aset Tetap" dipancarkan alur *purchase* tetapi tampil di grup "Aset Tetap" — event tidak dimiliki oleh modul pemegang master datanya.

### 3.3 `BarisJurnal` (tabel — disusun superuser)

Inilah pengganti "role". Bukan sekadar akun, melainkan resep satu baris jurnal.

| kolom | keterangan |
|---|---|
| `jenis_transaksi` | FK |
| `urutan` | |
| `label` | bahasa bisnis, tampil ke superuser, mis. "Pendapatan Barang Dagang" |
| `angka` | kode dari katalog §3.1, mis. `service_charge` |
| `arah` | `DEBIT` \| `KREDIT` \| `BERTANDA` |
| `sumber_akun` | `MAPPING` \| `DARI_ITEM` \| `DARI_KONTEKS` \| `DARI_MITRA` (lihat §3.5) |
| `scope_ref` | `default` \| `asal` \| `tujuan` (untuk mutasi antar cabang) |
| `lewati_bila_nol` | baris bernilai nol dihilangkan, tidak ditulis |
| `wajib` | |
| `kategori_akun` | daftar kategori CoA yang boleh dipilih (**tuple**, bukan satu nilai) |

Untuk `arah = BERTANDA`, baris punya **dua slot akun** — bukan satu akun dua arah:

- `akun_bila_kredit` → nilai positif (mis. **Laba** Pelepasan Aset, kategori pendapatan)
- `akun_bila_debit` → nilai negatif (mis. **Rugi** Pelepasan Aset, kategori beban)

Berlaku untuk: Laba/Rugi Pelepasan Aset, Pembulatan, Selisih Kas (over/short).

### 3.4 `PemetaanAkun` (tabel — akun per baris, per scope)

| kolom | keterangan |
|---|---|
| `baris_jurnal` | FK |
| `scope_tipe` | `global` \| `entitas_bisnis` \| `lv2` \| `lv3` \| `metode_bayar` \| `alasan` \| … |
| `scope_id` | null untuk `global` |
| `spesifisitas` | int — resolver memilih yang tertinggi |
| `akun` | FK ke `master_data.Akun`, `PROTECT` |
| `berlaku_mulai` | **effective-dated** — riwayat, bukan timpa |

**Scope sebagai rantai, bukan satu FK.** Ini yang membuat POS tidak jadi warga kelas dua: cascade Lv1→Lv3 dan akun per `PaymentMethod` yang **sudah berjalan** hari ini terpetakan tanpa kehilangan kemampuan. Menambah `scope_tipe` baru (gudang, sales channel, customer group) = menambah konstanta + spesifisitas, **tanpa migrasi**.

**"Alasan" adalah scope, bukan jenis transaksi baru.** Ini yang mencegah ledakan registry:

```
Penghapusan Persediaan → baris "Beban":
    global            → Beban Kerugian Persediaan
    alasan=rusak      → Beban Barang Rusak
    alasan=hilang     → Beban Kehilangan Persediaan
    alasan=expired    → Beban Barang Kadaluarsa
```

Satu jenis transaksi, N pemetaan. Yang bertambah adalah **baris data**, bukan definisi.

### 3.5 `sumber_akun` — akun tidak selalu dari mapping

| nilai | contoh baris |
|---|---|
| `MAPPING` | Pendapatan, PPN Keluaran, Service Charge, Tips, Pembulatan |
| `DARI_ITEM` | **Persediaan, HPP** — dari `item.coa_account` |
| `DARI_KONTEKS` | Kas/Bank — dari `PaymentMethod` terpilih |
| `DARI_MITRA` | Piutang Usaha — per customer/supplier |

**Kritis:** akun Persediaan/HPP **tidak boleh** dari mapping global. Ia harus dari master item (sudah dipakai: `si.inventory_account_id = si.item.coa_account_id`). Memaksanya lewat mapping akan **merusak akuntansi persediaan** — semua item bermuara ke satu akun.

## 4. Resolver & Poster

```python
resolve_baris(jenis_transaksi, konteks, tanggal) -> list[BarisTerisi]
# BarisTerisi = (akun, arah, kode_angka)
```

Urutan resolusi akun: scope paling spesifik → … → global → fallback (masa transisi) → error jelas.

Modul **tetap menulis `JurnalDetail` sendiri**, tetapi dengan perulangan:

```python
for baris in resolve_baris(jt, konteks, tanggal):
    nilai = angka[baris.kode_angka]
    if nilai == 0 and baris.lewati_bila_nol:
        continue
    JurnalDetail(jurnal_header=h, akun=baris.akun, debit=…, kredit=…)
```

**Ini menggantikan blok hardcoded** di `create_sales_automated_journals` (yang hari ini hanya mengenal HPP & Pendapatan). Tanpa pembongkaran ini, baris apapun yang disusun di UI tidak akan pernah muncul di jurnal.

## 5. Invarian yang dijaga

1. **Balance.** Σ debit = Σ kredit, divalidasi saat `JurnalHeader` di-post — siapapun yang membangun barisnya. Ini otomatis menangkap kesalahan tersering: ada angka yang tidak dipasangkan ke baris manapun (kasir menagih service charge, barisnya lupa dipasang → jurnal tidak balance → **ditolak**, bukan diam-diam salah).
2. **Fail loud.** Baris `wajib` tanpa akun → error jelas. Tidak pernah menjurnal separuh.
3. **Nol baris adalah hasil yang sah.** Mutasi antar cabang dengan akun persediaan yang sama menghasilkan nol baris. Bukan error.
4. **Effective-dated.** Mengubah pemetaan **tidak boleh** mengubah arti jurnal yang sudah terbit.
5. **Satu pintu untuk pemilihan akun** — bukan untuk penulisan jurnal. Dilarang: magic string, FK akun config baru di model domain.

## 6. UI (superuser only)

Klien EB **tidak melihat halaman ini** (atau maksimal read-only). Permission `settings_*` di spec lama terlalu longgar.

Tiga hal yang wajib ada:

- **Penyusun jenis transaksi** — tambah/hapus baris; dropdown "angka" **hanya menampilkan yang diumumkan modul** (§3.1), sehingga mustahil merujuk angka yang tidak ada.
- **Preview jurnal** — sebelum simpan: *"penjualan tunai Rp100.000 → D Kas 111.000 / K Pendapatan 100.000 / K Hutang PPN 11.000"*. Satu-satunya cara memverifikasi konfigurasi tanpa menjalankan transaksi sungguhan.
- **Preset & pewarisan** — Template Global (vendor) → Klien (EB) → Outlet (Lv2/Lv3). Preset F&B/Retail/Jasa untuk onboarding.

Grouping per `grup`, filter "belum di-set", indikator kelengkapan. Bukan matriks datar.

## 7. Non-goals

- **STT tidak disentuh** (tetap legacy). Tapi **jadwalkan pencabutannya** setelah Sales/Purchase pindah — jangan biarkan jadi mesin menganggur permanen.
- FK yang **genuinely per-record** (mis. `ModalDisetorDebit.akun`, dipilih user tiap transaksi) tetap FK — **tetapi wajib dideklarasikan** sebagai baris ber-`sumber_akun` input-user, agar form tahu field mana yang harus ditampilkan. Kalau tidak, ada dua sumber kebenaran.
- **Tax Rule / Approval / Workflow / Notification / Loyalty Rule** — tidak dibangun. Diikat kelak lewat katalog jenis transaksi yang sama.
- **Markup antar cabang di GL** — tidak. Dalam satu badan usaha, entitas tidak dapat memperoleh laba dari dirinya sendiri. Markup antar cabang adalah alat transfer pricing untuk penilaian kinerja → **lapisan pelaporan manajemen**, bukan jurnal. Jurnal tetap sebesar harga pokok.
- Bahasa aturan / DSL / scripting di UI.
- Hierarki jenis transaksi yang saling mewarisi (pewarisan cukup lewat rantai scope).

## 7a. Baris opsional = varian, bukan jenis transaksi baru

**Diputuskan 2026-07-15.** Baris yang "kadang ada, kadang tidak" (PPN, ongkos angkut, diskon, service charge, tips) adalah **varian di dalam satu jenis transaksi** — bukan jenis transaksi terpisah.

Mekanismenya **sudah tercakup `lewati_bila_nol`** (§3.3); **tidak ada tabel atau kolom baru**. Bila kondisinya tidak berlaku, modul mengirim angka **nol**, dan barisnya lenyap sendiri:

```
Jenis Transaksi: "Pembelian"   (satu-satunya, untuk semua kombinasi)
  persediaan       D   → (dari master item)
  ppn_masukan      D   → Pajak Masukan          ← nol bila non-PPN → hilang
  ongkos_angkut    D   → Beban Angkut Masuk     ← nol bila tidak ada → hilang
  hutang / kas     K   → (dari metode bayar)
```

Non-PPN tanpa angkut → 2 baris. PPN + angkut → 4 baris. **Satu konfigurasi, semua kombinasi.**

Bila dipecah menjadi jenis transaksi terpisah, Pembelian sendirian meledak menjadi belasan jenis transaksi hanya karena kombinasi PPN × angkut × retur — persis ledakan registry yang dihindari.

**Aturan pemisah (pakai ini saat ragu):**

| Situasi | Perlakuan |
|---|---|
| Baris **ada / tidak ada**, tergantung angkanya nol | **Varian** — pasang saja, `lewati_bila_nol` |
| Baris ada, tapi **akunnya berbeda** tergantung kondisi (PPN dapat dikreditkan vs tidak; alasan penghapusan) | **Scope** (§3.4) — satu baris, N pemetaan |
| **Arah / struktur** barisnya memang berbeda (Retur Pembelian, Refund) | **Jenis transaksi terpisah** |

Retur Pembelian **bukan** varian: bedanya bukan "ada baris bernilai nol", melainkan arah terbalik dan akun kontra tersendiri.

**Validasi UI yang menyertainya:** bila modul mengumumkan sebuah angka (§3.1) yang **tidak dikonsumsi baris manapun** pada suatu jenis transaksi, UI memperingatkan — karena bila angka itu kelak tidak nol, jurnal tidak akan balance. Peringatan saat menyusun, bukan kejutan saat kasir menutup transaksi.

## 8. Rollout

- **Tahap 0 — Fondasi.** Katalog angka, `JenisTransaksi`, `BarisJurnal`, `PemetaanAkun`, resolver, UI penyusun + preview. **Nol pemanggil produksi.**
- **Tahap 1 — Pilot: Penyusutan Aset Tetap.** Dua baris, balance nyata, magic string (`5.1.19` / `1.2.7`) sebagai fallback, angka dari skedul penyusutan. Cakupan terkurung rapat: satu-satunya jurnal yang dimiliki `aset_tetap`. **Perolehan aset tidak disentuh** (milik alur Purchase).
- **Tahap 2 — POS: Service Charge & Pembulatan.** Event yang **hari ini belum dijurnal sama sekali** → nol risiko regresi. Membuktikan tesis utama: menambah baris jurnal **tanpa mengubah kode posting**. Butuh pembongkaran `create_sales_automated_journals` (§4).
- **Tahap 3 — POS: penjualan & pembayaran** dipindah ke engine, cascade existing sebagai rantai scope, fallback aktif, uji kesetaraan jurnal.
- **Tahap 4 — Penghapusan (aset tetap & persediaan), mutasi antar cabang.**
- **Tahap 5 — Piutang, Pembelian; kebijakan modul baru.**

Aturan tiap tahap: fallback dulu → verifikasi jurnal identik → baru cabut fallback (strict). Tidak pernah ada momen modul rusak.

## 9. Testing

- **Resolver:** prioritas scope (spesifik > umum > global > fallback); effective-date memilih pemetaan yang berlaku pada tanggal jurnal, bukan yang terbaru.
- **Poster:** baris nol dilewati; baris `BERTANDA` positif→akun kredit, negatif→akun debit; jenis transaksi tanpa baris → nol `JurnalDetail`, bukan error.
- **Balance:** jurnal tidak balance ditolak; angka yang tidak dipasangkan ke baris manapun terdeteksi lewat balance.
- **Kesetaraan migrasi (per modul):** dengan fallback aktif, jurnal **identik** dengan sebelum migrasi.
- **Regresi STT:** alur purchase/sales/pendapatan berbasis STT tidak berubah.

## 10. Open questions

**Sudah diputuskan:**
- ~~Baris opsional — varian vs jenis transaksi terpisah~~ → **varian** (§7a). Tidak mengubah bentuk tabel.

**Masih terbuka (tidak menghalangi Tahap 0):**
- Lokasi app: `apps/posting` (baru) vs menumpang `jurnal`.
- Bentuk `konteks` yang dikirim modul ke resolver (dict vs dataclass).
- Apakah tiap cabang punya akun Persediaan sendiri di CoA — menentukan mutasi antar cabang menghasilkan **2 baris** atau **0 baris**. Tidak mengubah skema (rantai scope sudah menampung keduanya); baru relevan di Tahap 4.
