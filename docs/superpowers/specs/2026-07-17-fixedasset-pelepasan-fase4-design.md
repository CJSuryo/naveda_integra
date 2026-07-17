# Desain — Pelepasan Aset Tetap (Fase 4)

**Tanggal:** 2026-07-17
**Status:** Disetujui (siap plan)
**Ruang lingkup:** Modul `apps/aset_tetap` — model `AssetDisposal`, engine jurnal pelepasan, reversal, view/form/UI, dan interaksi dengan penyusutan. Melanjutkan Fase 4 dari roadmap `2026-07-15-inventory-fixedassets-review-and-roadmap.md`.
**Beririsan minimal dengan Fase 1–3** (stok/costing) — dapat dikerjakan mandiri.

---

## A. Latar & Masalah

Modul Aset Tetap kuat di penyusutan (5 metode) tetapi kosong di siklus hidup pelepasan. Saat aset dijual/dihibahkan/rusak/dimusnahkan, saat ini tidak ada:
- pencatatan peristiwa pelepasan (audit trail),
- jurnal otomatis yang menormalkan nilai buku dan mengakui laba/rugi pelepasan,
- penonaktifan aset dari daftar penyusutan.

Tujuan Fase 4: satu peristiwa `AssetDisposal` yang memicu jurnal pelepasan yang benar, mendukung pelepasan sebagian (partial quantity), dan dapat dibatalkan (reversible) kapan saja.

Referensi kode kunci:
- Record aset: `apps/aset_tetap/models.py:6` (`AsetTetapRecord`), properti `nilai_buku` di `:146`.
- Engine penyusutan & jurnal: `apps/aset_tetap/services.py` (`process_depreciation` `:138`, penomoran `:119`).
- Pola hapus/reversal jurnal: `apps/aset_tetap/views.py:484` (`delete_depreciation_journal`, memakai `log_jurnal_terhapus`).
- Akun aset saat perolehan: `PurchaseItem.coa_account` (didebit di `apps/purchase/services.py:49`); default per item: `ItemMasterPurchase.coa_account` (`apps/purchase/models.py:106`).

---

## B. Keputusan Desain

1. **Empat jenis pelepasan** dalam satu model: `jual`, `hibah`, `rusak`, `musnah`. `jual` punya proceeds (harga jual + kas); tiga lainnya tanpa proceeds → seluruh nilai buku menjadi rugi pelepasan.
2. **Pelepasan sebagian didukung.** `quantity` yang dilepas boleh ≤ sisa quantity aset. Perolehan, akumulasi, dan residu yang dilepas dihitung **pro-rata** terhadap quantity.
3. **Reversible kapan saja.** Setiap `AssetDisposal` yang belum di-reversal dapat dibatalkan tanpa syarat "harus yang terakhir". Reversal memulihkan state aset dari **snapshot** yang tersimpan di record disposal.
4. **Resolusi COA (pola startswith/lookup, konsisten fase penyusutan):**
   - **Akun Aset** = `aset.purchase_item.coa_account` → fallback `aset.item.coa_account`. Bila keduanya kosong → `ValueError` eksplisit.
   - **Akun Akumulasi Penyusutan** = `Akun.objects.filter(kode_akun__startswith='1.2.7').first()` (sama seperti penyusutan). Kosong → `ValueError`.
   - **Akun Kas/Piutang** = dipilih user di form (`akun_kas`). Wajib hanya bila `jual` dan `harga_jual > 0`.
   - **Akun Laba/Rugi Pelepasan** = dipilih user di form (`akun_laba_rugi`). Wajib. (Tidak ada kode baku di sistem; user membuat akunnya via UI dan memilihnya.) Mapping per-kategori diserahkan ke Fase 5.
5. **Snapshot disimpan di disposal** (bukan dihitung ulang saat reversal) agar reversal presisi meski penyusutan berjalan setelahnya.

---

## C. Model

### C.1 `AssetDisposal` (baru, `apps/aset_tetap/models.py`)

| Field | Tipe | Catatan |
|---|---|---|
| `disposal_number` | `CharField(max_length=50, unique=True, editable=False)` | auto `DSP-<eb/urut>` (§C.3) |
| `aset` | `FK(AsetTetapRecord, PROTECT, related_name='disposals')` | |
| `tanggal` | `DateField(default=timezone.now, db_index=True)` | |
| `jenis` | `CharField(choices=JENIS_CHOICES)` | `jual`/`hibah`/`rusak`/`musnah` |
| `quantity` | `DecimalField(max_digits=15, decimal_places=4)` | qty dilepas, > 0 dan ≤ sisa qty aset |
| `harga_jual` | `DecimalField(max_digits=19, decimal_places=4, default=0)` | hanya relevan `jual` |
| `akun_kas` | `FK(master_data.Akun, PROTECT, null=True, blank=True, related_name='disposal_kas')` | wajib bila `jual` & `harga_jual>0` |
| `akun_laba_rugi` | `FK(master_data.Akun, PROTECT, related_name='disposal_laba_rugi')` | wajib |
| `perolehan_dilepas` | `DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)` | snapshot = `quantity × aset.harga_perolehan` |
| `akumulasi_dilepas` | `DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)` | snapshot pro-rata (§D.1) |
| `residu_dilepas` | `DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)` | snapshot pro-rata |
| `laba_rugi` | `DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)` | snapshot = `harga_jual − nilai_buku_dilepas` (+laba / −rugi) |
| `jurnal_header` | `FK(jurnal.JurnalHeader, SET_NULL, null=True, blank=True, related_name='+')` | link untuk reversal |
| `keterangan` | `TextField(blank=True)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`JENIS_CHOICES = [('jual','Jual'), ('hibah','Hibah'), ('rusak','Rusak'), ('musnah','Musnah')]`

Meta: `ordering = ['-tanggal', '-created_at']`; index pada `aset`, `tanggal`.

### C.2 Perubahan `AsetTetapRecord`

Tambah:
```python
STATUS_CHOICES = [('aktif', 'Aktif'), ('dilepas', 'Dilepas')]
status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='aktif', db_index=True)
```
Migrasi aman: default `'aktif'` untuk seluruh baris lama. Field ini turunan dari quantity (dilepas bila quantity habis) tetapi disimpan eksplisit agar filter daftar & blokir penyusutan sederhana dan cepat.

### C.3 Penomoran

Helper `_next_disposal_number()` di `services.py`, pola sama dengan `_next_depreciation_journal_number` tetapi prefix `DSP-` (record) dan jurnal `TRX-DSP-`. Penomoran record disposal: `DSP-<seq:03d>` global sekuensial (cukup untuk kebutuhan sekarang).

---

## D. Engine Jurnal — `process_asset_disposal(disposal)`

Di `apps/aset_tetap/services.py`. Dipanggil setelah `AssetDisposal` (belum tersimpan / tersimpan tanpa jurnal) siap. Mengembalikan `JurnalHeader`.

### D.1 Hitung snapshot (dari state aset saat ini)
```
qty_sebelum   = aset.quantity
fraksi        = quantity / qty_sebelum            # 0 < fraksi ≤ 1
perolehan_dilepas = quantity * aset.harga_perolehan
akumulasi_dilepas = aset.akumulasi_penyusutan * fraksi
residu_dilepas    = aset.nilai_residu * fraksi
nilai_buku_dilepas = perolehan_dilepas - akumulasi_dilepas
laba_rugi          = harga_jual - nilai_buku_dilepas   # jual: harga_jual>0; lainnya: 0
```
Kuantisasi seluruh nilai uang ke 4 desimal (konsisten skema `DecimalField`).

### D.2 Validasi (raise `ValueError`)
- `quantity > 0` dan `quantity ≤ aset.quantity`.
- `aset.status == 'aktif'` (aset yang sudah `dilepas`/quantity 0 tak bisa dilepas lagi).
- `jenis == 'jual'` → `akun_kas` wajib bila `harga_jual > 0`; `harga_jual ≥ 0`.
- `jenis != 'jual'` → `harga_jual` dipaksa `0` (abaikan input), `akun_kas` diabaikan.
- `akun_laba_rugi` wajib.
- Akun Aset resolvable (§B.4) → else `ValueError`.
- Akun Akumulasi (`1.2.7`) ada → else `ValueError`.

### D.3 Baris jurnal
| Sisi | Akun | Nilai |
|---|---|---|
| Kredit | Aset | `perolehan_dilepas` |
| Debit | Akumulasi Penyusutan | `akumulasi_dilepas` |
| Debit | Kas/Piutang (`akun_kas`) | `harga_jual` — **hanya** `jual` & `harga_jual>0` |
| Kredit | `akun_laba_rugi` | `laba_rugi` bila `laba_rugi > 0` |
| Debit | `akun_laba_rugi` | `-laba_rugi` bila `laba_rugi < 0` |

`laba_rugi == 0` → tanpa baris laba/rugi. Verifikasi `Σdebit == Σkredit` (assert; bila tidak balance → `ValueError`, indikasi bug).

Hibah/rusak/musnah: `harga_jual=0` → tanpa baris kas; `laba_rugi = -nilai_buku_dilepas` → seluruh nilai buku menjadi **rugi** (debit `akun_laba_rugi`).

### D.4 Efek ke aset & persistensi (atomic)
```python
with transaction.atomic():
    # simpan snapshot ke disposal
    disposal.perolehan_dilepas = ...
    disposal.akumulasi_dilepas = ...
    disposal.residu_dilepas    = ...
    disposal.laba_rugi         = ...

    # kurangi aset (pro-rata)
    aset.quantity            -= quantity
    aset.akumulasi_penyusutan -= akumulasi_dilepas
    aset.nilai_residu        -= residu_dilepas
    if aset.quantity <= 0:
        aset.status = 'dilepas'
    aset.save()   # save() recompute total_value = quantity * harga_perolehan

    header = JurnalHeader.objects.create(
        tanggal=disposal.tanggal,
        nomor_transaksi=_next_disposal_journal_number(),   # TRX-DSP-xxx
        uraian_transaksi=f'Pelepasan {aset.aset_number} ({jenis}) — {aset.item.nama}',
        entitas_bisnis=aset.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([...])
    disposal.jurnal_header = header
    disposal.save()
return header
```

**Catatan integritas penyusutan:** mengurangi `quantity` menyusutkan `total_value` (basis penyusutan) untuk unit yang tersisa — perilaku yang benar (unit terlepas tak lagi disusutkan). Jurnal penyusutan lama yang sudah diposting tetap historis. `akumulasi_penyusutan` sisa berkurang proporsional sehingga nilai buku unit tersisa tetap benar.

---

## E. Reversal — `reverse_asset_disposal(disposal, request)`

Mirror `delete_depreciation_journal` (`views.py:484`), tanpa syarat "harus terbaru".

Atomic:
1. `log_jurnal_terhapus(disposal.jurnal_header, 'aset_tetap', request)` (bila jurnal ada).
2. Hapus `jurnal_header.details` + `jurnal_header`.
3. Pulihkan aset dari snapshot: `quantity += disposal.quantity`, `akumulasi_penyusutan += akumulasi_dilepas`, `nilai_residu += residu_dilepas`, `status='aktif'` (karena quantity kini > 0). `save()` recompute `total_value`.
4. Hapus record `AssetDisposal`.

Karena tiap disposal hanya menambah/mengurangi berdasarkan snapshot-nya sendiri, reversal salah satu dari beberapa disposal tetap konsisten (bukan bergantung urutan).

---

## F. Penyusutan × Pelepasan

- `process_depreciation` menolak aset `status='dilepas'` (`ValueError` eksplisit) — tambahkan guard.
- `aset_tetap_bulk_depreciation` (`views.py:313`) melewati (`skip`) record `status='dilepas'`.
- Aset **sebagian** dilepas tetap `aktif` dan tersusutkan otomatis atas basis `total_value` baru — tak perlu perubahan khusus.

---

## G. View / URL / Form / Template

### G.1 Views (`apps/aset_tetap/views.py`)
- `aset_tetap_dispose(request, pk)` — POST dari halaman detail; bangun `AssetDisposal` dari form, panggil `process_asset_disposal`, `messages.success/error`, redirect ke detail.
- `aset_tetap_disposal_delete(request, pk, disposal_pk)` — GET konfirmasi (`delete_disposal_confirm.html`), POST panggil `reverse_asset_disposal`.

### G.2 URL (`urls.py`)
```python
path('<int:pk>/lepas/', views.aset_tetap_dispose, name='dispose'),
path('<int:pk>/pelepasan/<int:disposal_pk>/batal/', views.aset_tetap_disposal_delete, name='disposal_delete'),
```

### G.3 Form (`forms.py`)
`AssetDisposalForm(ModelForm)` — fields: `jenis`, `tanggal`, `quantity`, `harga_jual`, `akun_kas`, `akun_laba_rugi`, `keterangan`. `clean()`:
- `quantity` > 0 dan ≤ sisa qty aset (aset di-`__init__`).
- `jual` & `harga_jual>0` → `akun_kas` wajib.
- non-`jual` → normalkan `harga_jual=0`.
- `akun_laba_rugi` wajib.
Queryset `akun_kas`/`akun_laba_rugi` = `Akun.objects.all()` (akun global; UI menampilkan kode+nama).

### G.4 Template detail (`templates/aset_tetap/detail.html`)
- Tombol **"Lepas Aset"** (buka modal/section form) — disembunyikan bila `record.status == 'dilepas'` / `quantity <= 0`.
- Section **Riwayat Pelepasan**: tabel disposal (nomor, tanggal, jenis, qty, harga jual, laba/rugi, jurnal) + aksi **Batalkan** per baris.
- Badge status aset (Aktif/Dilepas).

### G.5 Daftar (`aset_tetap_list`)
Tampilkan kolom/badge status; opsi filter status. (Tidak wajib mengubah export kecuali menambah kolom status — opsional.)

---

## H. Test (Acceptance) — `apps/aset_tetap/tests.py`

**Skenario jurnal (jual):**
- **Laba:** harga jual > nilai buku → nilai buku unit dilepas ter-nol, laba di **kredit** `akun_laba_rugi`, jurnal balance.
- **Rugi:** harga jual < nilai buku → selisih di **debit** `akun_laba_rugi`.
- **Impas:** harga jual = nilai buku → tanpa baris laba/rugi.

**Non-jual:** hibah/rusak/musnah → tanpa baris kas, seluruh nilai buku menjadi **rugi** (debit), jurnal balance.

**Partial:** lepas qty 3 dari 10 → `perolehan/akumulasi/residu_dilepas` pro-rata; aset sisa `quantity=7`, `total_value`/akumulasi/nilai_buku benar; penyusutan berikutnya memakai basis baru.

**Full disposal:** qty penuh → `status='dilepas'`; `process_depreciation` diblok; `bulk_depreciation` skip.

**Reversal (kapan saja):** buat 2 disposal berbeda pada satu aset, reversal yang **pertama** → state aset pulih presis (quantity, akumulasi, residu, status), jurnal terhapus & tercatat di `log_jurnal_terhapus`, record disposal terhapus.

**Validasi:** qty > sisa → error; qty ≤ 0 → error; aset sudah `dilepas` → error; akun aset tak resolvable (purchase_item & item.coa_account null) → `ValueError`; akun akumulasi `1.2.7` tak ada → `ValueError`; `jual` tanpa `akun_kas` saat harga_jual>0 → error form.

**Balance:** untuk seluruh skenario, `Σdebit == Σkredit`.

---

## I. Migrasi

Satu migrasi: `AssetDisposal` (model baru) + `AsetTetapRecord.status` (default `'aktif'`). Backward-safe; tidak menyentuh data penyusutan/perolehan yang ada. Tidak ada backfill diperlukan (semua aset lama `aktif`).

---

## J. Risiko & Mitigasi

- **Pembulatan pro-rata** (partial) meninggalkan selisih kecil antara `Σ dilepas` dan nilai aset saat unit terakhir dilepas → kuantisasi konsisten 4 desimal; saat `quantity` habis, `status='dilepas'` dan sisa akumulasi/residu record mendekati 0 (residu error di bawah 1 rupiah dapat diabaikan; opsional: paksa nol saat full disposal).
- **Reversal setelah penyusutan berjalan** → snapshot menjamin pemulihan porsi yang tepat; penyusutan pasca-pelepasan tetap valid sebagai transaksi terpisah.
- **Akun laba/rugi salah pilih user** → mitigasi via label kode+nama di dropdown; bukan resolusi otomatis sehingga tanggung jawab pemilihan ada pada akuntan (sesuai keputusan §B.4).
- **Ketergantungan Fase 5** → saat mapping per-kategori hadir, resolusi `akun_laba_rugi`/akumulasi dapat dialihkan ke engine mapping tanpa mengubah struktur `AssetDisposal`.
