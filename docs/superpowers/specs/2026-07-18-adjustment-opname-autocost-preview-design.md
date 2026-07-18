# Adjustment & Opname — Auto-Cost, Purchase-Style Entity Picker, dan Preview — Design

**Tanggal:** 2026-07-18
**Status:** Disetujui — siap ke tahap perencanaan (writing-plans)
**Halaman terdampak:** `/inventory/adjustment/create/` dan `/inventory/opname/create/`
**Fondasi:** Fase 6 (Transaksi & Kontrol Stok) sudah live — lihat [2026-07-17-fase6-inventory-stock-transactions-design.md](2026-07-17-fase6-inventory-stock-transactions-design.md). Ledger `StockMovement`, `process_adjustment`/`process_opname`, dan isolasi EB/gudang tidak diubah perilakunya.

---

## A. Tujuan

Menyelaraskan form **Stock Adjustment** dan **Stock Opname** dengan pola form **Tambah Purchase**, dan menambah transparansi sebelum posting:

1. **Harga/unit otomatis** ditarik dari sistem sesuai **metode costing item** (FIFO/LIFO/Average/WMA) — bukan diketik buta.
2. **Pemilihan entitas bisnis** memakai UX yang sama seperti tambah purchase: satu dropdown hierarkis (lv1/lv2/lv3) + gudang otomatis terfilter.
3. **Tanggal default** = hari ini.
4. **Preview Jurnal** + **Preview Mutasi Persediaan** sebelum posting.
5. **Memastikan** modul persediaan lewat ledger `StockMovement` benar-benar terupdate (verifikasi via test + preview yang identik dengan posting).

**Di luar cakupan:** transfer & retur (form terpisah, tidak diubah); perubahan model header/detail (adjustment & opname tetap **satu entitas per dokumen**); mapping COA otomatis per kategori.

---

## B. Prinsip yang dipertahankan

- **Satu entitas per dokumen.** Adjustment/Opname header tetap punya satu `entitas_bisnis` (+`_lv2`/`_lv3` nullable). "Seperti purchase" hanya soal **UX pemilihan**, bukan multi-entitas per grup.
- **Costing sebagai strategy.** Semua harga acuan & biaya penurunan stok mengikuti `item.metode_biaya_persediaan` — tidak ada rata-rata tertimbang yang dipaksakan.
- **Preview == Posting.** Angka preview dihitung dari simulasi posting yang sesungguhnya (savepoint + rollback), bukan estimasi terpisah, sehingga tidak pernah menyimpang dari hasil akhir.
- **Ledger sebagai satu-satunya sumber.** Saldo & nilai stok selalu dari `StockMovement`.

---

## C. Pemilihan Entitas Bisnis (kedua form)

File: [apps/inventory/forms.py](../../../apps/inventory/forms.py), [templates/inventory/adjustment_form.html](../../../templates/inventory/adjustment_form.html), [templates/inventory/opname_form.html](../../../templates/inventory/opname_form.html), [apps/inventory/views.py](../../../apps/inventory/views.py).

### C.1 Dropdown hierarkis tunggal
- Ganti tiga select (`entitas_bisnis` / `entitas_bisnis_lv2` / `entitas_bisnis_lv3`) di **template** dengan **satu** dropdown hierarkis indent, opsinya dibangun dari `_get_eb_dropdown_options(user)` (helper existing di [apps/purchase/views.py](../../../apps/purchase/views.py), nilai `lv1:<pk>` / `lv2:<pk>` / `lv3:<pk>`). Helper ini dipindahkan/di-share (lihat C.4).
- Tambah field form **`eb_hierarki`** (`ChoiceField`, satu nilai). Tiga field model (`entitas_bisnis`, `_lv2`, `_lv3`) **tetap ada di model** tapi tidak lagi ditampilkan sebagai input terpisah; nilainya diisi dari resolusi `eb_hierarki`.

### C.2 Resolusi di `clean()`
- `lv1:<pk>` → `entitas_bisnis=pk`, lv2=None, lv3=None.
- `lv2:<pk>` → `entitas_bisnis_lv2=pk`, `entitas_bisnis`=parent lv1, lv3=None.
- `lv3:<pk>` → `entitas_bisnis_lv3=pk`, `entitas_bisnis_lv2`=parent lv2, `entitas_bisnis`=parent lv1.
- Set ketiga FK ke `cleaned_data` sebelum `save()`. Validasi lingkup gudang existing (`_validate_warehouse_scope`) tetap jalan terhadap **lv1** hasil resolusi.

### C.3 Gudang otomatis terfilter + tanggal default
- Warehouse dropdown tetap memakai `EntitasScopedSelect` + [_warehouse_scope_js.html](../../../templates/inventory/_warehouse_scope_js.html), namun sekarang difilter oleh **lv1 hasil resolusi** dari `eb_hierarki` (JS membaca prefix `lv1:`/`lv2:`/`lv3:` untuk menentukan lv1 pemilik, sama seperti `getEBLv1Id` di purchase). Opsi gudang yang tak sesuai lv1 disembunyikan.
- View meng-set `initial={'tanggal': timezone.localdate()}` saat GET (kedua form), meniru purchase.

### C.4 Sharing helper
- Pindahkan `_get_eb_dropdown_options` ke lokasi yang bisa diimpor kedua modul (mis. `apps/entitas_bisnis/utils.py` atau helper bersama), lalu purchase & inventory mengimpornya. Bila risiko refactor terlalu luas, minimal impor langsung dari `apps.purchase.views` — **keputusan: pindahkan ke `apps/entitas_bisnis/`** agar tidak ada dependensi inventory→purchase untuk hal presentational.

---

## D. Harga/Unit Otomatis (per metode costing)

File: [apps/inventory/ledger.py](../../../apps/inventory/ledger.py), [apps/inventory/views.py](../../../apps/inventory/views.py) (endpoint `stock_available`), template kedua form.

### D.1 Helper ledger baru
```python
def current_unit_cost(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None, metode=None) -> Decimal | None:
    """Harga acuan per unit dari layer StockMovement tersisa, mengikuti metode costing item.

    FIFO    -> unit_cost layer tersisa TERTUA (yang akan keluar berikutnya)
    LIFO    -> unit_cost layer tersisa TERBARU
    average / weighted_moving_average -> rata-rata tertimbang layer tersisa
    Kembalikan None bila tidak ada stok tersisa di scope (item baru / belum ada layer).
    """
```
- `metode` default `item.metode_biaya_persediaan`.
- Scope layer memakai iterator tier yang sama dengan `get_available_stock`/`consume_stock` (`_candidate_tiers`) agar konsisten dengan isolasi EB hierarkis + kunci warehouse. Hanya layer dengan `remaining_qty > 0` yang dihitung.
- Untuk FIFO/LIFO pemilihan layer mengikuti urutan yang dipakai `consume_stock` (tanggal/urutan yang sama), sehingga "harga acuan" = biaya unit berikutnya yang benar-benar akan dikonsumsi.

### D.2 Endpoint `stock_available` diperluas
- Tambah `unit_cost` ke respons JSON (di samping `available` yang sudah ada). `unit_cost = str(current_unit_cost(...))` atau `null` bila `None`.
- Parameter tetap: `item`, `warehouse`, `eb`, `eb_lv2`, `eb_lv3`. EB diambil dari `eb_hierarki` terpilih (JS mengirim lv1/lv2/lv3 hasil parse).

### D.3 Perilaku field Harga/Unit di form
- Saat baris item dipilih (atau entitas/gudang berubah), JS memanggil `stock_available` dan **mengisi otomatis** field `unit_cost` (adjustment) / `unit_cost` per baris (opname). Field **tetap editable** (user boleh override untuk koreksi naik pada harga tertentu).
- **Opname**: `qty_sistem` tetap terisi otomatis seperti sekarang; `unit_cost` kini juga terisi otomatis dari respons yang sama.
- **Bila `unit_cost` = null (belum ada stok di scope):** field dibiarkan **kosong** dan baris menampilkan **badge peringatan** inline ("Belum ada stok di entitas/gudang ini — isi harga manual") agar user waspada. Tidak memblokir submit (koreksi naik barang baru itu sah).

---

## E. Preview Jurnal & Mutasi Persediaan

File: [apps/inventory/views.py](../../../apps/inventory/views.py), template kedua form (modal), JS.

### E.1 Endpoint preview (simulasi posting sesungguhnya)
- Endpoint baru **`adjustment_preview`** dan **`opname_preview`** (POST, menerima payload form+formset yang sama dengan submit).
- Implementasi: di dalam `transaction.atomic()`, gunakan savepoint:
  1. Validasi form+formset (kembalikan error bila invalid, tanpa menyentuh DB).
  2. `save()` header+items (unsaved→saved di dalam savepoint).
  3. Panggil `process_adjustment` / `process_opname` yang **sesungguhnya**.
  4. Baca kembali `JurnalDetail` (akun, debit, kredit) dari `JurnalHeader` hasil, dan `StockMovement` per item (movement_type, qty, unit_cost, remaining_qty).
  5. Hitung mutasi: untuk tiap item, `stok_sebelum = get_available_stock(scope)` (diambil sebelum langkah 3), `stok_sesudah = stok_sebelum + delta`, `nilai` = kontribusi jurnal item tsb.
  6. **Rollback** savepoint (`transaction.set_rollback(True)` lalu keluar, atau raise sentinel yang ditangkap) sehingga TIDAK ada yang tersimpan.
- Keunggulan: memakai jalur costing yang persis sama → biaya penurunan FIFO/LIFO akurat, jurnal pasti balance, preview tidak akan berbeda dari posting.
- Catatan implementasi: `process_*` butuh instance tersimpan (FK source ke movement). Karena semua di dalam savepoint yang di-rollback, tidak ada residu. Nomor dokumen/jurnal auto-generate ikut ter-rollback.

### E.2 Payload respons JSON
```json
{
  "ok": true,
  "balance": true,
  "jurnal": [{"akun": "1-1300 Persediaan", "debit": "500000", "kredit": "0"}, ...],
  "total_debit": "500000", "total_kredit": "500000",
  "mutasi": [
    {"item": "RM-001", "movement_type": "adjustment_in",
     "stok_sebelum": "10", "delta": "5", "stok_sesudah": "15",
     "unit_cost": "1000", "nilai": "5000"},
    {"item": "RM-002", "movement_type": "-", "delta": "0", "catatan": "tidak ada mutasi"}
  ]
}
```
Bila form invalid: `{"ok": false, "errors": {...}}`.

### E.3 UI modal
- Tombol **"Preview Jurnal & Mutasi"** di sebelah tombol Submit. Meng-`fetch` endpoint preview dengan `FormData` form, lalu membuka modal (markup `ni-modal` seperti [purchase_form.html](../../../templates/purchase/purchase_form.html) journal modal).
- Modal berisi dua panel:
  - **Preview Jurnal**: tabel Akun / Debit / Kredit + baris total dengan indikator balance (hijau bila `debit == kredit`).
  - **Preview Mutasi Persediaan**: tabel per item → Stok Sistem Sebelum → Sesudah, Qty Delta, Nilai (Rp), Tipe Movement. Baris selisih 0 (opname) ditandai "tidak ada mutasi".
- Modal read-only; posting tetap lewat tombol Submit.

---

## F. Memastikan Ledger Terupdate

- Jalur posting existing (`record_inflow`/`consume_stock`) sudah menulis ke `StockMovement` — itu ledger sesungguhnya dan sudah terpasang. Tugas fase ini: menambah **bukti terukur**.
- Setelah posting, list adjustment/opname, `get_available_stock`, dan stock card mencerminkan saldo baru.
- Test regresi (lihat §G) menegaskan preview == angka jurnal & mutasi yang benar-benar tersimpan setelah posting.

---

## G. Testing

File: [apps/inventory/tests_fase6.py](../../../apps/inventory/tests_fase6.py) (atau modul test baru `tests_autocost_preview.py`).

1. **`current_unit_cost` per metode:** dengan ≥2 layer harga berbeda — FIFO ambil tertua, LIFO terbaru, average = rata-rata tertimbang; `None` saat tanpa stok.
2. **Endpoint `stock_available`:** mengembalikan `unit_cost` benar sesuai metode + `available`; `null` saat belum ada layer.
3. **Resolusi `eb_hierarki`:** `lv2:`/`lv3:` menghasilkan FK lv1/lv2/lv3 yang benar; validasi gudang lintas-lv1 ditolak.
4. **Tanggal default:** GET form → field tanggal berisi `timezone.localdate()`.
5. **Preview == Posting:** untuk skenario naik, turun (FIFO & LIFO), dan campuran — `adjustment_preview`/`opname_preview` menghasilkan baris jurnal & mutasi yang **identik** dengan hasil `process_*` yang benar-benar diposting; dan preview **tidak** menyisakan `StockMovement`/`JurnalHeader` (rollback bersih).
6. **Ledger terupdate:** setelah posting, `get_available_stock(item, scope)` berubah tepat sebesar delta; `StockMovement` ada dengan `remaining_qty` benar; opname selisih 0 tidak membuat movement.
7. **Regresi:** purchase/sales/transfer/retur existing tetap hijau; pemindahan `_get_eb_dropdown_options` tidak memutus purchase.

---

## H. Urutan Implementasi (ringkas — detail di plan)

1. `current_unit_cost` di ledger + test.
2. Perluas `stock_available` (tambah `unit_cost`) + test.
3. Pindahkan/-share `_get_eb_dropdown_options`; tambah field `eb_hierarki` + resolusi `clean()` di `StockAdjustmentForm` & `StockOpnameForm`; tanggal default di view.
4. Update template kedua form: dropdown hierarkis, auto-fill harga + badge no-stock, warehouse scope JS mengikuti lv1 hasil resolusi.
5. Endpoint `adjustment_preview`/`opname_preview` (savepoint + rollback) + payload JSON.
6. Modal preview (jurnal + mutasi) + tombol di kedua form.
7. Test end-to-end preview==posting & ledger terupdate; jalankan regresi.
