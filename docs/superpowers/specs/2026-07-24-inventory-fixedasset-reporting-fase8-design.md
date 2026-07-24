# Design — Fase 8: Pelaporan Inventory & Aset Tetap

**Tanggal:** 2026-07-24
**Status:** Disetujui (siap ke plan)
**Roadmap induk:** `docs/superpowers/specs/2026-07-15-inventory-fixedassets-review-and-roadmap.md` (FASE 8)
**Ruang lingkup:** Lapisan pelaporan read-only untuk modul Inventory & Aset Tetap. Tidak ada perubahan model/migrasi.

---

## 1. Tujuan & Latar Belakang

Roadmap FASE 8 meminta: Stock Card, Inventory Movement, Inventory Valuation, Laporan HPP, Slow/Fast Moving, dan Asset Register per kategori/lokasi/departemen.

Sebagian sudah ada dari fase sebelumnya:
- **Kartu Stok** — `inventory.stock_card` ([apps/inventory/views.py:527](../../apps/inventory/views.py))
- **Buku Persediaan (Inventory Movement)** — `inventory.stock_ledger` (views.py:483)
- **Laporan Persediaan** — `inventory.laporan_persediaan` (komprehensif, masih baca legacy `InventoryRecord`/`FIFOBatch`)
- **Laporan Penyusutan** per kategori/lokasi/departemen — `aset_tetap.laporan_penyusutan` ([apps/aset_tetap/reports.py:37](../../apps/aset_tetap/reports.py))
- **Depreciation Schedule** — `aset_tetap.depreciation_schedule`

Yang benar-benar belum ada / lemah dan menjadi fokus Fase 8:
1. **Inventory Valuation** khusus (bersumber `StockMovement`, bukan tabel legacy).
2. **Laporan HPP/COGS** (bersumber `StockConsumption` + gerakan `sale_out`).
3. **Slow/Fast Moving** memakai `velocity_category` + metrik aktual.
4. **Asset Register** sebagai halaman laporan tersendiri (bukan sekadar daftar admin), terfilter per dimensi.
5. **Reports hub** — satu halaman landing untuk semua laporan Inventory & Aset Tetap.

## 2. Prinsip & Keputusan Desain

- **Sumber data valuasi/HPP = `StockMovement` / `StockConsumption`** (single source of truth, prinsip P1 roadmap). Laporan legacy `laporan_persediaan` dibiarkan apa adanya — tidak dimigrasikan pada fase ini.
- **Pisahkan lapisan laporan dari CRUD**: fungsi query/agregasi murni di `reports.py` (tanpa HTTP, dapat diuji unit), meniru pola `aset_tetap/reports.py`. View tipis memanggilnya, menerapkan filter EB, lalu render.
- **Tanpa perubahan model/migrasi.** `velocity_category` tetap field manual (`fast`/`medium`/`slow`/`dead`); laporan hanya menampilkan realita terhitung di sebelahnya.
- **Isolasi EB** memakai pola yang ada: `_get_eb_tree(user)` dan `_resolve_eb_lv1_ids(list, user)` dari `apps.purchase.views`.
- **Export** mengikuti pola `inventory_export` (CSV) dan `inventory_export_pdf` (template ramah-cetak).

## 3. Komponen & Kontrak

### 3.1 `apps/inventory/reports.py` (baru)

Fungsi murni, mengembalikan struktur data (list of dict / dataclass), tanpa `request`.

```
valuation_report(eb_lv1_ids, *, warehouse_id=None, tipe_item=None, as_of=None)
    -> {'rows': [{item, kategori, warehouse, on_hand_qty, unit_cost_avg, total_value}],
        'subtotals_kategori': {...}, 'subtotals_warehouse': {...}, 'grand_total_value': Decimal}
    Sumber: StockMovement layer remaining_qty>0, tanggal<=as_of. Nilai = Σ remaining_qty*unit_cost.

hpp_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *, warehouse_id=None)
    -> {'rows': [{item, kategori, qty_terjual, total_hpp, revenue|None}],
        'subtotals_kategori': {...}, 'grand_total_hpp': Decimal}
    Sumber: StockMovement movement_type='sale_out' pada rentang, join StockConsumption
    untuk biaya layer-akurat. return_customer pada rentang mengurangi qty & hpp.

velocity_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *, warehouse_id=None,
                velocity_filter=None)
    -> [{item, velocity_category, qty_keluar, jumlah_gerakan, hari_sejak_keluar_terakhir,
         on_hand, mismatch_flag}]
    Sumber: gerakan outflow pada rentang + on-hand saat ini. mismatch_flag=True bila
    tag velocity tak cocok realita (mis. 'fast' tapi qty_keluar==0).
```

Catatan as-of: valuasi memakai state layer saat ini yang difilter `tanggal<=as_of`. Untuk `as_of=hari ini` hasilnya eksak; untuk tanggal lampau bersifat aproksimasi (tidak me-rewind konsumsi). Batasan ini didokumentasikan di UI.

### 3.2 `apps/aset_tetap/reports.py` (tambah fungsi)

```
asset_register(eb_lv1_ids, *, kategori_id=None, lokasi_id=None, departemen_id=None,
               pic=None, status=None, group_by='kategori')
    -> {'rows': [{aset, kode, nama, kategori, lokasi, departemen, pic, tgl_perolehan,
                  harga_perolehan, akumulasi_penyusutan, nilai_buku, status, kondisi}],
        'subtotals': {<group_key>: {harga_perolehan, akumulasi, nilai_buku}},
        'grand_total': {...}}
    Sumber: AsetTetapRecord + akumulasi penyusutan berjalan.
```

### 3.3 View & URL

Inventory (`apps/inventory/`):
- `laporan_hub` → `inventory:laporan_hub` — halaman kartu tautan semua laporan.
- `laporan_valuasi` → `inventory:laporan_valuasi`
- `laporan_hpp` → `inventory:laporan_hpp`
- `laporan_velocity` → `inventory:laporan_velocity`

Aset Tetap (`apps/aset_tetap/`):
- `laporan_register` → `aset_tetap:laporan_register`

Tiap view laporan mendukung `?export=csv` dan `?export=pdf`.

### 3.4 Template

`templates/inventory/`: `laporan_hub.html`, `laporan_valuasi.html`, `laporan_hpp.html`, `laporan_velocity.html`, plus partial cetak bersama `_laporan_print.html`.
`templates/aset_tetap/`: `laporan_register.html`.

Semua meniru gaya filter + tabel dari `stock_ledger.html` / `laporan_penyusutan.html` (kelas `ni-*`, filter EB tree, tombol export).

### 3.5 Navigasi (`templates/base.html`)

- Submenu Inventory: tambah tautan **Hub Laporan** (mengarah ke `laporan_hub`) di atas Laporan Persediaan.
- Submenu Aset Tetap: tambah tautan **Laporan** (Register + Penyusutan).

## 4. Aliran Data

`request` → view → resolve EB ids via `_resolve_eb_lv1_ids` → panggil fungsi `reports.py` → (a) render HTML, (b) `?export=csv` streaming `HttpResponse` CSV, atau (c) `?export=pdf` render template cetak. Fungsi `reports.py` tidak pernah menyentuh `request`.

## 5. Penanganan Error & Edge Case

- Tanpa filter item/EB: laporan tetap tampil (agregasi seluruh EB yang boleh diakses user), dengan peringatan bila data besar tak difilter.
- Item tanpa layer / tanpa gerakan: baris dihilangkan dari valuasi (on_hand 0) tetapi tetap muncul di velocity bila punya tag (agar dead stock terdeteksi).
- Rentang tanggal terbalik / kosong: default rentang = bulan berjalan; validasi ringan di view.
- `return_customer` pada rentang HPP: mengurangi qty & total_hpp (retur = pembalik penjualan).

## 6. Pengujian

`apps/inventory/tests_fase8.py` & `apps/aset_tetap/tests_fase8_register.py`:
- Valuasi: seed beberapa layer inflow + sebagian terkonsumsi → total_value = Σ remaining_qty*unit_cost yang dihitung tangan.
- HPP: satu penjualan FIFO lintas 2 layer → total_hpp = angka terverifikasi; retur mengurangi.
- Velocity: item tag 'fast' tanpa gerakan → mismatch_flag True; item ber-gerakan → metrik benar.
- Isolasi EB: laporan cabang A tak memuat data cabang B.
- Asset register: subtotal per kategori = Σ nilai buku; filter lokasi/departemen/status bekerja.
- Export CSV: header + jumlah baris sesuai data.

## 7. Di Luar Lingkup (YAGNI)

- Rewind valuasi historis sejati (menelusuri tiap konsumsi mundur).
- Grafik/chart — laporan tabular saja.
- Migrasi `laporan_persediaan` off legacy (tetap seperti sekarang).
- Perubahan skema apa pun.

## 8. Urutan Implementasi (ringkas)

1. `inventory/reports.py` + tests (valuation, hpp, velocity).
2. `aset_tetap/reports.py` `asset_register` + tests.
3. View + URL + template inventory (valuasi, hpp, velocity) dengan export.
4. View + URL + template asset register dengan export.
5. Reports hub + integrasi menu `base.html`.
6. Verifikasi (test suite + smoke check halaman).
