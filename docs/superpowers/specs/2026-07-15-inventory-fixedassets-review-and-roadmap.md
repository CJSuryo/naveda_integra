# Review & Roadmap — Modul Inventory & Aset Tetap

**Tanggal:** 2026-07-15
**Penulis:** Solution Architect review
**Status:** Menunggu persetujuan (belum ada implementasi)
**Ruang lingkup:** Inventory, Fixed Assets, dan integrasinya dengan Accounting, Purchase, Sales, POS. Manufacturing hanya dipertimbangkan sebagai konsumen desain agar tetap scalable.

---

## A. Ringkasan Temuan

Fondasi akuntansi transaksional kedua modul sudah ada dan matang, tetapi keduanya belum lengkap sebagai modul operasional. Temuan struktural utama:

1. **Item Master terpusat** (`purchase.ItemMasterPurchase`) dipakai lintas modul — desain benar, dipertahankan.
2. **Dua ledger stok paralel**: `purchase.FIFOBatch` (dikonsumsi Manufacturing) dan `inventory.InventoryRecord` (dikonsumsi Sales), keduanya dibuat saat pembelian dan disinkronkan manual. Risiko divergensi.
3. **Costing hanya FIFO**. LIFO/Average/WMA hanya pilihan dropdown, tidak diimplementasikan.
4. **`consume_fifo` mengabaikan Entitas Bisnis** → stok bocor antar cabang (bug material).
5. **Tidak ada Master Satuan (UOM)** dan konversi — gap fondasi.
6. **Fixed Asset** kuat di penyusutan (5 metode), kosong di siklus hidup (pelepasan, revaluasi, mutasi, PIC, dokumen).
7. **Mapping COA per item**, bukan per kategori. COA penyusutan di-hardcode (`startswith('5.1.19')`).

Referensi kode kunci:
- Item master: `apps/purchase/models.py:49`
- Dua ledger dibuat saat beli: `apps/purchase/services.py:69` (FIFOBatch) & `:114` (InventoryRecord)
- Costing FIFO: `apps/sales/services.py:61` (`consume_fifo`) & `:223` (`process_sales_fifo`)
- Penyusutan: `apps/aset_tetap/services.py:17-112`; jurnal hardcode COA: `:170-171`
- Stub kosong: `apps/inventory/models.py:6-35`

Status per requirement: lihat lampiran matriks di akhir dokumen.

---

## B. Prinsip Desain (agar tidak dirombak saat Manufacturing berkembang)

- **P1 — Single source of truth untuk stok**: satu `StockMovement` ledger append-only; semua kuantitas & nilai stok diturunkan darinya.
- **P2 — Costing sebagai strategy**: satu entry point `consume_stock(item, entitas, gudang, qty, metode)`; FIFO/LIFO/Average di belakang antarmuka yang sama.
- **P3 — UOM generic & reusable**: base unit per dimensi + faktor konversi; dipakai Purchase, Sales, POS, Manufacturing tanpa ubah skema.
- **P4 — Mapping COA per kategori** dengan override per item/aset.
- **P5 — Event aset sebagai tabel terpisah** (audit trail), tiap event memicu jurnal via engine yang sama.
- **P6 — Dimensi akuntansi (Entitas Bisnis) ≠ lokasi fisik (Gudang)**.

---

## C. Rencana Implementasi Berfase

Setiap fase harus: (a) punya migrasi mundur yang aman, (b) mempertahankan perilaku FIFO yang sudah benar, (c) disertai test, (d) tidak memutus Purchase/Sales/POS yang berjalan.

### FASE 1 — Fondasi UOM (High)
**Tujuan:** master satuan standar + konversi, dipakai lintas modul.

Model baru (usulan app `master_data` atau `uom`):
- `UnitDimension` (count, berat, volume, panjang, luas) — atau enum.
- `UnitOfMeasure`: `kode`, `nama`, `dimension`, `is_base`, `factor_to_base` (Decimal), `is_system` (bawaan, tak bisa dihapus).
- `UnitConversion` (opsional bila butuh konversi lintas-dimensi khusus item, mis. karton→pcs yang item-specific): `item`, `from_uom`, `to_uom`, `factor`.

Perubahan item master (nullable dulu, backfill, lalu wajibkan):
- `base_uom`, `purchase_uom`, `sales_uom`, `stock_uom` (FK ke `UnitOfMeasure`).

Seed data bawaan: ton, kg, g, mg, L, mL, cc, m³, m², m, cm, mm, pcs, unit, box, pack, carton, roll, botol, dus.

Acceptance:
- Konversi `qty_in_uom → qty_in_base` teruji (mis. 1 carton = 24 pcs).
- Purchase/Sales/POS masih jalan dengan default `stock_uom = base_uom`.

**Tidak mengubah costing di fase ini** — hanya menyiapkan dimensi kuantitas.

### FASE 2 — Stock Ledger tunggal + isolasi Entitas/Gudang (High)
**Tujuan:** selesaikan dua-ledger & kebocoran antar cabang.

Model baru:
- `Warehouse` (gudang): `kode`, `nama`, `entitas_bisnis` (FK), `alamat`, `is_active`.
- `StockMovement` (append-only): `item`, `entitas_bisnis`, `warehouse`, `tanggal`, `qty` (base uom, signed atau in/out), `unit_cost`, `movement_type` (purchase/sale/production_in/production_out/transfer_in/transfer_out/adjustment/return_customer/return_supplier), `source_content_type`+`source_id` (referensi polimorfik), `remaining_qty` (untuk lapis FIFO), `created_at`.

Strategi migrasi:
1. Bangun `StockMovement` + backfill dari `FIFOBatch` (inflow) dan alokasi penjualan (outflow) yang ada.
2. Costing engine baru membaca dari `StockMovement`; `FIFOBatch`/`InventoryRecord` sementara dipertahankan sebagai read-model turunan sampai stabil, lalu di-deprecate.
3. `consume_stock` **wajib** filter `entitas_bisnis` (+ `warehouse` bila multi-gudang aktif).

Acceptance:
- Penjualan cabang A tidak mengonsumsi stok cabang B (test regresi bug §A-4).
- Saldo stok = agregasi `StockMovement`; cocok dengan FIFOBatch lama pada data uji.

### FASE 3 — Costing multi-metode (High)
- `consume_stock(item, entitas, warehouse, qty, metode)` → FIFO/LIFO/Average.
- Average: moving weighted average dari `StockMovement`.
- Jika metode belum dipilih → default FIFO; jika metode diminta tapi belum didukung → error eksplisit (bukan diam-diam FIFO).
- Alternatif jangka pendek bila fase ini ditunda: **batasi pilihan UI ke FIFO** agar tidak menyesatkan.

Acceptance: test HPP untuk skenario FIFO, LIFO, Average dengan angka yang diverifikasi manual.

### FASE 4 — Fixed Asset: Pelepasan + jurnal laba/rugi (High)
Model baru: `AssetDisposal` (`aset`, `tanggal`, `jenis`: jual/hibah/rusak/musnah, `harga_jual`, `akun_kas`, `keterangan`).
Logika jurnal saat pelepasan (jual):
- Kredit Aset (harga perolehan), Debit Akumulasi Penyusutan (saldo), Debit Kas/Piutang (harga jual), selisih → Debit/Kredit Laba/Rugi Pelepasan Aset.
Acceptance: nilai buku ter-nol-kan, laba/rugi otomatis benar, aset non-aktif.

### FASE 5 — Mapping COA per kategori (High)
- Tambah akun default pada `KategoriItem` (persediaan, HPP, pendapatan) dan pada kategori aset (aset, akumulasi penyusutan, beban penyusutan, laba/rugi pelepasan).
- Item/aset mewarisi, boleh override.
- Ganti hardcode `startswith('5.1.19')`/`'1.2.7'` di `aset_tetap/services.py` dengan lookup mapping.
Acceptance: penyusutan bangunan vs kendaraan memakai akun berbeda sesuai kategori.

### FASE 6 — Transaksi & kontrol stok (Medium)
- Stock Adjustment (+ jurnal penyesuaian) — di atas `StockMovement`.
- Stock Opname (hitung fisik → posting selisih).
- Transfer antar gudang/cabang (transfer_out/in, jurnal antar-akun bila lintas entitas).
- Retur pelanggan & retur supplier (movement + jurnal balik).
- Reorder Point / Minimum Stock + indikator.
- Buang stub `MutasiInventoryHeader/Detail`.

### FASE 7 — Fixed Asset lanjutan (Medium)
- Mutasi lokasi/departemen (`AssetTransfer`), Maintenance (`AssetMaintenance`), Revaluasi (`AssetRevaluation` + jurnal surplus revaluasi).
- Field PIC, lokasi/departemen terstruktur, umur ekonomis default per kategori.
- Relasikan dokumen/foto ke aset via `master_data.Bukti` (FK).
- Depreciation Schedule (proyeksi ke depan) + laporan penyusutan per kategori/lokasi.

### FASE 8 — Pelaporan (Medium)
- Stock Card, Inventory Movement, Inventory Valuation, Laporan HPP, Slow/Fast Moving (pakai `velocity_category` yang sudah ada).
- Asset register per kategori/lokasi/departemen.

### FASE 9 — Nilai tambah (Low)
- Barcode/QR (item & aset), Serial/Lot user-facing, Varian produk, Harga khusus pelanggan (price list), audit fisik aset, kapitalisasi vs expense.

---

## D. Urutan Eksekusi yang Disarankan

Fase 1 → 2 → 3 saling bergantung dan menjadi tulang punggung; kerjakan berurutan.
Fase 4 & 5 (Fixed Asset pelepasan + mapping COA) dapat berjalan paralel dengan 1–3 karena beririsan minimal.
Fase 6–9 menyusul di atas fondasi 1–3.

---

## E. Risiko & Mitigasi

- **Migrasi data stok** (Fase 2): jalankan backfill + rekonsiliasi saldo pada salinan produksi sebelum cutover; pertahankan ledger lama sebagai pembanding sampai cocok.
- **Perubahan item master (UOM wajib)**: lakukan bertahap (nullable → backfill → wajib) agar transaksi berjalan tidak putus.
- **Regressi FIFO**: kunci perilaku FIFO saat ini dengan test sebelum refactor costing.

---

## Lampiran — Matriks Status Requirement (ringkas)

Inventory: SKU ✅ · Kategori ✅ · UOM+konversi ❌ · Harga beli ✅ · Harga jual ⚠️ · Harga khusus pelanggan ❌ · Multi gudang ❌ · Multi cabang ⚠️(EntitasBisnis) · Varian ❌ · FIFO ✅ · LIFO/Average ❌ · HPP POS ✅ · Penerimaan beli ✅ · Pengurangan POS ✅ · Transfer ❌ · Retur pelanggan/supplier ❌ · Adjustment ❌ · Reorder ❌ · Opname ❌ · Batch ⚠️(implisit) · Expiry ✅ · Serial ❌ · Jurnal beli ✅ · Jurnal HPP ✅ · Jurnal penyesuaian ❌ · Mapping COA per kategori ⚠️ · Laporan (Stock Card/Movement/Valuation/HPP/Slow-Fast) ❌.

Fixed Assets: Kode otomatis ✅ · Kategori ✅ · Data perolehan ⚠️(vendor/invoice belum) · Lokasi ⚠️(free-text) · Dept/cabang ⚠️ · PIC ❌ · Foto/dokumen ❌ · Garis Lurus ✅ · Saldo Menurun ✅ · Unit Produksi ✅ (+SYD, Service Hours) · Umur per kategori ⚠️ · Residu ✅ · Penyusutan otomatis ✅ · Jadwal penyusutan ❌ · Mutasi lokasi ❌ · Maintenance ❌ · Kapitalisasi/expense ❌ · Revaluasi ❌ · Pelepasan ❌ · Laba/rugi pelepasan ❌ · Jurnal perolehan ✅ · Jurnal penyusutan ✅ · Jurnal pelepasan ❌ · Mapping COA ⚠️(hardcode) · Asset Register ✅ · Laporan penyusutan ⚠️ · Laporan per kategori/lokasi ⚠️ · Opname aset ❌ · Barcode/QR ❌.
