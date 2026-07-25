# Desain — Redesain Halaman Hub Laporan

**Tanggal:** 2026-07-25
**Status:** Disetujui (siap ke penyusunan rencana)
**Ruang lingkup:** UI/template saja. Redesain 3 halaman hub laporan yang sudah ada agar sangat menarik, menyenangkan, mudah dimengerti, dan konsisten. Tidak ada perubahan view, URL, model, atau Python.

---

## 1. Latar & Tujuan

Tiga hub laporan yang ada saat ini bertampilan minimal (kartu polos judul + subjudul, tanpa ikon/pengelompokan/identitas visual):

- `templates/jurnal/laporan_keuangan_hub.html` — 6 laporan
- `templates/inventory/laporan_hub.html` — 6 laporan
- `templates/aset_tetap/laporan_aset_hub.html` — 2 laporan

Karena hub laporan sering diakses, tujuannya membuat ketiganya delightful dan mudah dipindai tanpa mengubah alur atau tautan yang ada.

**Non-tujuan (YAGNI):** tidak menggabungkan jadi satu hub terpusat; tidak menambah angka/KPI hidup (murni navigasi); tidak menyentuh laporan Piutang/Utang/POS; tidak mengubah view/URL/model.

## 2. Keputusan Desain (final)

1. **Tetap 3 hub terpisah**, masing-masing didesain ulang dan dibuat konsisten.
2. **Kartu murni navigasi**: ikon bermakna + judul + deskripsi + aksen warna kategori. Tanpa query backend tambahan.
3. **Gaya kartu: "Gradient Hero" (opsi C)** — ikon medali bergradien, tipografi lebih besar, chip "Lihat laporan →", hover mengangkat dengan bayangan berwarna.
4. **Dikelompokkan ke seksi berlabel** di dalam tiap hub (hub Aset yang hanya 2 laporan memakai grid rata tanpa label).
5. **Header hero berwarna tema per kategori** (Keuangan biru, Persediaan teal/hijau, Aset indigo).

## 3. Pendekatan Implementasi (Approach A)

CSS bersama + markup per template — sesuai gaya codebase (kelas `ni-` + markup per template).

- **Baru:** `static/css/report-hub.css` berisi seluruh kelas `.ni-rhub-*` dan tema per kategori. Dimuat lewat `{% block extra_css %}` hanya di 3 halaman hub (base.html tetap ramping).
- **Diubah:** 3 template hub di atas — markup saja.
- **Tidak diubah:** view, URL, model, Python. Semua tautan tetap `{% url %}` yang ada.
- **Ikon:** lucide (`data-lucide=...`), sudah dimuat global di base.html.

Alternatif yang ditolak: (B) partial `{% include %}` berbasis data di view — memindah data navigasi statis ke Python, menambah indireksi tanpa manfaat; (C) komponen JS — berlebihan.

## 4. Kontrak Kelas / Struktur Komponen

```
.ni-rhub  .ni-rhub--{keuangan|persediaan|aset}   ← root; menyetel CSS var tema
  .ni-rhub__hero              ← banner gradien
    .ni-rhub__hero-glow       ← lingkaran radial dekoratif (aria-hidden)
    .ni-rhub__hero-icon       ← ikon medali
    .ni-rhub__hero-title (h1) + .ni-rhub__hero-sub (p)
    .ni-rhub__hero-count      ← angka jumlah laporan + label
    .ni-rhub__hero-back       ← tombol Kembali (history.back())
  .ni-rhub__section           ← per grup (dilewati untuk hub Aset)
    .ni-rhub__section-label   ← teks uppercase + garis
  .ni-rhub__grid              ← grid responsif
    a.ni-rhub__card           ← seluruh kartu adalah <a href="{% url %}">
      .ni-rhub__card-glow (aria-hidden)
      .ni-rhub__card-icon     ← ikon gradien
      .ni-rhub__card-title (h3/h4) + .ni-rhub__card-desc (p)
      .ni-rhub__card-chip     ← "Lihat laporan →"
```

Kartu = elemen `<a>` penuh (bukan `<div onclick>`) agar bisa diklik seluruhnya, aksesibel, dan mendukung fokus keyboard.

## 5. Tema Warna (diturunkan dari palet asli aplikasi)

Tema di-set via CSS variable pada modifier root:

| Hub | `--rhub-c1 → --rhub-c2` (gradien) | `--rhub-chip-bg` | `--rhub-chip-fg` |
|---|---|---|---|
| `--keuangan` | `#0054a6 → #3b82f6` | `#e8f0fe` | `#0054a6` |
| `--persediaan` | `#0d9488 → #10b981` | `#ecfdf5` | `#0d9488` |
| `--aset` | `#6366f1 → #8b5cf6` | `#eef2ff` | `#6366f1` |

Bayangan hover kartu memakai warna kategori (`--rhub-c1` beropasitas rendah).

## 6. Isi & Pengelompokan Tiap Hub

Ikon = nama lucide. Semua tautan memakai `{% url %}` yang sudah ada; jumlah laporan tidak berubah.

### Laporan Keuangan (`--keuangan`) — 6 laporan
- **Laporan Utama:** Laporan Laba Rugi (`trending-up`, `jurnal:laporan_laba_rugi`) · Neraca (`scale`, `jurnal:neraca`) · Laporan Perubahan Ekuitas (`arrow-left-right`, `jurnal:laporan_perubahan_ekuitas`)
- **Buku & Saldo:** Neraca Saldo (`scale-3d`, `jurnal:neraca_saldo`) · Buku Besar (`book-open`, `jurnal:buku_besar`)
- **Analisis:** Analisis Keuangan (`line-chart`, `jurnal:analisis_keuangan`)

### Laporan Persediaan (`--persediaan`) — 6 laporan
- **Nilai & Biaya:** Valuasi Persediaan (`bar-chart-3`, `inventory:laporan_valuasi`) · Laporan HPP (`dollar-sign`, `inventory:laporan_hpp`)
- **Pergerakan Stok:** Kartu Stok (`layout-grid`, `inventory:stock_card`) · Buku Persediaan (`book`, `inventory:stock_ledger`)
- **Analisis & Ringkasan:** Slow / Fast Moving (`trending-up`, `inventory:laporan_velocity`) · Laporan Persediaan (`file-text`, `inventory:laporan_persediaan`)

### Laporan Aset (`--aset`) — 2 laporan, grid rata tanpa seksi
- Asset Register (`building-2`, `aset_tetap:laporan_register`) · Laporan Penyusutan (`trending-down`, `aset_tetap:laporan_penyusutan`)

## 7. Gerak, Responsif, Aksesibilitas

- **Masuk:** kartu fade-in bertahap (stagger `animation-delay`), memakai `animation.css` yang ada.
- **Hover:** angkat 4px + bayangan berwarna kategori; chip bergeser halus.
- **Responsif:** grid 3→2→1 kolom (`auto-fit`/breakpoint); hero menumpuk di mobile (ikon+judul atas, hitungan pindah bawah, tombol Kembali tetap terjangkau).
- **Aksesibilitas:** `<a>` dengan `:focus-visible` outline jelas; `@media (prefers-reduced-motion: reduce)` mematikan animasi & transform; kontras teks WCAG AA; elemen glow/ikon dekoratif `aria-hidden="true"`.

## 8. Kriteria Penerimaan

1. Ketiga hub tampil dengan gaya C: hero berwarna kategori, seksi berlabel (kecuali Aset), kartu ikon-gradien.
2. Semua tautan laporan tetap berfungsi ke tujuan yang sama seperti sebelumnya (tidak ada laporan hilang/tambah).
3. Tampilan rapi & bisa dipakai di layar mobile (grid menyusut, hero menumpuk).
4. `prefers-reduced-motion` dihormati; kartu dapat difokus keyboard dengan outline terlihat.
5. Tidak ada perubahan pada file view/URL/model/Python.
6. `report-hub.css` hanya dimuat di 3 halaman hub, bukan global.

## 9. Risiko

- **Nama URL/ikon salah ketik** → verifikasi tiap `{% url %}` cocok dengan `urls.py` dan tiap nama ikon valid di lucide saat implementasi.
- **Konsistensi antar hub** → ketiganya berbagi `report-hub.css` yang sama sehingga selaras otomatis.
