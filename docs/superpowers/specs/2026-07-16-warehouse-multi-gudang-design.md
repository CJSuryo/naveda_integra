# Warehouse (Multi-Gudang) — Design

**Tanggal:** 2026-07-16
**Status:** Disetujui (siap masuk perencanaan implementasi)
**Fase roadmap:** Bagian dari Fase 2 yang dikarve-out sebagai non-goal; dikerjakan sekarang sebagai fase tersendiri di atas fondasi Stock Ledger (Fase 2 selesai).
**Ruang lingkup:** Menambah dimensi **lokasi fisik (gudang)** ke ledger stok tunggal (`StockMovement`), terpisah dari dimensi akuntansi (Entitas Bisnis), untuk aplikasi keuangan **multi-tenant** Naveda.

---

## A. Konteks & Motivasi

Naveda adalah aplikasi keuangan **multi-tenant**: banyak bisnis berbeda memakainya, masing-masing punya cabang dan gudang sendiri. Fase 2 sudah membangun `StockMovement` sebagai ledger stok tunggal yang otoritatif, diisolasi per **Entitas Bisnis** (dimensi akuntansi, hierarki lv1→lv2→lv3) dengan konsumsi FIFO dan fallback tier (lv3→lv2→lv1). Gudang fisik **sengaja ditunda** (non-goal Fase 2).

Fase ini menambah **gudang fisik** sebagai dimensi ortogonal terhadap Entitas Bisnis (prinsip P6 roadmap: *dimensi akuntansi ≠ lokasi fisik*).

### Pemetaan hierarki EB

- **lv1 (`EntitasBisnis`) = bisnis/tenant.** Batas isolasi multi-tenant.
- **lv2/lv3 (`EntitasBisnisLv2`/`EntitasBisnisLv3`) = cabang/sub-unit** di dalam satu bisnis.

### Relasi gudang

- **Gudang ↔ bisnis (lv1): 1-ke-banyak.** Satu gudang **milik satu bisnis**; gudang bisnis A tak boleh muncul/dipakai bisnis B. → **FK ke `EntitasBisnis` (lv1).**
- **Gudang ↔ cabang (lv2/lv3): many-to-many.** Di dalam satu bisnis, satu gudang boleh dipakai banyak cabang dan satu cabang boleh punya banyak gudang. Relasi ini **tidak** dimodelkan sebagai FK/tabel; ia **muncul dari data transaksi** (kombinasi tier-EB + warehouse pada tiap `StockMovement`).

---

## B. Prinsip Desain

- **W1 — Warehouse = lokasi fisik, di-scope ke bisnis (lv1).** Bukan pemilik cabang tunggal; bukan dimensi akuntansi.
- **W2 — Gudang opsional.** `warehouse` nullable di seluruh alur; blank = escape hatch (perilaku lintas-gudang lama).
- **W3 — Kunci gudang, tanpa fallback antar gudang.** Bila transaksi menyebut gudang, konsumsi terkunci ke gudang itu; ambil dari gudang lain wajib transfer/mutasi dulu (Fase 6).
- **W4 — Tidak mengubah costing.** FIFO/bulk value-based tetap; warehouse hanya menambah filter. Same-warehouse (atau warehouse=None) menghasilkan angka HPP identik dengan Fase 2.
- **W5 — Isolasi tenant fail-loud.** Warehouse suatu movement wajib milik bisnis (lv1) movement itu; pelanggaran ditolak keras.

---

## C. Model Data

### `Warehouse` (baru, `apps/inventory/models.py`)

| Field | Tipe | Catatan |
|---|---|---|
| `entitas_bisnis` | `FK(entitas_bisnis.EntitasBisnis, on_delete=PROTECT)` | **lv1** = bisnis/tenant pemilik gudang |
| `kode` | `CharField` | kode gudang |
| `nama` | `CharField` | |
| `alamat` | `TextField(blank=True, null=True)` | opsional |
| `is_active` | `BooleanField(default=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

- `Meta.unique_together = (entitas_bisnis, kode)` — kode unik **per bisnis** (bisnis berbeda boleh punya kode "GD01" yang sama).
- `__str__` → `f'{kode} — {nama}'`.

### `StockMovement` (ubah)

Tambah:
- `warehouse = FK('inventory.Warehouse', on_delete=PROTECT, null=True, blank=True, related_name='stock_movements')`.
- Index baru: `Index(fields=['item', 'warehouse', 'remaining_qty'], name='idx_sm_item_wh_remaining')`.

Data lama: `warehouse = NULL` (tanpa backfill; NULL berperilaku persis seperti Fase 2).

### `StockConsumption`

Tidak berubah. Gudang layer inflow yang dikonsumsi sudah terekam di `in_movement.warehouse`.

### Invariant konsistensi tenant

Pada setiap penulisan movement (inflow & outflow), bila `warehouse` diisi maka **`warehouse.entitas_bisnis_id == movement.entitas_bisnis_id`** (lv1) wajib benar. Divalidasi di dua lapis:
1. **Form** (Purchase/Sales/Manufacturing/Saldo Awal) — dropdown sudah difilter, tapi validasi tetap ditegakkan.
2. **Ledger** (`record_inflow`/`consume_stock`) — raise `ValueError` (fail-loud) bila dilanggar, sebagai jaring pengaman terakhir.

---

## D. Semantik Ledger

`apps/inventory/ledger.py` — tanda tangan fungsi bertambah `warehouse=None`:

- `record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal, movement_type, source=None, *, warehouse=None, legacy_fifo_batch=None, legacy_inventory_record=None)`
- `consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type, source=None, metode='fifo', *, warehouse=None)`
- `get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None)`

### Aturan filter gudang di `_candidate_tiers`

Tambah parameter `warehouse` ke `_candidate_tiers`. Pada `base` queryset:
- **`warehouse` diisi (W)** → `base = base.filter(warehouse=W)`. **Exact match**: layer `warehouse IS NULL` **tidak** ikut. Konsumsi terkunci ke gudang W di dalam tier EB; **tanpa fallback antar gudang**.
- **`warehouse=None`** → **tanpa** filter warehouse. Konsumsi melihat semua layer (termasuk yang bergudang & yang NULL) dalam tier EB — perilaku Fase 2 identik.

Aturan ini otomatis berlaku sama untuk:
- Jalur non-bulk (`consume_stock`, memakai `_candidate_tiers`).
- Jalur bulk (`_consume_stock_bulk`, memakai `_candidate_tiers`).
- `get_available_stock` (memakai `_candidate_tiers`).

Fallback tier EB (lv3→lv2→lv1) **tetap** berjalan; warehouse hanya menyempitkan himpunan layer di tiap tier. `used_fallback`/`by_level`/`ConsumptionReport` tak berubah semantiknya.

### Validasi tenant di ledger

Di awal `record_inflow` dan `consume_stock`: bila `warehouse is not None and warehouse.entitas_bisnis_id != eb_lv1.pk` → `raise ValueError('Gudang <kode> bukan milik bisnis <eb_lv1>')`.

### Reversal

`reverse_movements` dan `reverse_inflow_movements` berbasis `source` — **tidak berubah**. Layer yang di-restore membawa `warehouse`-nya sendiri, jadi konsisten otomatis.

---

## E. Wiring Alur Transaksi

Keempat titik meneruskan `warehouse` (opsional) ke ledger. Dropdown gudang di form **difilter ke bisnis (lv1)** transaksi (hanya gudang aktif milik bisnis itu).

| Alur | Call site | Titik gudang |
|---|---|---|
| Pembelian (inflow) | `apps/purchase/services.py:186` (`record_inflow`) | 1 gudang tujuan penerimaan |
| Penjualan (outflow) | `apps/sales/services.py:244` & `:250` (`consume_stock`) | 1 gudang asal pengambilan |
| Manufaktur — RM keluar | `apps/manufacturing/services.py:345` (`consume_stock`) | 1 gudang asal bahan baku |
| Manufaktur — FG masuk | `apps/manufacturing/services.py:414` & `:661` (`record_inflow`, dua jalur) | 1 gudang tujuan hasil produksi |
| Saldo Awal | jalur `saldo_awal` (`record_inflow`) | 1 gudang penempatan saldo awal |

Field gudang **opsional** di semua form (blank diperbolehkan). Bila diisi, wajib lolos invariant tenant (bagian C).

**Catatan konsekuensi migrasi (bukan penghalang):** transaksi yang mulai menyebut gudang W tidak akan menyentuh layer lama ber-`warehouse=NULL`. Escape hatch: kosongkan gudang di transaksi, atau isi Saldo Awal per gudang saat go-live fitur ini.

---

## F. Admin & Query

- **Admin CRUD `Warehouse`**: list_display `kode, nama, entitas_bisnis, is_active`; filter per `entitas_bisnis` & `is_active`; search `kode, nama`.
- `StockMovement` admin (read-only, dari Fase 2): tambahkan `warehouse` ke list_display/list_filter agar audit per gudang terlihat.
- `get_available_stock(..., warehouse=W)` → saldo per gudang. Stock Card penuh per gudang = **Fase 8** (di luar cakupan).

---

## G. Rencana Testing

Semua di `apps/inventory/tests.py` (append) + test alur di app masing-masing. Jalankan pada Postgres parity, bukan hanya SQLite.

1. **Kunci gudang:** dua inflow item sama, EB (lv1) sama, gudang A dan B; `consume_stock(warehouse=A)` hanya konsumsi layer A; stok B utuh.
2. **Insufficient walau gudang lain cukup:** minta qty > stok gudang A padahal gudang B punya → `InsufficientStockError`.
3. **Regresi Fase 2 (`warehouse=None`):** hasil konsumsi & HPP identik dengan baseline Fase 2 (karakterisasi FIFO tak berubah).
4. **Exact-match NULL:** `consume_stock(warehouse=W)` tidak menyentuh layer `warehouse=NULL`; `consume_stock(warehouse=None)` boleh menyentuh layer bergudang & NULL.
5. **Isolasi tenant:** `record_inflow`/`consume_stock` dengan gudang milik bisnis lain → `ValueError`.
6. **Bulk per gudang:** item RMB/FGB/ITMB value-based terkunci gudang sama seperti non-bulk.
7. **Reversal:** membatalkan `source` memulihkan `remaining_qty` ke layer di gudang asal.
8. **Form:** dropdown gudang hanya menampilkan gudang aktif milik bisnis transaksi; memilih gudang bisnis lain ditolak validasi.
9. **Regresi penuh:** suite 809 test tanpa kegagalan baru (baseline: hanya isu django-axes login-setup & pytest-import yang sudah ada sebelumnya).

---

## H. Non-Goal (tegas)

- Transfer/mutasi antar gudang → **Fase 6**.
- Stock Card / Inventory Movement / Valuation per gudang → **Fase 8**.
- Allow-list (tabel pemetaan) gudang↔cabang lv2/lv3 → tidak diperlukan (bebas dalam satu bisnis).
- Penghapusan/deprecate ledger lama (`FIFOBatch`/`InventoryRecord`) → di luar cakupan; mirror tetap dijaga seperti Fase 2.
- Menambah `warehouse` ke ledger lama (`FIFOBatch`/`InventoryRecord`) → tidak; keduanya sedang menuju deprecate.
- Costing multi-metode (LIFO/Average) → **Fase 3**, terpisah.

---

## I. Risiko & Mitigasi

- **Layer NULL ter-stranded** saat transaksi mulai memakai gudang → dokumentasikan escape hatch (kosongkan gudang / Saldo Awal per gudang); tak ada backfill otomatis agar tak menebak-nebak penempatan fisik.
- **`PROTECT` pada `StockMovement.warehouse`** mencegah penghapusan gudang yang sudah dipakai — disengaja (integritas audit). Nonaktifkan via `is_active=False`, bukan hapus.
- **Regresi FIFO** → dikunci oleh test karakterisasi jalur `warehouse=None` sebelum & sesudah perubahan.
