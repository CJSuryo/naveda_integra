# Account Mapping Engine — Transaction Settings per Modul per Jenis Transaksi

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

- **Status sistem: campuran.** Modul panas (data riil): Purchase & Inventory, Sales & Pendapatan/Piutang, Aset Tetap & Aset Lainnya. Modul dingin: Ekuitas, POS/Kasir. Migrasi dimulai dari modul dingin.
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
- **Tahap 1 — Pilot dingin: Ekuitas.** Registry Ekuitas, pindahkan pemilihan akun `ekuitas/services.py` ke resolver dengan fallback lama. Isi mapping via UI, tes end-to-end, lalu cabut fallback (strict).
- **Tahap 2 — Aset Tetap & Aset Lainnya.** Registry + resolver dengan fallback = magic string lama. Setelah admin isi mapping & hasil jurnal cocok dengan sebelumnya → cabut fallback.
- **Tahap 3 — Piutang/Ekuitas FK bertebaran & modul panas lain (opsional, paling akhir).** Kasus per kasus: yang murni config akun default pindah ke mapping; yang per-record tetap FK di record.
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
