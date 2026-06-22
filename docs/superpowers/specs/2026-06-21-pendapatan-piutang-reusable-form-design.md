# Desain: Form Piutang Reusable & Integrasi Pendapatan → Piutang (Kredit)

**Tanggal:** 2026-06-21
**Status:** Disetujui (desain) — siap masuk tahap perencanaan implementasi
**Modul terdampak:** `apps/pendapatan`, `apps/piutang`

## 1. Latar Belakang & Masalah

Pada modul **purchase**, form pembelian otomatis terhubung ke **Item Master**: memilih item akan menarik `unit_price` (modal), `coa_account`, kategori, dan metode biaya langsung dari Item Master melalui endpoint `api_item_autocomplete`. Item Master adalah *sumber tunggal* — form purchase hanya mengonsumsinya, tidak mengetik ulang.

Alur **pendapatan → piutang** untuk transaksi **kredit** belum bekerja seperti itu:

- Form pendapatan (`PendapatanHeaderForm`) untuk kredit hanya menangkap `payment_type=credit` + item KP. Tidak ada satu pun field piutang.
- Saat confirm, `create_piutang_from_pendapatan()` (`apps/piutang/services.py:325`) membuat piutang **tipis** — hanya `tanggal, debitur (= nama EB), deskripsi, jumlah_pokok, coa_piutang_account`.
- Semua field kaya yang sudah dibangun di "form tambah piutang" (`PiutangHeaderForm`) — `jatuh_tempo, jenis_bunga, suku_bunga, periode_angsuran, pv_discount_rate, kategori_pengukuran (PSAK), business_model, sppi_test_passed, biaya_transaksi, agunan_*`, dll. — **hilang**: tidak pernah ditangkap untuk pendapatan kredit.

**Tujuan:** menjadikan "form tambah piutang" sebagai **single source of truth** yang dipakai ulang oleh pendapatan (dan modul lain di masa depan), sehingga semua field piutang tertangkap di sumbernya dan terbawa utuh — persis seperti purchase yang menarik dari Item Master.

## 2. Keputusan Desain (hasil brainstorming)

1. **Pola integrasi:** field piutang muncul sebagai **modal inline** di form pendapatan, dibuka saat Tipe Pembayaran = Kredit (meniru pola modal purchase).
2. **Auto-isi vs manual:** auto-isi `debitur`, baris detail (jumlah/deskripsi/akun pendapatan) dari item KP. **Akun piutang (`coa_piutang_account`) dipilih di dalam modal** (bukan diturunkan dari `payment_account` pendapatan). Sisa syarat kredit diisi manual.
3. **Cakupan sekarang:** bangun komponen reusable + satu service entry-point; **wire pendapatan saja**. Sales & modul lain bisa mengadopsi nanti tanpa menulis ulang.
4. **Pendekatan persistensi:** **Pendekatan A** — data modal di-*stage* pada pendapatan saat create; piutang lengkap dibangun saat **confirm**. Tidak mengubah lifecycle draft→confirm pendapatan dan tidak meninggalkan piutang yatim.

## 3. Arsitektur — Komponen Bersama (3 Lapisan)

Tidak ada duplikasi. Form, partial, JS, dan service semuanya kanonik tunggal.

### 3.1 Lapisan Form (Python)
- `PiutangHeaderForm` + `PiutangDetailFormSet` tetap satu-satunya definisi field.
- Saat dipakai di pendapatan, di-instansiasi dengan `prefix='piutang'` agar nama field tidak bentrok dengan form pendapatan dalam satu halaman.

### 3.2 Lapisan Template (partial)
- Badan wizard diekstrak dari `templates/piutang/form.html` ke partial baru `templates/piutang/_form_body.html`.
- Halaman piutang asli meng-`include` partial ini (perilaku tidak berubah).
- Modal pendapatan meng-`include` partial yang sama dengan flag `embedded=True` yang:
  - menyembunyikan Kartu 7 "Detail Baris Piutang" (baris ditarik dari item KP),
  - menyembunyikan dropdown Entitas Bisnis (sudah dipilih di pendapatan).

### 3.3 Lapisan JS (init reusable)
- Script wizard inline (klasifikasi PSAK, EIR, toggle kartu, TomSelect) dipindah ke `static/js/piutang_form.js` sebagai fungsi `initPiutangForm(rootEl, options)` yang ter-scope ke elemen root.
- Halaman piutang memanggilnya pada `document`; modal pendapatan memanggilnya pada elemen modal. Menghilangkan bentrok ID dan menyatukan logika.

### 3.4 Propagasi perubahan masa depan
- **Otomatis ikut** (tanpa menyentuh pendapatan): tambah/ubah/hapus field di `PiutangHeaderForm`; ubah widget/label/validasi/queryset; ubah tampilan kartu di `_form_body.html`; ubah logika wizard JS; ubah logika `build_piutang()`.
- **Perlu sentuhan kecil terlokalisir**: hanya ketika field baru perlu **diisi otomatis** dari data pendapatan → tambah satu baris pemetaan di adapter `pendapatan_to_piutang_payload()` (lihat §4.3). Field yang diisi manual oleh user muncul otomatis tanpa kerja tambahan.

## 4. Model Data, Service, & Adapter

### 4.1 Model staging baru — `PendapatanPiutangProfil`
Di `apps/pendapatan/models.py`. One-to-one ke `PendapatanHeader`. Menyimpan input modal saat create untuk dipakai saat confirm. Field mirror credit-terms `PiutangHeader` (hanya yang relevan untuk form *tambah*):

```
pendapatan_header    OneToOneField(PendapatanHeader, related_name='piutang_profil', on_delete=CASCADE)
debitur              CharField              # auto dari EB, bisa override
coa_piutang_account  FK Akun                # DIPILIH di modal
jatuh_tempo          DateField null
jenis_jangka_waktu   CharField
jenis_bunga          CharField
suku_bunga           DecimalField
periode_angsuran     CharField
pv_discount_rate     DecimalField null
interest_income_account     FK Akun null
coa_piutang_lancar_account  FK Akun null
standar_akuntansi    CharField
kategori_pengukuran  CharField
business_model       CharField
sppi_test_passed     BooleanField null
biaya_transaksi      DecimalField null
biaya_transaksi_account     FK Akun null
agunan_jenis         CharField
agunan_nilai         DecimalField null
is_approval_required BooleanField
```

- Daftar field didefinisikan sekali sebagai konstanta `PIUTANG_PROFIL_FIELDS`, dipakai bersama model + adapter (satu tempat untuk ditambah bila form piutang menambah field).
- Migrasi bersifat **aditif** (hanya menambah tabel baru), tidak mengubah tabel lama.

### 4.2 Service kanonik — `build_piutang(payload, *, source, source_obj, details, user)`
Di `apps/piutang/services.py`. Satu-satunya jalan membuat `PiutangHeader`, menggantikan logika tumpang-tindih di `create_manual_piutang`, `create_piutang_from_pendapatan`, `create_piutang_from_sales`.
- `payload` = dict field header piutang (dari form manual atau profil pendapatan).
- `details` = list baris (dari formset manual atau diturunkan dari item KP).
- `source` ∈ `{'manual','pendapatan','sales'}`; `source_obj` = header sumber.
- **Tidak** mem-posting jurnal AR saat create (konsisten dengan perilaku manual sekarang; jurnal AR pendapatan kredit dibukukan oleh confirm pendapatan).
- `create_manual_piutang` & `create_piutang_from_pendapatan` menjadi pembungkus tipis di atas `build_piutang` (atau dihapus bila aman) agar pemanggil lama tidak pecah.

### 4.3 Adapter tunggal — `pendapatan_to_piutang_payload(header)`
Di `apps/pendapatan/services.py`. "Satu tempat pemetaan" auto-prefill. Mengubah `PendapatanHeader` + `PendapatanPiutangProfil`-nya menjadi `(payload, details)`:
- `payload` ← disalin dari `PendapatanPiutangProfil` (semua credit-terms + `coa_piutang_account`).
- `details` ← diturunkan dari item KP: `deskripsi_item → deskripsi`, `nilai_kontrak → jumlah`, `revenue_account → revenue_account`.
- `entitas_bisnis` ← dari `PendapatanEntitasBisnis`.

Bila ada field auto-prefill baru di masa depan, **hanya fungsi ini** yang disentuh.

## 5. Alur UX Modal & Koreksi Akuntansi

### 5.1 Alur form pendapatan (create/edit)
1. User isi pendapatan, set **Tipe Pembayaran = Kredit**.
2. Muncul tombol **"Atur Detail Piutang"** + badge status ("Belum diatur / Sudah diatur"). Submit diblokir bila kredit tapi profil belum diatur.
3. Klik tombol → **modal** berisi partial `_form_body.html` (mode `embedded`):
   - **Auto-terisi**: `debitur` (dari EB) dan baris detail (deskripsi/jumlah/akun pendapatan) **read-only** dari item KP, via JS.
   - **Diisi user**: `coa_piutang_account`, jatuh tempo, jenis bunga/suku bunga, klasifikasi PSAK, PV/EIR, biaya transaksi, agunan.
4. Klik **"Simpan Detail Piutang"** → tidak submit ke server; JS menyalin field modal (ber-prefix `piutang-`) ke **hidden inputs** di `<form>` pendapatan utama, lalu tutup modal.
5. Submit form pendapatan → view memvalidasi `piutang-*` lewat `PiutangHeaderForm(prefix='piutang')`; bila valid simpan/update `PendapatanPiutangProfil`. Bila tidak valid, modal dibuka lagi dengan error.
6. Saat **confirm** → adapter + `build_piutang()` membuat piutang lengkap.

Validasi dua lapis: ringan di JS (UX), otoritatif di server lewat `PiutangHeaderForm` (sumber kebenaran). Tidak ada duplikasi aturan validasi.

### 5.2 Koreksi akuntansi (penting)
Saat ini `confirm_pendapatan` membukukan KP kredit point-in-time sebagai **Dr `payment_account` / Cr revenue**, padahal `payment_account` adalah kas/bank. Untuk **kredit**, debit seharusnya **akun Piutang**:
- KP **kredit** point-in-time: `debit_acct = profil.coa_piutang_account` (dari modal), bukan `payment_account`.
- Field "Akun Kas/Bank" (`payment_account`) di baris KP menjadi **opsional/disembunyikan saat Kredit** (tetap wajib saat Cash).
- Jurnal AR (Dr Piutang / Cr Pendapatan) dibukukan oleh confirm pendapatan, lalu **ditautkan** ke `PiutangHeader` yang dibuat (jejak audit). `build_piutang` dari pendapatan **tidak** membuat jurnal AR kedua → mencegah pendapatan dobel.

## 6. Edge Case & Aturan
- **Kredit tanpa profil**: submit diblokir di server (bukan hanya JS); pesan error jelas.
- **Ganti Cash ↔ Kredit**: pindah ke Cash → profil yang ada dihapus/diabaikan; pindah ke Kredit → wajib isi modal.
- **Edit pendapatan draft**: modal dibuka kembali ter-prefill dari `PendapatanPiutangProfil`; baris detail mengikuti item KP terbaru.
- **Item KP berubah setelah profil diatur**: baris detail selalu diturunkan dari KP saat confirm (tidak disnapshot di profil) → otomatis sinkron. Hanya credit-terms yang dari profil.
- **Multi Entitas Bisnis dalam satu pendapatan**: ikut perilaku sekarang — satu piutang per header (debitur dari EB pertama). Di luar cakupan.
- **Confirm jalur cash**: tidak tersentuh.
- **Void/batal pendapatan**: logika existing pembatalan piutang tertaut tetap berlaku.

## 7. Kompatibilitas Data Lama
- Pendapatan kredit yang sudah dikonfirmasi sebelum perubahan ini **tidak disentuh** (piutang tipisnya tetap ada).
- Pemanggilan `create_piutang_from_pendapatan` lama dialihkan ke jalur baru; bila masih ada pemanggil lain, dipertahankan sebagai wrapper tipis.
- Migrasi aditif → aman.

## 8. Testing
- **Unit:** `build_piutang()` (manual & pendapatan menghasilkan piutang identik untuk input setara); `pendapatan_to_piutang_payload()` memetakan KP → details dengan benar.
- **Integrasi:** create→confirm pendapatan kredit menghasilkan `PiutangHeader` lengkap (semua credit-terms terbawa) + jurnal Dr Piutang/Cr Pendapatan dengan akun dari modal; jalur cash tak berubah; blokir submit bila profil kosong.
- **Regresi:** halaman tambah piutang manual tetap berfungsi setelah ekstraksi partial + `piutang_form.js` (submit, wizard, formset detail).
- **Runner:** `python manage.py test apps.pendapatan apps.piutang`.

## 9. Di Luar Cakupan (YAGNI)
- Wiring modul Sales (disiapkan lewat `build_piutang` tapi tidak di-wire sekarang).
- Pemecahan piutang per-Entitas Bisnis.
- Field tahap-lanjut piutang (ECL, write-off, factoring) di dalam modal.
