# Desain — Master Satuan (UOM) & Konversi (Fase 1)

**Tanggal:** 2026-07-15
**Status:** Disetujui (siap disusun rencana implementasi)
**Bagian dari:** [Roadmap Inventory & Aset Tetap](2026-07-15-inventory-fixedassets-review-and-roadmap.md) — Fase 1 (High Priority)
**Ruang lingkup:** Master satuan standar + mesin konversi hybrid. Fondasi lintas modul (Inventory, Purchase, Sales, POS, Manufacturing). TIDAK mengubah costing/stock ledger (itu Fase 2).

---

## 1. Tujuan & Konteks

Requirement menuntut master satuan bawaan (metrik + satuan bisnis umum), konversi otomatis antar satuan yang dapat dikonfigurasi, satuan kustom, dan penggunaan satuan berbeda per proses bisnis (beli Karton → simpan PCS → produksi Gram/mL → jual PCS) dengan konversi otomatis agar stok/costing/HPP tetap akurat. Desain harus generic, reusable, dan siap untuk BOM/Manufacturing tanpa mengubah skema.

Saat ini **tidak ada** master satuan maupun field satuan pada item master ([apps/purchase/models.py:49](../../../apps/purchase/models.py)). Ini gap fondasi yang harus diselesaikan lebih dulu karena menyentuh semua modul.

## 2. Keputusan Desain (terkunci)

- **Model konversi: Hybrid.** Konversi fisik universal (kg↔g, L↔mL) memakai faktor global per dimensi; konversi kemasan yang berbeda tiap produk (carton→pcs, box→pcs) memakai tabel per-item. Pola standar ERP (mirip Odoo/SAP), paling akurat untuk multi-satuan & BOM.
- **Ruang lingkup Fase 1: fondasi + CRUD + utilitas.** Model, seed, field UOM di item master, UI kelola satuan, dan fungsi `convert()` teruji. BELUM menyambung ke transaksi Purchase/Sales/POS agar tidak bentrok dengan rebuild ledger Fase 2.
- **Penempatan: app baru `apps/uom`.** Batas domain jelas dan netral; modul lain meng-import dari `uom`, bukan sebaliknya.

## 3. Prinsip

- **Reusable & netral:** `uom` tidak bergantung pada modul lain (kecuali FK item master untuk `ItemUOM`).
- **Satu unit kanonik per item (`stock_uom`)** menjadi acuan semua konversi item tersebut.
- **Konversi fisik universal tidak butuh konteks item;** konversi kemasan butuh konteks item.
- **Gagal keras, bukan diam-diam salah:** konversi yang tak dapat diselesaikan melempar `ConversionError`.
- **YAGNI:** tanpa `base_uom` terpisah (redundan dengan `stock_uom`); tanpa kemasan berjenjang di fase ini.

## 4. Model Data

### 4.1 `UnitOfMeasure` — registry satuan global
| field | tipe | catatan |
|---|---|---|
| `kode` | CharField, unique | mis. `kg`, `g`, `pcs`, `carton` |
| `nama` | CharField | |
| `dimension` | CharField choices | `count`, `weight`, `volume`, `length`, `area` |
| `factor_to_base` | DecimalField, null=True | faktor universal ke base dimensinya. **null** untuk satuan kemasan yang berbeda tiap produk (carton, box, pack, dus, roll, botol) |
| `is_base` | BooleanField | satuan dasar dimensi (factor = 1). Tepat satu base per dimensi |
| `is_system` | BooleanField | bawaan seed — dilindungi dari hapus/ubah kode |
| `is_active` | BooleanField default True | |

Aturan integritas:
- Tepat satu `is_base=True` per `dimension`.
- Satuan fisik (weight/volume/length/area) **wajib** punya `factor_to_base`.
- Satuan `count` boleh punya `factor_to_base` global (pcs=1, unit=1, lusin=12, gross=144) atau `null` (kemasan per-item: box/pack/carton/dus/roll/botol).
- `is_system=True` tidak boleh dihapus; `kode`-nya tidak boleh diubah.

### 4.2 `ItemUOM` — konversi kemasan per-item
| field | tipe | catatan |
|---|---|---|
| `item` | FK `purchase.ItemMasterPurchase` | on_delete=CASCADE |
| `uom` | FK `UnitOfMeasure` | mis. carton |
| `qty_in_stock_uom` | DecimalField | jumlah `stock_uom` dalam 1 satuan ini. 1 carton = 24 pcs → `24` |
| Meta | unique_together `(item, uom)` | |

### 4.3 Tambahan pada `ItemMasterPurchase`
Field baru (nullable dulu; data migration backfill default `pcs`; tetap nullable di Fase 1 agar item lama tidak putus):
- `stock_uom` FK `UnitOfMeasure` — satuan penyimpanan/penilaian (kanonik item).
- `purchase_uom` FK `UnitOfMeasure` — default satuan saat pembelian.
- `sales_uom` FK `UnitOfMeasure` — default satuan saat penjualan.

Tidak ada `base_uom` terpisah.

## 5. Mesin Konversi

Modul `apps/uom/conversion.py`:

```
class ConversionError(Exception): ...

def convert(qty: Decimal, from_uom, to_uom, item=None) -> Decimal:
    # 1. from == to  -> qty
    # 2. dimensi sama & keduanya punya factor_to_base
    #    -> qty * from.factor_to_base / to.factor_to_base    (universal, item tak perlu)
    # 3. melibatkan satuan kemasan (factor_to_base null) -> butuh item:
    #    konversi from -> item.stock_uom -> to  via ItemUOM.qty_in_stock_uom
    #    (dan/atau factor_to_base bila sisi lain sedimensi dgn stock_uom)
    # 4. tak dapat diselesaikan -> raise ConversionError
```

Algoritma langkah 3 (umum): konversi `from_uom → stock_uom` lalu `stock_uom → to_uom`.
- `X → stock_uom`: jika X kemasan → `qty * ItemUOM(item, X).qty_in_stock_uom`; jika X sedimensi dengan `stock_uom` & punya factor → pakai faktor global; jika X = stock_uom → apa adanya.
- `stock_uom → Y`: kebalikannya.
- Jika data ItemUOM yang diperlukan tidak ada → `ConversionError`.

Fungsi helper: `to_stock_uom(qty, from_uom, item)` dan `from_stock_uom(qty, to_uom, item)` dipakai internal + berguna untuk fase penyambungan transaksi nanti.

## 6. Seed Data Bawaan (data migration, `is_system=True`)

| Dimensi | Satuan (kode: factor_to_base) |
|---|---|
| count | **pcs (base=1)**, unit (1), lusin (12), gross (144), box (null), pack (null), carton (null), dus (null), roll (null), botol (null) |
| weight | **g (base=1)**, mg (0.001), kg (1000), ton (1 000 000) |
| volume | **mL (base=1)**, cc (1), L (1000), m³ (1 000 000) |
| length | **mm (base=1)**, cm (10), m (1000) |
| area | **m² (base=1)**, cm² (0.0001) |

Base unit dipilih paling kecil yang praktis untuk meminimalkan pecahan. Seed idempotent (aman dijalankan ulang; pakai `get_or_create` by `kode`).

## 7. CRUD / UI

- **Kelola Satuan:** halaman list + form create/edit satuan kustom (dimensi, factor_to_base, is_active). `is_system` read-only & tidak dapat dihapus. Django admin juga tersedia.
- **ItemUOM:** inline pada form item master (dan admin) untuk mendefinisikan kemasan per-item (uom + qty_in_stock_uom).
- Pilihan `stock_uom`/`purchase_uom`/`sales_uom` ditambahkan pada form item master.

## 8. Strategi Migrasi

1. Migrasi skema: buat `UnitOfMeasure`, `ItemUOM`; tambah 3 FK nullable pada `ItemMasterPurchase`.
2. Data migration seed satuan bawaan (idempotent).
3. Data migration backfill: set `stock/purchase/sales_uom = pcs` untuk item yang ada.
4. FK dibiarkan nullable di Fase 1 (pengetatan non-null menyusul saat penyambungan transaksi).

## 9. Testing

- `convert()`:
  - fisik: kg→g (=1000×), L→mL, mm↔m.
  - kemasan per-item: carton→pcs (item A=24, item B=12) menghasilkan hasil berbeda.
  - satuan sama → identitas.
  - error: kemasan tanpa `item`; pasangan tak kompatibel (mis. kg→pcs tanpa data) → `ConversionError`.
- Seed migration: tiap dimensi punya tepat satu base; kode unik.
- Backfill: item lama memperoleh `pcs`.
- Guard: `is_system` tidak dapat dihapus.

## 10. Non-Goals (Fase 1)

- Penyambungan konversi ke transaksi Purchase/Sales/POS (form input per-baris dalam purchase_uom/sales_uom).
- Kemasan berjenjang (carton→box→pcs).
- Pengetatan FK UOM menjadi wajib (non-null).

Semua di atas menyusul di fase berikutnya di atas fondasi ini.
