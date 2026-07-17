# Desain — Perbaikan UI/UX Fase 1 (UOM) & Fase 2 (Stock Ledger + Gudang)

**Tanggal:** 2026-07-17
**Status:** Design — menunggu review user sebelum plan implementasi
**Ruang lingkup:** Hanya lapisan presentasi (templates + context ringan di views inventory & uom). Tidak mengubah model, migrasi, engine costing, atau logika stok. Bukan git repo — tidak ada commit.
**Konteks:** Lanjutan dari `2026-07-15-inventory-fixedassets-review-and-roadmap.md`. Fase 1 & 2 sudah diimplementasi; layar-layarnya sudah masuk navigasi tetapi belum konsisten dengan design system aplikasi.

---

## A. Masalah yang diselesaikan

1. **Inkonsistensi design system.** Empat layar Fase 2 (`warehouse_list`, `warehouse_form`, `stock_ledger`, `stock_card`) memakai kelas tipis (`ni-page`, `ni-page__title`, `ni-filter`, `ni-input`, tombol `ni-link`), sedangkan Fase 1 (UOM) dan sisa aplikasi memakai pola kaya (`ni-page-header` judul+subtitle+actions, `ni-card`/`ni-card__body`, varian `ni-btn`, ikon lucide, `ni-animate-fade-in`, `ni-table-wrapper`, empty-state ber-style, badge). Akibatnya layar Fase 2 terlihat setengah jadi.

2. **Satuan (UOM) tidak muncul di angka stok.** Fase 1 membangun UOM tapi ledger/kartu stok menampilkan qty telanjang. Setiap qty seharusnya terbaca dengan `item.stock_uom.kode` (mis. "120 pcs").

3. **Filter Entitas Bisnis absen di laporan stok.** Isolasi EB adalah alasan utama Fase 2, tapi `stock_ledger` hanya filter item/gudang/tanggal dan `stock_card` tidak punya filter EB sama sekali.

4. **Valuasi persediaan tidak terlihat di Kartu Stok.** Belum ada Total Nilai Persediaan (Σ `remaining_qty × unit_cost`).

5. **Penghalusan kecil UI Fase 1 (UOM)** masih menyisakan gesekan: checkbox ter-render seperti input teks, tak ada preview konversi, ikon dimensi pakai emoji.

## B. Prinsip desain

- **Meniru pola matang yang sudah ada**, bukan menciptakan visual baru. Rujukan gold-standard: `templates/inventory/inventory_list.html` (page header, filter card, tabel, badge, empty state) dan `templates/uom/item_conversion_form.html` (pola form).
- **Perubahan view minimal & aditif**: hanya menambah key context yang dibutuhkan (mis. daftar EB tree, agregat valuasi). Tidak mengubah queryset inti atau perhitungan saldo.
- **Tanpa dependensi baru**: pakai `intcomma`/`humanize`, ikon lucide, komponen `components/eb_filter_modal.html` yang sudah ada.
- **Aksesibilitas & konsistensi angka**: kolom numerik `ni-text-right` + `intcomma`; status/jenis sebagai badge; empty state konsisten.

---

## C. Perubahan per layar

### C1. Buku Persediaan — `stock_ledger.html` + `stock_ledger` view
**Template**
- Header `ni-page-header` (judul "Buku Persediaan" + subtitle "Pergerakan stok append-only dengan saldo berjalan").
- Filter dibungkus `ni-card`/`ni-card__body`, layout flex seperti `inventory_list` (item, gudang, tanggal dari/sampai) + **filter EB** via `components/eb_filter_modal.html` + tombol Filter & Reset.
- Tabel dibungkus `ni-card` + `ni-table-wrapper`.
- Kolom Jenis Pergerakan → badge (`ni-badge`), warna per arah: masuk (`qty > 0`) hijau, keluar (`qty < 0`) merah.
- Qty tampil dengan tanda + satuan `stock_uom.kode` (mis. "−12 pcs"), `ni-text-right`. Biaya/Unit & Saldo `intcomma`, `ni-text-right`.
- **Guard saldo**: banner hint kecil bila filter belum menyaring ke tepat 1 item + 1 gudang — teks: "Kolom Saldo hanya bermakna bila difilter ke satu item dan satu gudang." Ditentukan dari context boolean `saldo_valid = bool(item_filter) and bool(wh_filter)`.
- Empty state ber-style (`ni-text-center ni-text-muted`).

**View (`stock_ledger`)** — tambahan aditif:
- Tambah filter `entitas_bisnis` (multi) mengikuti pola `inventory_list`: `eb_filter_list = getlist('entitas_bisnis')`; bila ada → `qs.filter(entitas_bisnis_id__in=_resolve_eb_lv1_ids(eb_filter_list, request.user))`.
- Context tambahan: `eb_tree=_get_eb_tree(request.user)`, `eb_filter_list`, `saldo_valid`.
- Import `_get_eb_tree`, `_resolve_eb_lv1_ids` dari `apps.purchase.views` (sudah dipakai di file yang sama).
- `select_related` sudah mencakup `item`; tambahkan `item__stock_uom` agar `stock_uom.kode` tak memicu query N+1.

*Di luar scope sekarang:* baris total & tombol Export (opsi "visual + guard" dipilih, bukan "+ Export + total").

### C2. Kartu Stok — `stock_card.html` + `stock_card` view
**Template**
- Header `ni-page-header` (judul + subtitle "Saldo, valuasi, dan layer FIFO aktif per item").
- Filter item dibungkus `ni-card`; tambah **filter EB** (opsional bila item dipilih; ikut pola yang sama).
- Setelah item dipilih, tampilkan **stat tiles** (baris ringkas 2–3 kartu): Total Stok On-Hand (Σ qty, dengan `stock_uom.kode`) & **Total Nilai Persediaan** (Σ `remaining_qty × unit_cost`, `intcomma`). Meniru gaya metric card yang sudah dipakai di `laporan_persediaan`.
- Tabel "Saldo per Gudang": qty + satuan, `ni-text-right`; bungkus `ni-card`/`ni-table-wrapper`.
- Tabel "Layer Inflow Aktif (FIFO)": tambah kolom Nilai Layer (`remaining_qty × unit_cost`, `intcomma`); qty + satuan; angka `ni-text-right`.
- Tautan "Lihat di Buku Persediaan" pre-filter item terpilih (`?item=<pk>`).
- Empty/placeholder state ber-style saat item belum dipilih.

**View (`stock_card`)** — tambahan aditif:
- Filter EB opsional (sama seperti C1) untuk `layers` & `saldo_per_wh`.
- Hitung `total_on_hand = Σ qty` dan `total_value = Σ (remaining_qty × unit_cost)` untuk item terpilih (agregasi Python atas `layers`/movement, atau `aggregate`).
- `select_related('item__stock_uom', ...)`; context tambahan `total_on_hand`, `total_value`, `stock_uom`, `eb_tree`, `eb_filter_list`.

### C3. Master Gudang — `warehouse_list.html`
- Ganti `ni-page` → `ni-page-header` dengan subtitle "Lokasi fisik penyimpanan stok per Entitas Bisnis" + action "Gudang Baru" (tombol `ni-btn ni-btn--success` + ikon `plus`).
- Tabel dibungkus `ni-card`/`ni-table-wrapper`.
- Kolom Status → badge (Aktif hijau / Nonaktif abu).
- Kolom Aksi: tombol Edit (`ni-btn ni-btn--warning ni-btn--sm`) + tombol toggle sebagai form submit dengan konfirmasi (`onsubmit="return confirm(...)"`) bergaya tombol, bukan `ni-link`.
- Empty state ber-style.
- *Catatan:* filter EB pada daftar gudang **tidak** ditambahkan (view sengaja list semua; `_resolve_eb_lv1_ids([])` mengembalikan kosong — lihat komentar di view). Di luar scope.

### C4. Form Gudang — `warehouse_form.html`
- Header `ni-page-header` + tombol Kembali (ikon `arrow-left`).
- Bungkus `ni-card`/`ni-card__body`.
- Ganti loop generik `{% for field in form %}` dengan tata letak `ni-form-row`/`ni-form-group` eksplisit (Bisnis, Nama, Alamat, Aktif) + error per field, mengikuti pola `uom/unit_form.html`. Field Kode (disabled saat edit) tetap ditampilkan.
- Tombol Simpan/Batal `ni-btn-row`.

### C5. Master Satuan — `uom/unit_list.html`
- Ganti ikon dimensi dari emoji `{{ g.icon }}` ke ikon lucide (peta dimensi→nama ikon; disediakan lewat context atau filter template kecil). Bila peta ikon menambah kompleksitas berlebih, alternatif minimal: pertahankan emoji tapi seragamkan ukuran — **keputusan: pakai lucide** untuk konsistensi.
- Kolom Base/Sistem/Aktif "Ya/-" → ikon centang/strip (mis. lucide `check`/`minus`) atau badge kecil agar mudah dipindai.

### C6. Form Satuan — `uom/unit_form.html`
- Checkbox `is_base` & `is_active` di-render inline (checkbox + label sejajar), bukan label-di-atas seperti input teks.
- **Preview langsung**: teks "1 {kode} = {factor} {base}" yang ter-update saat mengetik `kode`/`factor_to_base`/memilih `dimension`. Perlu peta `dimension → base unit kode` dikirim ke template sebagai JSON (`base_by_dimension`) + skrip kecil inline.
- Saat `is_base` dicentang → `factor_to_base` dikunci ke `1` dan di-disable (skrip kecil).

### C7. Form Konversi Item — `uom/item_conversion_form.html`
- Tambah preview langsung "1 {uom} = {qty} {stock_uom}" saat mengisi (butuh `stock_uom.kode` per item dikirim sebagai peta JSON, atau di-fetch dari opsi terpilih). Mengurangi salah input arah konversi.

---

## D. Komponen & pola yang dipakai ulang (tanpa bikin baru)

- `components/eb_filter_modal.html` — filter Entitas Bisnis (butuh `eb_tree` di context + `filter_form_id`).
- `_get_eb_tree(user)` & `_resolve_eb_lv1_ids(list, user)` dari `apps/purchase/views.py`.
- Kelas: `ni-page-header(__title/__subtitle/__actions)`, `ni-card(__body)`, `ni-table-wrapper`, `ni-table`, `ni-btn--{success,warning,secondary,primary,danger,sm}`, `ni-badge`, `ni-form-row/group/label/error`, `ni-btn-row`, `ni-text-right`, `ni-text-center`, `ni-text-muted`, `ni-animate-fade-in`.
- `humanize` `intcomma` untuk angka; ikon lucide via `data-lucide`.

## E. Yang TIDAK dilakukan (YAGNI / fase lain)

- Tidak ada perubahan model, field, atau migrasi.
- Tidak ada Export/PDF atau baris total di ledger (bisa menyusul).
- Tidak ada filter EB di daftar gudang (butuh sentinel "semua" pada helper resolusi EB).
- Tidak menyentuh logika costing, saldo, atau backfill.
- Tidak refactor view di luar penambahan context yang disebut.

## F. Strategi verifikasi

- Karena murni presentasi, verifikasi manual: jalankan server dev, buka tiap layar dengan data contoh (item dgn `stock_uom`, ≥1 gudang, movement masuk+keluar lintas EB).
- Cek: satuan tampil di semua qty; filter EB mempersempit ledger/kartu stok; stat valuasi cocok dengan Σ layer; guard saldo muncul saat filter belum spesifik; badge & empty state tampil benar; preview form UOM ter-update.
- Regresi ringan: pastika layar Fase 2 lama masih memuat tanpa error setelah penambahan context (import `_get_eb_tree` dsb.).

## G. Urutan implementasi yang disarankan (untuk plan)

1. Ledger (`stock_ledger` view + template) — perubahan terbesar, menyiapkan pola filter EB.
2. Kartu Stok (`stock_card` view + template) — pakai ulang pola EB + tambah valuasi.
3. Gudang list + form (template saja).
4. UOM: unit_list, unit_form, item_conversion_form (template + context/JSON kecil).

Tiap langkah berdiri sendiri dan bisa diverifikasi terpisah.
