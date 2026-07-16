# Desain — Integrasi UI Fase 1 (UOM) & Fase 2 (Stock Ledger)

**Tanggal:** 2026-07-16
**Status:** Disetujui — siap ke rencana implementasi
**Ruang lingkup:** Melengkapi lapisan UI untuk fondasi UOM (Fase 1) dan Stock Ledger/Warehouse (Fase 2) yang backend-nya sudah matang. Tidak mengubah costing FIFO yang sudah benar.
**Referensi:** [2026-07-15-inventory-fixedassets-review-and-roadmap.md](2026-07-15-inventory-fixedassets-review-and-roadmap.md)

---

## A. Konteks & Temuan

Backend Fase 1 & 2 sudah selesai dan aktif dipakai:

- `uom.UnitOfMeasure`, `uom.ItemUOM`, `uom/conversion.py` (`to_stock_uom`, `from_stock_uom`, `convert`) — lengkap.
- `ItemMasterPurchase` punya FK `stock_uom`/`purchase_uom`/`sales_uom`; dirender di form item master ([item_master_form.html](../../templates/purchase/item_master_form.html)).
- `inventory.Warehouse`, `inventory.StockMovement`, `inventory.StockConsumption`; `inventory/ledger.py` (`record_inflow`, `consume_stock`, reversal) sudah warehouse-aware.
- Transaksi Purchase/Sales/Manufacturing sudah menulis `StockMovement` dan **sudah punya pemilih Gudang** (Purchase/Sales per-baris + "Gudang seragam"; Manufacturing `warehouse_rm`/`warehouse_fg`).

Yang belum ada adalah lapisan UI berikut:

1. Menu **Master Satuan** (`uom:list` ada tapi tak ter-link di sidebar).
2. **CRUD Gudang** — `Warehouse` hanya dapat dikelola via Django admin.
3. **CRUD Konversi Satuan Item** (`ItemUOM`) — hanya via Django admin.
4. **Konversi UOM aktif di form transaksi** (Purchase, Sales, Manufacturing) — qty yang diinput saat ini langsung dianggap satuan stok; belum ada pemilihan satuan + konversi.
5. **Stock Ledger / Kartu Stok** — belum ada view yang membaca `StockMovement`.

## B. Prinsip Desain

- **INV-1 — Ledger & costing selalu dalam base/stock_uom.** Konversi UOM terjadi **hanya di batas input**. Field kuantitas base yang sudah ada tetap otoritatif; semua kode hilir (FIFOBatch, InventoryRecord, StockMovement, simulasi biaya) tidak berubah.
- **INV-2 — Audit input.** Tiap surface transaksi menyimpan `input_uom` + `input_qty` (nilai yang diketik user) di samping kuantitas base, untuk keterlacakan & tampil ulang.
- **INV-3 — Nullable + kompatibel mundur.** Field baru nullable; transaksi lama tanpa `input_uom` menghasilkan angka identik.
- **INV-4 — Ikuti pola yang ada.** Semua view/template memakai gaya `ni-*`, decorator `@login_required`, dan filter akses EB via `_resolve_eb_lv1_ids`/`_get_eb_tree`.
- **INV-5 — Read-only viewer tidak menyentuh transaksi.** Ledger/Kartu Stok murni membaca `StockMovement`/`StockConsumption`.

## C. Rincian per Item

### C1. Menu "Master Satuan"

Tambah entri nav di submenu **Inventory** pada [base.html](../../templates/base.html) → `{% url 'uom:list' %}`. Tidak ada backend baru (views/urls/template `uom` sudah ada).

### C2. CRUD Gudang (Warehouse)

App `inventory`:

- **`forms.py`** — `WarehouseForm(ModelForm)`: `entitas_bisnis`, `kode`, `nama`, `alamat`, `is_active` (widget `ni-input`). Validasi `unique_together (entitas_bisnis, kode)` sudah di model.
- **`views.py`** — `warehouse_list`, `warehouse_create`, `warehouse_update`, `warehouse_toggle_active` (soft, tidak hard-delete karena `StockMovement.warehouse` PROTECT). Daftar difilter ke bisnis yang boleh diakses user via `_resolve_eb_lv1_ids`.
- **`urls.py`** — `warehouse/`, `warehouse/create/`, `warehouse/<pk>/edit/`, `warehouse/<pk>/toggle/`.
- **Template** — `inventory/warehouse_list.html`, `inventory/warehouse_form.html` (meniru pola list/form yang ada).
- **Menu** — Inventory → Gudang.

**Acceptance:** user non-admin dapat membuat/menyunting gudang untuk bisnisnya; gudang bisnis lain tidak muncul; menonaktifkan gudang tidak menghapus data movement.

### C3. CRUD Konversi Satuan Item (ItemUOM)

App `uom`:

- **`forms.py`** — `ItemUOMForm(ModelForm)`: `item`, `uom`, `qty_in_stock_uom`. Validasi: `uom` tidak boleh sama dengan `item.stock_uom`; `qty_in_stock_uom > 0`.
- **`views.py`** — `item_conversion_list` (filter per item), `item_conversion_create`, `item_conversion_update`, `item_conversion_delete`.
- **`urls.py`** — `konversi/`, `konversi/create/`, `konversi/<pk>/edit/`, `konversi/<pk>/delete/`.
- **Template** — `uom/item_conversion_list.html`, `uom/item_conversion_form.html`.
- **Menu** — Inventory → Konversi Satuan Item.

**Acceptance:** operator dapat mendefinisikan "1 carton = 24 pcs" untuk item tertentu; entri ini langsung dipakai `to_stock_uom` di form transaksi (C4).

### C4. Konversi UOM aktif di form transaksi

Prinsip INV-1/INV-2 diterapkan seragam. Saat simpan tiap baris/entri:

```
qty_base       = to_stock_uom(input_qty, input_uom, item)
total_value    = input_qty * harga_per_input_uom          # yang dilihat user
unit_price_base = total_value / qty_base                  # disimpan sbg unit cost base
```

Jika `input_uom` kosong (data lama / default), `qty_base = input_qty` dan `unit_price_base` = harga input — perilaku identik dengan sekarang.

Konversi dilakukan **server-side** di view (bukan JS) untuk menekan risiko. Front-end hanya menambah kolom pilih satuan dan menampilkan qty-base hasil konversi sebagai teks bantu. Daftar satuan yang valid per item (stock_uom + purchase/sales_uom + satuan ItemUOM) dikirim ke template sebagai `item_uoms_json` (mirip `WAREHOUSES` yang sudah ada).

| Modul | Titik input | Field base otoritatif (tak berubah) | Field baru (nullable) |
|---|---|---|---|
| Purchase | baris `PurchaseItem` | `quantity`, `unit_price` | `input_uom` (FK UnitOfMeasure), `input_qty` |
| Sales | baris `SalesItem` | `quantity`, `unit_price` | `input_uom`, `input_qty` |
| Manufacturing — BOM | `BOMLine` (master) | `qty_required` (base) | `input_uom`, `input_qty` |
| Manufacturing — Produksi | `ProductionOrder` | `qty_produced` (base) | `input_uom` (FK, satuan FG) |

Detail:

- **Purchase** — kolom "Satuan" per baris di [purchase_form.html](../../templates/purchase/purchase_form.html), default `item.purchase_uom` (fallback `stock_uom`). View `purchase_create`/`update` mengonversi sebelum membuat `PurchaseItem`/`FIFOBatch`/`InventoryRecord`/`StockMovement`.
- **Sales** — kolom "Satuan" per baris di [sales_form.html](../../templates/sales/sales_form.html), default `item.sales_uom`. View `sales_create`/`update` mengonversi sebelum `consume_stock`.
- **Manufacturing BOM** — form BOM: tiap baris pilih satuan RM (default `raw_material.purchase_uom`/`stock_uom`); `qty_required` disimpan dalam base. Karena `qty_required` tetap base, `get_bom_preview`/`_simulate_fifo_cost`/`process_production` **tidak berubah**.
- **Manufacturing Produksi** — form production order: pilih satuan FG untuk `qty_produced`; disimpan dalam base FG. `unit_cost = total_cost / qty_produced_base`.

**Acceptance (per modul):**
- Regresi: transaksi/BOM lama tanpa `input_uom` menghasilkan `quantity`/`unit_price`/HPP/biaya produksi identik.
- Konversi: pembelian "10 carton @ Rp X" dengan `1 carton = 24 pcs` menghasilkan `quantity = 240 pcs`, total nilai benar, FIFO/HPP saat dijual benar.
- BOM "1 unit FG butuh 2 carton RM" → konsumsi RM base benar saat produksi.

### C5. Stock Ledger / Kartu Stok (read-only)

App `inventory`, dua view membaca `StockMovement`/`StockConsumption`:

- **Buku Persediaan (Ledger)** — `stock_ledger`: filter item · EB (tree) · gudang · rentang tanggal. Menampilkan daftar pergerakan (masuk/keluar) terurut tanggal, biaya satuan, dan **saldo berjalan** (running balance) dari agregasi qty.
- **Kartu Stok per item** — `stock_card`: layer inflow aktif (`remaining_qty > 0`) FIFO, alokasi konsumsi (`StockConsumption`), dan saldo per EB/gudang.

- **`urls.py`** — `ledger/`, `kartu-stok/` (opsional `kartu-stok/<item_id>/`).
- **Template** — `inventory/stock_ledger.html`, `inventory/stock_card.html`.
- **Menu** — Inventory → Kartu Stok.

**Acceptance:** saldo berjalan cocok dengan agregasi `StockMovement`; filter gudang/EB mengisolasi hasil dengan benar; halaman tidak menulis apa pun.

## D. Ringkasan Perubahan File

- **`apps/inventory/`**: `forms.py` (+WarehouseForm), `views.py` (+warehouse CRUD, +stock_ledger, +stock_card), `urls.py`, template baru: `warehouse_list.html`, `warehouse_form.html`, `stock_ledger.html`, `stock_card.html`.
- **`apps/uom/`**: `forms.py` (+ItemUOMForm), `views.py` (+ItemUOM CRUD), `urls.py`, template baru: `item_conversion_list.html`, `item_conversion_form.html`.
- **`apps/purchase/`**: `models.py` (+`input_uom`/`input_qty` di `PurchaseItem` + migrasi), `views.py` (konversi saat create/update), `templates/purchase/purchase_form.html` (+kolom Satuan + `item_uoms_json`).
- **`apps/sales/`**: `models.py` (+`input_uom`/`input_qty` di `SalesItem` + migrasi), `views.py`, `templates/sales/sales_form.html`.
- **`apps/manufacturing/`**: `models.py` (+`input_uom`/`input_qty` di `BOMLine`, +`input_uom` di `ProductionOrder` + migrasi), `forms.py`/`views.py` (konversi), template BOM & production form (+kolom/pilih Satuan).
- **`templates/base.html`**: 4 entri menu di submenu Inventory (Master Satuan, Konversi Satuan Item, Gudang, Kartu Stok).

Model transaksi `warehouse` & `inventory/ledger.py` sudah siap — tidak diubah.

## E. Risiko & Mitigasi

- **Regresi costing (C4):** kunci perilaku FIFO/HPP/biaya produksi lama dengan test sebelum menambah konversi; jalur `input_uom` kosong harus identik dengan sekarang.
- **Konsistensi harga vs qty (C4):** selalu turunkan `unit_price_base` dari `total_value / qty_base` agar `total_value` yang dilihat user tetap sumber kebenaran; hindari pembulatan ganda.
- **Konversi tak terdefinisi:** bila `to_stock_uom` gagal (tak ada `ItemUOM` maupun faktor universal), form menolak dengan pesan eksplisit — jangan diam-diam pakai qty apa adanya.
- **Warehouse PROTECT:** gudang dinonaktifkan (soft), tidak dihapus, karena dirujuk `StockMovement`.

## F. Di Luar Ruang Lingkup

- Migrasi "Daftar Inventory" & "Laporan Persediaan" lama agar bersumber dari `StockMovement` (bagian Fase 8).
- Costing multi-metode (LIFO/Average) — Fase 3.
- POS (arsitektur terpisah).
