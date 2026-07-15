# Stock Ledger Tunggal + Isolasi Entitas Bisnis — Design (Fase 2)

**Tanggal:** 2026-07-15
**Status:** Disetujui (siap masuk penyusunan plan implementasi)
**Ruang lingkup:** Fase 2 dari roadmap `2026-07-15-inventory-fixedassets-review-and-roadmap.md`. Menyelesaikan dua-ledger paralel dan kebocoran stok antar cabang. **Tidak** mengubah metode costing (FIFO tetap; LIFO/Average = Fase 3). **Tidak** menambah Warehouse (ditunda).

---

## A. Masalah yang Diselesaikan

1. **Kebocoran stok antar cabang (§A-4, bug material).** `FIFOBatch` tidak punya field `entitas_bisnis`. `sales.consume_fifo` dan `manufacturing._consume_fifo` memfilter hanya `item_id`, sehingga penjualan/produksi cabang A dapat mengonsumsi stok cabang B.
2. **Dua ledger paralel** — `purchase.FIFOBatch` (dikonsumsi Sales & Manufacturing) dan `inventory.InventoryRecord` (dibaca POS/kasir, dashboard) — dibuat & disinkronkan manual. Sinkronisasi memakai pencocokan rapuh `(tanggal, unit_price)` di `apps/sales/services.py:process_sales_fifo`. Risiko divergensi.

Prinsip roadmap yang dipenuhi: **P1** (single source of truth), **P6** (dimensi akuntansi EB vs lokasi fisik — Warehouse disiapkan additive untuk masa depan).

## B. Keputusan Desain (hasil brainstorming)

- **Data produksi harus aman** → strategi *strangler*: bangun ledger baru, backfill, rekonsiliasi di salinan produksi, pertahankan ledger lama sebagai mirror/pembanding; hapus di fase lanjutan.
- **Warehouse ditunda** → isolasi memakai Entitas Bisnis; `StockMovement` dirancang agar penambahan FK `warehouse` nanti murni additive.
- **Isolasi hierarkis** → konsumsi mencocokkan di node EB terdalam, boleh **naik ke induk** (lv3→lv2→lv1) dalam pohon cabang yang sama; **tidak pernah** menyeberang ke cabang sibling.
- **Produksi juga fleksibel level EB** → `ProductionOrder` memperoleh `entitas_bisnis_lv2`/`lv3`, sehingga konsumsi produksi mendapat perlakuan hierarkis yang sama seperti Sales.
- **Approach A** (dari 3 opsi): `StockMovement` otoritatif; `FIFOBatch`/`InventoryRecord` tetap ditulis sebagai *mirror* agar pembaca hilir tak perlu diubah di fase ini.
- **Notifikasi fallback** → saat konsumsi menaikkan level (mengambil stok dari induk), UI memberi peringatan informatif (non-blocking).

## C. Model Data

### C.1 `StockMovement` (baru, `apps/inventory`) — append-only, sumber kebenaran stok

| Field | Tipe | Keterangan |
|---|---|---|
| `item` | FK `purchase.ItemMasterPurchase` (PROTECT) | |
| `entitas_bisnis` | FK `EntitasBisnis` (PROTECT) | lv1, **selalu terisi** — akar isolasi |
| `entitas_bisnis_lv2` | FK `EntitasBisnisLv2` (PROTECT, null) | terisi sesuai kedalaman transaksi |
| `entitas_bisnis_lv3` | FK `EntitasBisnisLv3` (PROTECT, null) | terisi sesuai kedalaman transaksi |
| `tanggal` | DateField (db_index) | |
| `movement_type` | CharField(choices) | `purchase_in`, `sale_out`, `production_in`, `production_out`, `saldo_awal` (transfer/adjustment/return_customer/return_supplier → Fase 6) |
| `qty` | Decimal(15,4) | base-uom, **signed**: inflow > 0, outflow < 0 |
| `unit_cost` | Decimal(19,4) | biaya per satuan base (bermakna pada layer inflow) |
| `remaining_qty` | Decimal(15,4) | hanya bermakna pada layer inflow — sisa belum dikonsumsi (peran `FIFOBatch` dilebur) |
| `source_content_type` | FK ContentType (null) | GenericFK polimorfik... |
| `source_object_id` | PositiveIntegerField (null) | ...ke `PurchaseItem` / `SalesItem` / konsumsi produksi |
| `legacy_fifo_batch` | FK `purchase.FIFOBatch` (SET_NULL, null) | jembatan 1:1 ke ledger lama (backfill & dual-write) |
| `legacy_inventory_record` | FK `inventory.InventoryRecord` (SET_NULL, null) | jembatan 1:1 ke ledger lama |
| `created_at` | DateTimeField(auto_now_add) | |

Index yang diperlukan: `(item, entitas_bisnis, remaining_qty)` untuk pencarian layer kandidat; `(item, tanggal)` untuk urutan FIFO; `(source_content_type, source_object_id)` untuk reversal.

**Konvensi item bulk (RMB/FGB/ITMB):** dipertahankan value-based seperti sekarang — inflow `qty=1`, `unit_cost=total_value`; outflow mengurangi berbasis nilai. Fase 2 tidak mengubah costing.

### C.2 `StockConsumption` (baru, `apps/inventory`) — alokasi outflow→inflow

| Field | Tipe | Keterangan |
|---|---|---|
| `out_movement` | FK `StockMovement` (CASCADE) | baris outflow (`sale_out`/`production_out`) |
| `in_movement` | FK `StockMovement` (PROTECT) | layer inflow yang dikonsumsi |
| `qty` | Decimal(15,4) | jumlah base-uom yang dialokasikan dari layer ini |
| `unit_cost` | Decimal(19,4) | biaya layer (untuk COGS presisi) |

Menggantikan pencocokan `(tanggal, unit_price)` yang rapuh; membuat reversal presisi & COGS auditable. `SalesItemFIFOAllocation` yang ada tetap ditulis (diturunkan dari `StockConsumption`) demi tampilan lama.

### C.3 Perubahan `ProductionOrder` (`apps/manufacturing`)

Tambah `entitas_bisnis_lv2` (FK, null) dan `entitas_bisnis_lv3` (FK, null), sejajar pola Purchase/Sales. Form/UI production order memperoleh pemilihan lv2/lv3. Konsumsi produksi meneruskan level terdalam yang tersedia ke `consume_stock`.

## D. Service Layer — `apps/inventory/ledger.py`

Mesin stok tunggal. Empat fungsi inti + tipe hasil.

### D.1 `record_inflow(...) -> StockMovement`
```
record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal,
              movement_type, source, *,
              legacy_fifo_batch=None, legacy_inventory_record=None)
```
Membuat satu layer inflow (`remaining_qty = qty`), menautkan mirror lama bila diberikan. Dipakai purchase inflow, `production_in` (FG), `saldo_awal`.

### D.2 `consume_stock(...) -> ConsumptionResult`
```
consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal,
              movement_type, source, metode='fifo') -> ConsumptionResult
```
Inti fix bug:
1. Susun himpunan layer kandidat berdasarkan **kedekatan EB**: node terdalam yang diberikan dulu (lv3 → lv2 → lv1), masing-masing FIFO by `tanggal, created_at`. **Tidak menyeberang cabang sibling.**
2. `select_for_update()` untuk konkurensi.
3. Kurangi `remaining_qty` tiap layer, buat baris outflow `StockMovement` (`qty<0`), buat `StockConsumption`, **mirror** pengurangan ke `legacy_fifo_batch`/`legacy_inventory_record` yang tertaut.
4. Cabang value-based untuk item bulk berada di dalam fungsi ini (caller tak special-case).
5. `raise InsufficientStockError` (subclass `ValueError`) bila kurang.

Return `ConsumptionResult`:
```
ConsumptionResult:
  total_cost: Decimal
  allocations: list[StockConsumption]
  report: ConsumptionReport

ConsumptionReport:
  requested_level: 'lv1'|'lv2'|'lv3'      # level node transaksi
  used_fallback: bool                     # True bila ada qty dari level di atas requested_level
  by_level: list[{ level, eb_name, qty }] # rincian sumber per level
```

### D.3 `reverse_movements(source)`
Diberi objek sumber (atau transaksi), pulihkan `remaining_qty` layer inflow via `StockConsumption`, hapus baris outflow + alokasi, pulihkan mirror lama. Menggantikan logika reversal yang tersebar di `reverse_sales_fifo`.

### D.4 `get_available_stock(item, eb_lv1, eb_lv2, eb_lv3) -> Decimal`
Jumlah `remaining_qty` atas himpunan kandidat hierarkis. Pengganti `get_available_stock` di `apps/sales/services.py` & `apps/manufacturing/services.py`.

### D.5 Integrasi dual-write (Fase 2)
- **Purchase inflow** (`apps/purchase/services.py`): tetap buat `FIFOBatch` + `InventoryRecord` (tak diubah), lalu **juga** panggil `record_inflow` dengan tautan ke keduanya.
- **Sales outflow** (`apps/sales/services.py:process_sales_fifo`): isi diganti → `consume_stock` otoritatif (memfilter EB = fix bug) & me-mirror ke `FIFOBatch` + `InventoryRecord` lewat FK tautan. Kode pencocokan `(tanggal, unit_price)` dibuang. `SalesItemFIFOAllocation` tetap ditulis dari `StockConsumption`.
- **Manufacturing** (`apps/manufacturing/services.py`): konsumsi RM lewat `consume_stock` (kini dengan lv2/lv3); FG lewat `record_inflow` (`production_in`) + tetap buat mirror `FIFOBatch`/`InventoryRecord` FG.

### D.6 Kompatibilitas baca
POS/kasir (`apps/sales/kasir_views.py`), dashboard, inventory views **tetap membaca `InventoryRecord`/`FIFOBatch`** tanpa perubahan karena selalu ter-mirror. `StockMovement` otoritatif untuk urutan konsumsi & isolasi.

### D.7 Notifikasi fallback ke UI
- **Sales form biasa:** `messages.warning(...)` bila `report.used_fallback`, mis. *"Stok di [Cabang lv3] tidak mencukupi. 12 unit diambil dari [induk lv2/lv1]."*
- **Kasir/POS:** banner/toast pada respons proses.
- **Manufacturing:** pesan pada hasil eksekusi produksi bila RM diserap dari level induk.
- Bersifat informatif (tidak memblokir), sesuai model hierarkis yang membolehkan naik ke induk. Mode "wajib konfirmasi" bisa ditambah di fase UI lanjutan tanpa ubah engine.

## E. Migrasi & Backfill (aman untuk data produksi)

**Langkah A — Migrasi skema (additive, reversible):** buat `StockMovement` + `StockConsumption`; tambah `entitas_bisnis_lv2`/`lv3` ke `ProductionOrder`. Semua nullable/tabel baru → data lama tak tersentuh; reverse = drop.

**Langkah B — Backfill (`RunPython`), digerakkan oleh `FIFOBatch`** (otoritatif sisa & biaya FIFO):
- Tiap `FIFOBatch` → satu layer inflow `StockMovement`: `qty = quantity_in`, `remaining_qty = remaining_qty` **saat ini** (snapshot keadaan sekarang; tidak replay riwayat outflow), `unit_cost = unit_price`.
- **Atribusi EB:** ada `purchase_item` → dari `purchase_item.purchase_eb` (lv1/lv2/lv3); saldo awal → cocokkan `InventoryRecord` via `(item, tanggal, unit_price)`.
- **Tautan legacy:** set `legacy_fifo_batch` = batch; `legacy_inventory_record` = InventoryRecord tercocok.
- `movement_type` = `purchase_in` atau `saldo_awal`. Item bulk pertahankan konvensi value-based.
- Karena `remaining_qty` disalin langsung dari `FIFOBatch`, **saldo total per item cocok by construction**; pembagian per-EB diturunkan dari purchase/InventoryRecord.
- Riwayat outflow lama **tidak** direkonstruksi — transaksi lama tetap reversible via jalur legacy (`SalesItemFIFOAllocation` + mirror). Konsumsi sejak cutover sepenuhnya pakai engine baru.

**Langkah C — Rekonsiliasi:** management command `reconcile_stock_ledger` melaporkan per item & per EB:
- Σ `StockMovement.remaining_qty` (inflow) vs Σ `FIFOBatch.remaining_qty` → harus sama.
- Σ `StockMovement.remaining_qty` per EB vs agregat `InventoryRecord.quantity` → tandai drift.
- Anomali: FIFOBatch tanpa pasangan InventoryRecord / EB tak teratribusi.

**Alur cutover (mitigasi §E roadmap):** backfill + rekonsiliasi di **salinan** produksi → tinjau drift → perbaiki anomali → terapkan ke produksi. Ledger lama tetap sebagai pembanding; penghapusan dijadwalkan fase lanjutan.

## F. Strategi Testing

Jalankan via `python manage.py test <path> --settings=naveda_integra.settings.test`.

1. **Characterization (kunci FIFO saat ini)** — ditulis **sebelum** refactor: urutan konsumsi, total COGS same-EB, reversal memulihkan layer, deduksi value-based item bulk.
2. **Regresi bug kebocoran (§A-4)** — beli di Cabang A + B, jual di A → stok B utuh, A hanya konsumsi layer A. **Wajib gagal di kode lama, lulus di engine baru.**
3. **Isolasi & fallback hierarkis:**
   - Beli lv1, jual lv3 → konsumsi lv1, `used_fallback=True`, `by_level` benar.
   - Beli lv3 + lv1, jual lv3 melebihi stok lv3 → lv3 dulu lalu naik lv1; laporan menampilkan keduanya.
   - **Isolasi sibling:** beli lv3-A, jual lv3-B (induk lv2 sama) → `InsufficientStockError`.
4. **`consume_stock` unit** — kurang stok → `InsufficientStockError`; Σ `StockConsumption` = qty; `remaining_qty` benar; mirror ke `FIFOBatch`+`InventoryRecord` cocok.
5. **Dual-write integrasi** — satu pembelian → `FIFOBatch` + `InventoryRecord` + `StockMovement` tertaut; saldo ketiganya sepakat.
6. **Reversal** — `reverse_movements` memulihkan `remaining_qty`, hapus outflow + alokasi, pulihkan mirror; keadaan akhir = sebelum konsumsi.
7. **Backfill migration** — fixture FIFOBatch+InventoryRecord legacy → jalankan backfill → assert layer StockMovement (EB, remaining, tautan legacy) benar; rekonsiliasi lulus.
8. **Manufacturing** — konsumsi RM terisolasi EB dengan lv2/lv3; `production_in` FG buat layer + mirror.
9. **Notifikasi UI** — view sales/kasir keluarkan `messages.warning` saat `used_fallback`; manufacturing serupa.

## G. Non-Goals (Fase 2)

- Metode costing LIFO/Average (Fase 3).
- Model/UI Warehouse, transfer antar gudang (Warehouse ditunda; transfer Fase 6).
- Stock adjustment, opname, retur (Fase 6).
- Penghapusan `FIFOBatch`/`InventoryRecord` (fase lanjutan setelah pembaca dimigrasi).
- Mode konsumsi "wajib konfirmasi sebelum naik level" (fase UI lanjutan).

## H. Referensi Kode

- Bug kebocoran: `apps/sales/services.py:61` (`consume_fifo`), `apps/manufacturing/services.py:175` (`_consume_fifo`).
- Sinkronisasi rapuh: `apps/sales/services.py:223` (`process_sales_fifo`).
- Pembuatan dua ledger: `apps/purchase/services.py:69` (`create_fifo_batches`), `:114` (`create_inventory_records`).
- Pembaca InventoryRecord: `apps/sales/kasir_views.py:82`.
- Model: `apps/purchase/models.py:566` (`FIFOBatch`), `apps/inventory/models.py:38` (`InventoryRecord`), `apps/manufacturing/models.py:90` (`ProductionOrder`).
