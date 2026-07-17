# Desain — Costing Multi-Metode (Fase 3)

**Tanggal:** 2026-07-17
**Status:** Disetujui (siap plan)
**Ruang lingkup:** Engine costing `apps/inventory/ledger.py` dan para pemakainya (Sales, Manufacturing). Melanjutkan Fase 3 dari roadmap `2026-07-15-inventory-fixedassets-review-and-roadmap.md`.
**Prasyarat (sudah selesai):** Fase 1 (UOM), Fase 2 (StockMovement/StockConsumption/Warehouse + isolasi EB).

---

## A. Latar & Masalah

`consume_stock` sudah menerima parameter `metode='fifo'` tetapi **mengabaikannya** — selalu FIFO (urutan `tanggal, created_at`). Sekaligus, para pemanggil (`process_sales_fifo`, konsumsi RM manufaktur) memanggil `consume_stock` **tanpa** meneruskan metode, sehingga `item.metode_biaya_persediaan` yang dipilih user saat registrasi item **tidak pernah dipakai** saat costing.

Item master (`purchase.ItemMasterPurchase.metode_biaya_persediaan`) menyediakan 4 pilihan: `fifo`, `lifo`, `average`, `weighted_moving_average`.

Tujuan Fase 3: satu entry point `consume_stock(item, eb, gudang, qty, metode)` dengan FIFO/LIFO/Average di belakang antarmuka yang sama (Prinsip P2 roadmap), dan metode benar-benar dihormati per item.

---

## B. Keputusan Desain

1. **Tiga strategi diimplementasikan:** FIFO, LIFO, dan satu **moving weighted average**. Baik `average` maupun `weighted_moving_average` dipetakan ke engine moving-average yang sama.
2. **Sumber metode:** per-item, dari `item.metode_biaya_persediaan` (dipilih user saat registrasi). Caller meneruskan nilai mentah ini ke `consume_stock`; engine yang menormalkan + memvalidasi.
3. **Metode tak dikenal → `ValueError` eksplisit.** Kosong `''` → default FIFO. Jangan pernah diam-diam FIFO untuk string yang tak dikenal.
4. **Item bulk (RMB/FGB/ITMB) method-agnostic:** jalur bulk `_consume_stock_bulk` tetap value-based dan **mengabaikan** metode. Costing method hanya berlaku untuk item non-bulk.
5. **Average = pengurangan proporsional** (lihat §D.3) — menyempurnakan gagasan awal "kurangi qty FIFO", agar moving-average tetap benar pada penjualan berulang.

---

## C. Resolusi & Validasi Metode

Helper di `apps/inventory/ledger.py`:

```python
_METHOD_ALIASES = {
    '': 'fifo',
    'fifo': 'fifo',
    'lifo': 'lifo',
    'average': 'average',
    'weighted_moving_average': 'average',
}

def _normalize_method(metode: str) -> str:
    """Petakan pilihan item ke strategi engine. Tak dikenal → ValueError."""
    key = (metode or '').strip().lower()
    if key not in _METHOD_ALIASES:
        raise ValueError(f'Metode biaya persediaan tak didukung: {metode!r}')
    return _METHOD_ALIASES[key]
```

Dipanggil di awal `consume_stock` (non-bulk). Nilai internal engine: `'fifo' | 'lifo' | 'average'`.

---

## D. Perilaku Engine (jalur non-bulk)

Isolasi hierarki EB (lv3 → lv2 → lv1) dan validasi tenant gudang **tak berubah**. Yang berubah hanya urutan pengambilan **dalam satu tier** dan cara menghitung biaya.

### D.1 FIFO (perilaku sekarang)
- Urutan layer dalam tier: `('tanggal', 'created_at')` asc (tertua dulu).
- Biaya tiap alokasi = `layer.unit_cost`.

### D.2 LIFO
- Urutan layer dalam tier: `('-tanggal', '-created_at')` (terbaru dulu).
- Biaya tiap alokasi = `layer.unit_cost`.
- **Fallback hierarki EB tetap deepest-first** (lv3→lv2→lv1). Hanya urutan *di dalam* tier yang dibalik, bukan urutan tier.

### D.3 Moving weighted average (proporsional)
Untuk qty yang dilayani oleh sebuah tier:

- Hitung `avg = Σ(remaining_qty × unit_cost) / Σ(remaining_qty)` atas seluruh layer aktif (`remaining_qty > 0`) tier tersebut, **sebelum** pengurangan.
- Jika qty yang diminta ≥ total qty tier → konsumsi seluruh layer tier (setiap layer → 0), lalu lanjut ke tier berikutnya (recompute avg untuk tier itu).
- Jika qty yang diminta < total qty tier (tier terakhir yang dikonsumsi sebagian) → kurangi **proporsional**: `fraksi = qty_diminta / total_qty_tier`; `take_layer = layer.remaining_qty × fraksi`.
  - **Pembulatan:** kuantisasi tiap `take_layer` ke 4 desimal; sisa selisih (agar `Σ take = qty_diminta` persis) dibebankan ke layer terakhir dalam daftar.
- COGS tier = `qty_dilayani × avg`. Tiap `StockConsumption` dicatat dengan `unit_cost = avg` (bukan `layer.unit_cost`), `qty = take_layer`.

**Alasan proporsional (bukan FIFO-order):** dengan pengurangan proporsional, sisa pool mempertahankan `avg` yang sama untuk penjualan berikutnya, dan valuasi berbasis layer (`Σ remaining_qty × unit_cost`) tetap konsisten dengan valuasi average. Pengurangan urutan-FIFO akan mencondongkan pool ke layer mahal sehingga average penjualan berikutnya menggelembung (salah).

*Contoh:* L1 = 10 @ 100, L2 = 10 @ 200 (avg 150). Jual 5:
- COGS = 5 × 150 = 750.
- Proporsional (fraksi 0.25): L1 → 7.5, L2 → 7.5. Sisa nilai = 7.5×100 + 7.5×200 = 2250; avg = 2250/15 = **150** ✓.
- (Bandingkan urutan-FIFO: sisa 5@100 + 10@200 → avg 166.67 ✗.)

### D.4 out_movement & alokasi
- `out_movement.qty = -qty`, `out_movement.unit_cost = total_cost / qty` (blended untuk FIFO/LIFO; sama dengan avg untuk average), `remaining_qty = 0` — konsisten dengan implementasi sekarang.
- `StockConsumption` per layer tetap dibuat (untuk audit trail & reversal). Untuk average, `qty = take_layer` dan `unit_cost = avg`.
- Mirror ke legacy `FIFOBatch`/`InventoryRecord` (`_mirror_decrement`) tetap memakai `take_qty` per layer — tak berubah.

---

## E. Catatan Valuasi (average)

Untuk item average, valuasi sisa stok **harus** dihitung sebagai `qty × moving_avg`. Dengan pengurangan proporsional (§D.3), `Σ remaining_qty × unit_cost` per tier tetap sama dengan valuasi average, sehingga laporan valuasi berbasis layer tetap benar tanpa perlakuan khusus. Ini adalah alasan tambahan memilih proporsional.

---

## F. Struktur Kode

Semua di `apps/inventory/ledger.py`:

- Tambah `_normalize_method` + peta alias (§C).
- `_candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse=None, *, order='fifo')` — parameter `order` mengatur urutan dalam tier: `'fifo'` → asc, `'lifo'` → desc. Untuk `average` gunakan urutan deterministik (`'fifo'` asc) karena hasil proporsional tak bergantung urutan.
- `consume_stock(...)`:
  1. `_validate_warehouse_tenant`, hitung `req_level/req_rank` (tak berubah).
  2. Jika bulk → `_consume_stock_bulk` (tak berubah; metode diabaikan).
  3. `method = _normalize_method(metode)`.
  4. Loop tier memanggil helper konsumsi per-tier sesuai strategi:
     - `_consume_tier_sequential(layers_qs, remaining)` untuk FIFO/LIFO (ambil `layer.unit_cost`).
     - `_consume_tier_average(layers_qs, remaining)` untuk average (hitung avg, ambil proporsional, `unit_cost=avg`).
     Keduanya mengembalikan `(picked, tier_cost, tier_qty)`; `picked = [(layer, take, unit_cost_alokasi)]`.
  5. Agregasi lintas tier untuk `total_cost`, `per_level`, `by_level`, `used_fallback` — logika laporan fallback tak berubah.
  6. Buat `out_movement` + `StockConsumption` dari `picked`.

`select_for_update` tetap dipakai saat mengambil layer sebuah tier (konsistensi konkuren).

---

## G. Wiring Caller

1. **Sales** — `apps/sales/services.py process_sales_fifo`: kedua panggilan `consume_stock` (bulk & non-bulk) tambahkan `metode=si.item.metode_biaya_persediaan`. (Untuk bulk parameter diabaikan engine, tapi diteruskan agar seragam.)
2. **Manufacturing — konsumsi RM** — `apps/manufacturing/services.py:~345`: panggilan `consume_stock` untuk RM tambahkan `metode=<rm_item>.metode_biaya_persediaan`.
3. **Manufacturing — simulasi preview RM** — `apps/manufacturing/services.py:53-68`: fungsi simulasi read-only kini hardcode urutan FIFO (`order_by('tanggal','created_at')`). Buat method-aware sehingga estimasi biaya cocok dengan posting nyata:
   - LIFO → urutan `('-tanggal','-created_at')`.
   - Average → hitung `qty × avg` dari layer aktif (tanpa tulis DB).
   - FIFO → seperti sekarang.

---

## H. Test (Acceptance)

Semua di `apps/inventory/tests.py` (atau modul test costing baru) kecuali disebutkan.

**HPP terverifikasi manual:**
- FIFO: dua layer beda harga, konsumsi menembus batas layer → biaya sesuai urutan tertua.
- LIFO: setup sama → biaya sesuai urutan terbaru.
- Average: hitung `qty × avg` benar untuk satu penjualan.
- **Average berulang:** dua penjualan berturut → penjualan kedua memakai avg yang **tetap** (mengunci invariant proporsional §D.3), bukan avg yang menggelembung.

**Perilaku metode:**
- Metode `''` → FIFO.
- `weighted_moving_average` → hasil sama dengan `average`.
- Metode tak dikenal (mis. `'xyz'`) → `ValueError`.

**Isolasi & bulk:**
- Item bulk mengabaikan metode (LIFO/average pada item bulk berperilaku sama dengan value-based sekarang).
- LIFO/average tetap menghormati isolasi hierarki EB (tak bocor antar cabang) dan gudang.

**Reversal:**
- Reversal penjualan average mengembalikan `remaining_qty` tiap layer sesuai proporsi yang diambil (pool kembali utuh, avg kembali seperti semula).

**Regresi:**
- Test FIFO Fase 2 yang ada tetap hijau (perilaku default tak berubah).

---

## I. Risiko & Mitigasi

- **Drift average** bila keliru pakai urutan FIFO — dimitigasi dengan pengurangan proporsional (§D.3) + test average berulang (§H).
- **Pembulatan proporsional** meninggalkan dust di layer — dimitigasi dengan membebankan sisa selisih ke layer terakhir agar `Σ take = qty` persis.
- **Perubahan perilaku diam-diam** untuk item yang sudah diset LIFO/average tapi selama ini di-cost FIFO — ini justru koreksi yang diinginkan; dikunci test. Data historis tak di-recompute (hanya transaksi baru).
