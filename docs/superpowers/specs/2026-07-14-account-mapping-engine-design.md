# Account Mapping Engine — Transaction Settings per Modul per Jenis Transaksi

> ## ⚠️ SUPERSEDED — jangan dikerjakan
>
> Digantikan oleh **`2026-07-15-posting-engine-design.md`** setelah design review
> (`2026-07-15-mapping-engine-design-review.md`).
>
> Ringkas alasannya: spec ini menjawab *"akun mana yang dipakai"*, padahal kendala
> sesungguhnya adalah *"baris jurnal apa saja yang lahir dari sebuah kejadian bisnis,
> di sisi mana, senilai berapa"*. Ia tidak dapat menjurnal Service Charge, Tips,
> Pembulatan, Diskon, Retur, atau Refund — dan tidak akan pernah bisa, karena arah
> debit/kredit dan sumber angka tetap terkunci di kode.
>
> Tiga keputusan di dokumen ini dibatalkan secara eksplisit:
> - **Pendekatan A** (jenis transaksi hanya di kode) → menjadi **Pendekatan C**: superuser
>   (vendor) menyusun jenis transaksi lewat UI; kode hanya menyediakan angkanya.
> - **Scope = satu FK `entitas_bisnis`** → menjadi **rantai scope** (global → EB → Lv2/Lv3 →
>   metode bayar → alasan). Scope tunggal adalah **regresi** bagi POS, yang cascade-nya sudah
>   lebih kaya hari ini.
> - **`module` sebagai bagian kunci** → `module` hanya label UI. Event tidak dimiliki oleh
>   modul pemegang master datanya (perolehan aset tetap dipancarkan alur *purchase*).
>
> Yang **dipertahankan** dan diteruskan ke spec baru: resolver sebagai satu-satunya pintu baca,
> strangler + fallback, STT tidak disentuh, FK genuinely per-record tidak dipindah.

Date: 2026-07-14

## Background

Otomatisasi pemilihan akun ("mapping") saat ini tersebar dalam tiga pola yang tidak saling terkoordinasi, sehingga sulit dikelola dan rapuh:

1. **`SubTransactionType` (STT)** — `apps/purchase/models.py:213`. Satu tabel lebar dengan kolom peran akun yang fixed & mostly-null (`default_offset_account`, `default_revenue_account`, `default_payment_account`, `default_inventory_account`, `default_tax_account`). `module` di-hardcode hanya `purchase`/`sales`/`pendapatan`. Menambah peran akun baru = kolom baru + migration.
2. **Magic string `kode_akun`** — mis. `apps/aset_tetap/services.py:170`: `Akun.objects.filter(kode_akun__startswith='5.1.19')`. Putus bila CoA dinomori ulang.
3. **FK akun bertebaran di model domain** — mis. `apps/piutang/models.py` punya ~17 kolom `_account` di banyak model.

`JurnalAutomasi`/`JurnalAutomasiAkun` (`apps/jurnal/models.py:120`) hanya "nama + daftar akun" untuk template Jurnal Manual — bukan mapping otomatis per modul.

## Goal

Menyediakan **satu rumah tunggal** untuk memetakan akun secara otomatis **per modul per jenis transaksi**, yang robust (menambah peran tidak butuh migration), konsisten (kode konsumen dan UI setting bersumber dari definisi yang sama), dan aman dimigrasi (tanpa pernah merusak modul yang berjalan).

## Non-goals

- **STT tidak disentuh.** Semua transaksi existing yang memakai STT (purchase, sales, pendapatan) tetap berjalan apa adanya. Tidak ada backfill STT, tidak ada pencabutan kolom `default_*_account`, tidak ada perubahan alur panas STT.
- Tidak memindahkan FK akun yang benar-benar bersifat **per-record** (nilai per transaksi tertentu) ke mapping — hanya "config akun default per jenis transaksi" yang pindah.
- Tidak menambah level hierarki CoA baru.

## Keputusan desain yang sudah dikunci

- **Status sistem: campuran.** Modul panas (data riil): Purchase & Inventory, Sales & Pendapatan/Piutang, Aset Tetap & Aset Lainnya. Modul rendah-risiko untuk pilot: Ekuitas. Migrasi dimulai dari Ekuitas.
  - **Catatan hasil audit kode (2026-07-14):** karakterisasi awal "modul dingin = tanpa otomatisasi akun" tidak akurat untuk semua modul yang disebut di atas — sudah diverifikasi langsung ke kode:
    - **Ekuitas bukan 100% manual.** Sisi kredit "Modal Disetor" pakai magic-string (`Akun.objects.filter(kode_akun__startswith='3.1.1').first()`, `apps/ekuitas/services.py:112`) — pola yang sama persis dengan masalah Aset Tetap, hanya beda modul. Sisi debit (`ModalDisetorDebit.akun`) genuinely per-record (dipilih bebas via autocomplete tiap transaksi) — ini **tidak** dipindah ke mapping, tetap FK manual sesuai Non-goals.
    - **Piutang bukan murni "FK bertebaran".** `PiutangDetail.sub_transaction_type` (`apps/piutang/models.py:358`) juga FK ke `SubTransactionType` — Piutang adalah hybrid STT + 17 kolom `_account` manual per-record, bukan murni pola 3.
    - **Inventory tidak punya logika akun sendiri sama sekali** (nol referensi `Akun`/`kode_akun` di seluruh `apps/inventory/`) — 100% numpang `SubTransactionType.default_inventory_account` milik Purchase. Pemasangan "Purchase & Inventory" sebagai satu modul panas tetap benar, tapi otomatisasinya murni milik Purchase.
    - **POS/Kasir BUKAN modul dingin.** `MerchantPOSConfig` (`apps/pos_config/models.py:7-40`) sudah punya sistem cascading override 3-tingkat (Lv3→Lv2→Lv1, lewat `resolve_pos_config()` di `apps/pos_config/utils.py:4-34`) untuk `revenue_account`, `offset_coa_account`, `default_payment_account`, dan `sub_transaction_type` — arsitekturnya mirip resolver mapping engine ini sendiri (scope-cascade + fallback). Migrasi POS berarti **merekonsiliasi sistem cascade yang sudah berjalan**, bukan mulai dari kosong seperti Ekuitas — risikonya lebih tinggi dari asumsi awal. POS karena itu dikeluarkan dari kandidat pilot tahap awal (lihat Tahap 3, bukan Tahap 1).
- **Cakupan per-EB:** mapping bisa berbeda per Entitas Bisnis, dengan default global. Kunci: `(module, transaction_type, role, entitas_bisnis-nullable)`; `entitas_bisnis=NULL` = default global, EB terisi = override.
- **Pendekatan A (registry deklaratif di kode)**, bukan B (role didefinisikan user via UI). Daftar modul/jenis transaksi/peran ditulis programmer di registry; UI hanya mengisi akun ke slot yang sudah pasti benar. Ini mencegah "beda persepsi" role antara kode dan UI, dan memungkinkan validasi kelengkapan.
- **Target mesin baru:** mengambil alih bagian jelek non-STT (magic string aset tetap/lainnya; FK config bertebaran piutang/ekuitas/pos) secara bertahap dengan fallback, **dan** menjadi standar wajib untuk semua modul baru. STT dibiarkan legacy.
- **Akses admin-only.** Halaman Transaction Settings di-gate permission admin; tidak muncul di menu user biasa.

## Design

### 1. Model data

Dua konsep: satu tabel generik untuk data, satu registry di kode untuk definisi yang valid.

**`AccountMapping`** (tabel — lokasi: app baru `mapping`, atau app `jurnal`; diputuskan saat planning):

| kolom | tipe | keterangan |
|---|---|---|
| `module` | CharField | kode modul, mis. `'aset_tetap'` |
| `transaction_type` | CharField | kode jenis transaksi, mis. `'penyusutan'` |
| `role` | CharField | kode peran akun, mis. `'beban_penyusutan'` |
| `entitas_bisnis` | FK ke `entitas_bisnis.EntitasBisnis`, **null=True** | `NULL` = default global; terisi = override per EB |
| `akun` | FK ke `master_data.Akun`, `on_delete=PROTECT` | akun terpilih |

- `unique_together = (module, transaction_type, role, entitas_bisnis)`.
- Index pada `(module, transaction_type, role)` untuk lookup resolver.

**Registry (di kode, bukan tabel)** — mendefinisikan modul/jenis transaksi/peran yang valid dan men-drive UI + validasi:

```python
# apps/<modul>/mapping.py
register_mapping(
    module='aset_tetap',
    transaction_types=[('penyusutan', 'Penyusutan'), ('pelepasan', 'Pelepasan Aset')],
    roles=[
        Role('beban_penyusutan',     label='Beban Penyusutan',     kategori='beban', required=True),
        Role('akumulasi_penyusutan', label='Akumulasi Penyusutan', kategori='aset',  required=True),
    ],
)
```

- `Role.kategori` membatasi dropdown akun di UI ke kategori CoA yang sesuai.
- `Role.required` menandai peran yang wajib di-set (dipakai indikator UI & strict-mode resolver).
- Registry di-load saat app siap (mis. di `AppConfig.ready()`), disimpan di registry pusat yang bisa dibaca UI & resolver.

### 2. Resolver — satu-satunya pintu baca mapping

Semua modul memanggil fungsi ini; tidak ada modul yang query `AccountMapping` langsung.

```python
# apps/<mapping-app>/resolver.py
def resolve_account(module, transaction_type, role, entitas_bisnis=None, *, fallback=None):
    """
    Urutan pencarian:
      1. mapping khusus EB ini      (entitas_bisnis=<eb>)
      2. mapping default global     (entitas_bisnis=NULL)
      3. fallback (kalau diberi)    -> perilaku lama modul
      4. strict: raise error yang jelas; non-strict: None
    """
```

Perilaku kunci:

- **Validasi registry saat resolve.** Bila `module`/`transaction_type`/`role` tidak terdaftar di registry → raise error saat development. Mencegah role yang salah ketik/lupa daftar diam-diam.
- **Fallback opsional** untuk masa transisi:

  ```python
  beban = resolve_account(
      'aset_tetap', 'penyusutan', 'beban_penyusutan', eb,
      fallback=lambda: Akun.objects.filter(kode_akun__startswith='5.1.19').first(),
  )
  ```

  Selama mapping belum diisi admin, sistem memakai perilaku lama → tidak gagal.
- **Strict-mode** setelah modul selesai dimigrasi & mapping terisi: fallback dicabut; bila mapping wajib kosong → error jelas (`"Mapping 'beban_penyusutan' untuk Aset Tetap belum di-set"`), bukan jurnal salah diam-diam.
- **Caching per-request** agar resolve berulang dalam satu transaksi tidak berkali-kali query DB.

### 3. Halaman Transaction Settings (UI, admin-only)

Satu halaman baru yang **membaca registry** lalu merender matriks; struktur mengikuti registry tiap modul (bukan form statis).

```
Transaction Settings                    [ Entitas Bisnis: v Semua (Default Global) ]

> Aset Tetap
    Penyusutan
      Beban Penyusutan        [ 5.1.19 Beban Penyusutan v ]   (set)
      Akumulasi Penyusutan    [ 1.2.7  Akm. Penyusutan   v ]   (set)
    Pelepasan Aset
      Laba/Rugi Pelepasan     [ -- belum di-set --       v ]   (! wajib)

> Ekuitas
    Modal Disetor
      Kas/Bank Penerima       [ 1.1.1 Kas                v ]   (set)
      Akun Modal              [ 3.1.1 Modal Disetor      v ]   (set)
```

Perilaku:

- **Dropdown akun difilter** oleh `Role.kategori` (registry) dan oleh `EntitasBisnisAkun` bila EB tertentu dipilih.
- **Selector Entitas Bisnis** di atas: "Default Global" mengisi baris `entitas_bisnis=NULL`; memilih EB tertentu mengisi/override untuk EB itu (peran yang belum di-override ditampilkan pudar sebagai "warisan dari global").
- **Indikator status:** peringatan untuk peran `required` yang belum di-set — konsisten dengan strict-mode resolver.
- **Simpan** = upsert baris `AccountMapping` via AJAX (pola sama dengan modal CoA yang sudah ada).
- **Tidak ada** tombol "tambah peran/modul" — daftar murni dari registry (inti Pendekatan A).

### 4. Rollout bertahap (strangler)

Prinsip: satu modul selesai-tuntas sebelum lanjut; modul dingin dulu; fallback dulu, strict belakangan.

- **Tahap 0 — Fondasi.** Model `AccountMapping`, sistem registry (`register_mapping`, `Role`), `resolve_account`, halaman Transaction Settings (admin-gated). Belum ada modul yang memanggil resolver → nol risiko. Tes unit resolver.
- **Tahap 1 — Pilot: Ekuitas (sisi kredit Modal Disetor saja).** Registry Ekuitas dengan satu role (mis. `akun_modal_disetor`), pindahkan lookup `Akun.objects.filter(kode_akun__startswith='3.1.1')` di `ekuitas/services.py:112` ke resolver dengan fallback lama. Isi mapping via UI, tes end-to-end, lalu cabut fallback (strict). Sisi debit (`ModalDisetorDebit.akun`) **tidak** disentuh — tetap FK manual per-record.
- **Tahap 2 — Aset Tetap & Aset Lainnya.** Registry + resolver dengan fallback = magic string lama. Setelah admin isi mapping & hasil jurnal cocok dengan sebelumnya → cabut fallback.
- **Tahap 3 — Piutang (FK bertebaran), POS/Kasir (rekonsiliasi cascade existing), & modul panas lain (opsional, paling akhir).** Kasus per kasus:
  - **Piutang:** dari 17 kolom `_account`, yang murni "config akun default per jenis transaksi" pindah ke mapping; yang genuinely per-record (mis. hasil input user per transaksi) tetap FK di record.
  - **POS/Kasir:** **bukan migrasi dari nol.** `MerchantPOSConfig`/`resolve_pos_config()` sudah berfungsi dengan cascade Lv3→Lv2→Lv1. Rencana migrasi perlu memetakan cascade itu ke skema `AccountMapping` (kemungkinan `entitas_bisnis` sebagai satu-satunya scope alih-alih 3 level) tanpa memutus alur kasir yang aktif — butuh sub-plan tersendiri, dievaluasi terpisah dari Piutang.
- **Tahap 4 — Kebijakan modul baru.** Dokumentasikan: modul baru wajib lewat registry + resolver; dilarang magic string / FK config baru.

Aturan yang berlaku di semua tahap: STT tidak disentuh; tidak pernah ada momen modul rusak; tiap tahap punya gerbang tes sendiri; bila meragukan, berhenti dan diskusi.

## Testing

- **Resolver (unit):** prioritas EB-override > global > fallback; error saat `module`/`transaction_type`/`role` tak terdaftar; strict-mode menghasilkan pesan error yang jelas saat mapping wajib kosong.
- **Kesetaraan migrasi (per modul):** dengan fallback aktif dan mapping belum diisi, jurnal yang dihasilkan **identik** dengan sebelum migrasi.
- **Strict-mode (per modul):** setelah fallback dicabut, mapping kosong menghasilkan error yang benar, mapping terisi menghasilkan akun yang benar.
- **UI:** matriks merender sesuai registry; dropdown terfilter kategori & EB; upsert per-EB dan global tidak saling menimpa; peran required yang kosong ditandai.
- **Regresi STT:** alur purchase/sales/pendapatan berbasis STT tidak berubah sama sekali.

## Open questions (diputuskan saat planning)

- Lokasi model & resolver: app baru `mapping` vs menambah ke `jurnal`.
- Bentuk permission admin: `@staff_member_required` vs permission Django khusus.
