# Fase 6 — Transaksi & Kontrol Stok — Design

**Tanggal:** 2026-07-17
**Status:** Disetujui — siap ke tahap perencanaan (writing-plans)
**Fase induk:** Roadmap Inventory & Fixed Assets §Fase 6 (Medium)
**Prasyarat terpenuhi:** Fase 1 (UOM), Fase 2 (`StockMovement` + Warehouse + isolasi EB), Fase 3 (costing FIFO/LIFO/Average) sudah live.
**Di luar cakupan:** Fase 5 (mapping COA per kategori) di-skip — akun jurnal lawan dipilih user per transaksi.

---

## A. Tujuan

Membangun transaksi & kontrol stok operasional **di atas `StockMovement` ledger yang sudah ada** — tanpa ledger baru, tanpa merombak perilaku costing/isolasi EB yang sudah benar. Enam sub-fitur:

1. Stock Adjustment (koreksi manual + jurnal penyesuaian)
2. Stock Opname (hitung fisik → posting selisih)
3. Transfer antar gudang/cabang (jurnal antar-akun bila lintas entitas)
4. Retur pelanggan & retur supplier (terhubung ke dokumen asal)
5. Reorder Point / Minimum Stock per item+gudang + indikator
6. Buang stub `MutasiInventoryHeader`/`MutasiInventoryDetail`

## B. Prinsip yang dipertahankan

- **Single source of truth**: semua kuantitas & nilai stok tetap diturunkan dari `StockMovement` (P1).
- **Costing sebagai strategy**: penurunan stok selalu lewat `consume_stock(..., metode)` (P2) — menghormati FIFO/LIFO/Average, isolasi EB hierarkis, dan kunci warehouse.
- **Dimensi akuntansi (EntitasBisnis) ≠ lokasi fisik (Warehouse)** (P6).
- **Jurnal selalu balance-checked** sebelum commit (pola `process_asset_disposal`).
- **Semua transaksi reversible** lewat engine reversal yang sudah ada.

---

## C. Fondasi: Perluasan Ledger Engine

File: [apps/inventory/ledger.py](../../../apps/inventory/ledger.py) & [apps/inventory/models.py](../../../apps/inventory/models.py)

### C.1 Movement types baru
Tambahkan ke `StockMovement.MOVEMENT_TYPE_CHOICES`:

| Kode | Arah | Dipakai oleh |
|------|------|--------------|
| `adjustment_in` | inflow | Stock Adjustment (koreksi naik) |
| `adjustment_out` | outflow | Stock Adjustment (koreksi turun) |
| `opname_in` | inflow | Stock Opname (surplus fisik) |
| `opname_out` | outflow | Stock Opname (minus fisik) |
| `transfer_in` | inflow | Transfer (sisi tujuan) |
| `transfer_out` | outflow | Transfer (sisi asal) |
| `return_customer` | inflow | Retur pelanggan (barang kembali) |
| `return_supplier` | outflow | Retur supplier (barang keluar ke vendor) |

### C.2 Reuse engine
- **Kenaikan stok** (`*_in`, `return_customer`): `record_inflow(item, eb1, eb2, eb3, qty, unit_cost, tanggal, movement_type, source=..., warehouse=...)`. Membuat layer baru dengan `remaining_qty = qty`.
- **Penurunan stok** (`*_out`, `return_supplier`): `consume_stock(item, eb1, eb2, eb3, qty, tanggal, movement_type, source=..., metode=item.metode_biaya_persediaan, warehouse=...)`. Mengembalikan `ConsumptionResult(total_cost, allocations, out_movement, report)`; `total_cost / qty` = biaya rata-rata konsumsi (dipakai untuk cost transfer & jurnal).

### C.3 Perluasan set reversal
```python
INFLOW_MOVEMENT_TYPES  |= {'adjustment_in', 'opname_in', 'transfer_in', 'return_customer'}
OUTFLOW_MOVEMENT_TYPES |= {'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier'}
```
Agar `reverse_movements(source)` (memulihkan layer inflow + hapus outflow) dan `reverse_inflow_movements(source)` (hapus layer inflow; ProtectedError bila sudah dikonsumsi — fail-loud) bekerja untuk semua transaksi baru.

**Catatan bulk item** (`RMB/FGB/ITMB`): engine sudah punya cabang value-based (`_consume_stock_bulk`, mirror `_mirror_*`). Transaksi baru mewarisi perilaku ini otomatis karena lewat entry point yang sama.

---

## D. Model Data

Semua di `apps/inventory/models.py`, pola header/detail seperti `aset_tetap` & `sales`. Setiap header punya: `nomor` (auto-generate `TRX-<PREFIX>-NNN`), `tanggal`, `entitas_bisnis` (+`entitas_bisnis_lv2`/`lv3` nullable), `status` (`draft`/`posted`), `jurnal_header` (FK nullable ke `jurnal.JurnalHeader`), `keterangan`, `created_at`.

### D.1 StockAdjustment / StockAdjustmentItem
- Header: + `warehouse` (FK), + `akun_selisih` (FK `Akun`, user pick — akun laba/rugi persediaan).
- Item: `item` (FK), `qty` (Decimal, **bertanda**: + naik / − turun), `unit_cost` (untuk kenaikan; untuk penurunan diisi dari hasil konsumsi), `movement` (FK `StockMovement`, diisi saat posting).

### D.2 StockOpname / StockOpnameItem
- Header: + `warehouse`, + `akun_selisih`.
- Item: `item`, `qty_sistem` (snapshot `get_available_stock` saat baris dibuat), `qty_fisik` (input), `selisih` (auto = fisik − sistem, editable=False), `unit_cost`, `movement` (FK, saat posting).
- Posting: per baris, `selisih > 0` → `opname_in`; `selisih < 0` → `opname_out`; `selisih == 0` → skip. Satu jurnal untuk seluruh dokumen.

### D.3 StockTransfer / StockTransferItem
- Header: `eb_asal`(lv1-3)+`warehouse_asal`, `eb_tujuan`(lv1-3)+`warehouse_tujuan`, `akun_perantara` (FK `Akun`, nullable — **wajib hanya bila lintas EB lv1**).
- Item: `item`, `qty`, `unit_cost` (dihitung dari `total_cost/qty` konsumsi asal), `movement_out` (FK), `movement_in` (FK).
- Posting per baris: `consume_stock(eb_asal…, warehouse=warehouse_asal)` → `record_inflow(eb_tujuan…, warehouse=warehouse_tujuan, unit_cost=biaya_konsumsi)`.

### D.4 ReturCustomer / ReturCustomerItem
- Header: `sales_header` (FK `sales.SalesHeader`), `warehouse` (gudang barang masuk), EB diambil dari sales.
- Item: `sales_item` (FK `sales.SalesItem`), `item`, `qty` (≤ qty terjual & belum diretur), `unit_cost` (biaya asli dari alokasi HPP SalesItem), `movement` (FK, `return_customer`).

### D.5 ReturSupplier / ReturSupplierItem
- Header: `purchase_item`/`purchase_header` (FK `purchase`), `warehouse`.
- Item: `purchase_item` (FK), `item`, `qty` (≤ qty dibeli & belum diretur), `movement` (FK, `return_supplier`; biaya via `consume_stock`).

### D.6 ItemReorderSetting
- `item` (FK), `warehouse` (FK), `minimum_stock` (Decimal), `reorder_point` (Decimal), `reorder_qty` (Decimal, opsional). `unique_together = (item, warehouse)`.

### D.7 Hapus stub
`MutasiInventoryHeader` & `MutasiInventoryDetail` dihapus dari model, admin, dan migrasi drop-table. Sudah dikonfirmasi tidak direferensikan ledger baru maupun modul lain (verifikasi grep sebelum drop).

---

## E. Logika Jurnal

Akun persediaan item = `item.coa_account` (konvensi existing, sama seperti sales). Semua jurnal balance-checked; nomor via helper `TRX-<PREFIX>-NNN`; `entitas_bisnis` di header; reversal pakai `log_jurnal_terhapus` + hapus detail+header (pola `reverse_asset_disposal`).

| Transaksi | Debit | Kredit |
|-----------|-------|--------|
| Adjustment/Opname **naik** | Persediaan (`item.coa_account`) | `akun_selisih` |
| Adjustment/Opname **turun** | `akun_selisih` | Persediaan |
| Transfer **intra-EB lv1** | — (tanpa jurnal, pindah lokasi murni) | — |
| Transfer **lintas EB lv1** (jurnal asal) | `akun_perantara` | Persediaan |
| Transfer **lintas EB lv1** (jurnal tujuan) | Persediaan | `akun_perantara` |
| Retur pelanggan (balik pendapatan) | Pendapatan/Retur Penjualan (`revenue_account` asal) | Kas/Piutang (payment account asal) |
| Retur pelanggan (balik HPP) | Persediaan | HPP (`offset_coa_account` asal) |
| Retur supplier | Hutang/Kas (payment account asal) | Persediaan |

- Nilai retur pelanggan (pendapatan) = qty × harga jual asal; nilai HPP = `unit_cost` asli dari alokasi HPP SalesItem.
- Retur supplier: nilai = `total_cost` dari `consume_stock`.
- Transfer lintas-EB pakai **dua** `JurnalHeader` terpisah (satu per entitas), masing-masing balance sendiri.

---

## F. UI/UX

Pola existing `ni-*`, list + form header/detail inline (formset) + aksi post/batal (konfirmasi seperti `disposal_delete_confirm.html`).

- **Adjustment / Opname / Transfer / Retur**: masing-masing punya (a) halaman list dengan filter EB/gudang/tanggal/status, (b) form create header + formset detail, (c) tombol **Proses** (posting → movement + jurnal), (d) konfirmasi **Batal** (reversal). Opname: tombol "Ambil qty sistem" mengisi `qty_sistem` per item saat form dibuka.
- **Reorder**: setting per item+gudang (halaman kelola atau inline pada item master) + **indikator badge** di list inventory / dashboard ketika `get_available_stock(item, eb, warehouse) <= minimum_stock` (merah) atau `<= reorder_point` (kuning).
- Menu/nav: item baru di bawah modul Inventory.

---

## G. Testing (per fitur)

1. **Engine**: movement dibuat dengan `remaining_qty` benar; isolasi EB (cabang A tak tersentuh transaksi cabang B); kunci warehouse (tak ada fallback lintas gudang).
2. **Jurnal**: balance debit=kredit; akun benar sesuai tabel §E; arah naik vs turun.
3. **Reversal**: batal memulihkan layer & saldo stok; jurnal ter-log & terhapus; ProtectedError bila layer sudah dikonsumsi (inflow).
4. **Transfer lintas-EB**: dua jurnal balance; stok pindah gudang; cost terbawa benar.
5. **Retur**: qty tak melebihi sisa; cost retur pelanggan = biaya HPP asli; retur supplier via metode costing item.
6. **Opname**: selisih=fisik−sistem; selisih 0 tak buat movement.
7. **Reorder**: indikator menyala pada ambang yang benar; unique (item, warehouse).
8. **Regresi**: purchase/sales/POS existing tetap hijau; stub Mutasi terhapus tanpa memutus migrasi.

---

## H. Urutan Implementasi (ringkas — detail di plan)

1. Perluasan `StockMovement` types + set reversal + buang stub Mutasi (fondasi, migrasi).
2. Stock Adjustment (model → service/jurnal → UI → test) sebagai template pola.
3. Stock Opname (di atas pola Adjustment).
4. Transfer (termasuk cabang lintas-EB).
5. Retur pelanggan & retur supplier.
6. Reorder Point + indikator.

Fitur 2–6 saling independen di atas fondasi (1); bisa paralel bila perlu, tapi Adjustment (2) dulu agar polanya mapan.
