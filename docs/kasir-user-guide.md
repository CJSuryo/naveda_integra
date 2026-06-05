# Panduan Kasir — Cara Menggunakan Halaman Kasir

Halaman Kasir adalah layar khusus kasir berbasis tablet untuk mencatat transaksi penjualan. Kasir tidak perlu memahami akuntansi — semua entri jurnal dan perhitungan HPP terjadi otomatis di belakang layar.

---

## 1. Membuka Halaman Kasir

Klik **Kasir** di sidebar kiri (tepat di bawah Dashboard).

Browser akan berpindah ke layar penuh dengan latar belakang gelap — sidebar aplikasi hilang. Ini adalah mode kasir eksklusif.

---

## 2. Memilih Outlet

Saat pertama kali membuka halaman, akan muncul layar **Pilih Outlet** berisi kartu-kartu outlet yang aktif.

- Klik kartu outlet yang ingin digunakan.
- Layar POS akan langsung muncul, memuat katalog produk untuk outlet tersebut.
- Pilihan outlet disimpan di browser (`localStorage`) — saat membuka kembali halaman, outlet yang sama otomatis terpilih tanpa harus memilih ulang.

> Jika outlet yang diinginkan tidak muncul, minta admin untuk mengaktifkan outlet di halaman **Entitas Bisnis Level 3**.

---

## 3. Tampilan Utama

Layar dibagi dua kolom:

| Kiri — Katalog Produk | Kanan — Tiket Pesanan |
|---|---|
| Brandbar, pencarian, filter kategori, grid produk | Daftar item pesanan, total, metode bayar, tombol bayar |

---

## 4. Mencari Produk

**Pencarian teks:**
Ketik nama produk atau kode item di kotak pencarian atas. Pencarian berlaku secara langsung (tanpa tekan Enter) dan menyaring grid produk secara real-time.

**Filter kategori:**
Klik salah satu pil kategori (contoh: Kopi, Non-Coffee, Makanan) untuk menyaring produk per kategori. Angka kecil di setiap pil menunjukkan jumlah produk di kategori tersebut.
Klik **Semua** untuk menampilkan semua produk kembali.

---

## 5. Menambahkan Produk ke Pesanan

### Produk tanpa pilihan (modifier)
Klik kartu produk → produk langsung masuk ke tiket. Muncul notifikasi singkat di bawah layar.

Jika produk yang sama diklik lagi, jumlahnya bertambah di baris yang sama (tidak membuat baris duplikat), selama pilihan modifiernya identik.

### Produk dengan pilihan (ada label "Pilihan" di kartu)
Klik kartu produk → panel **Pilih Opsi** geser masuk dari kanan.

Di panel ini:
- Pilih opsi untuk setiap grup (contoh: tingkat gula, suhu, topping).
- Grup bertanda **Wajib** (merah) harus dipilih sebelum bisa menambahkan.
- Grup **Opsional** boleh dilewati.
- Atur **Jumlah** item di bagian bawah panel.
- Klik tombol hijau **Tambah + Rp …** untuk memasukkan ke tiket.

---

## 6. Mengelola Tiket Pesanan

Setiap baris di tiket menampilkan:
- Nama produk + pilihan yang dipilih (jika ada)
- Total harga baris
- Kontrol jumlah (tombol **−** dan **+**)
- Tombol **Ubah** (untuk produk dengan pilihan — membuka ulang panel modifier)
- Tombol **🗑** merah untuk menghapus baris

**Kurangi jumlah hingga 0:**
Tekan **−** saat jumlah = 1 → baris terhapus otomatis.

**Hapus langsung:**
Klik ikon tempat sampah merah di ujung kanan baris.

---

## 7. Menambahkan Diskon

Klik **Tambah diskon** di area total.

Panel diskon geser dari kanan, berisi dua jenis:

| Jenis | Pilihan |
|---|---|
| **Persentase** | Tanpa, 5%, 10%, 15%, 20%, 25% |
| **Nominal** | Rp 10.000, Rp 25.000, Rp 50.000 |

Klik pilihan → diskon langsung diterapkan, total dihitung ulang.
Pilih **Tanpa** untuk menghapus diskon.

> PPN 11% dihitung di atas subtotal **setelah** diskon.

---

## 8. Menahan Pesanan (Hold)

Jika perlu melayani pelanggan lain sementara pesanan pertama belum selesai:

1. Klik tombol **Tahan** (biru, bawah tiket) → pesanan disimpan sementara, tiket bersih.
2. Chip **Tertahan** di pojok kanan atas brandbar menampilkan jumlah pesanan yang ditahan.
3. Untuk melanjutkan pesanan yang ditahan: klik chip **Tertahan** → panel geser masuk → klik **Lanjutkan** di kartu pesanan yang dimaksud.
4. Klik ikon 🗑 di kartu pesanan tertahan untuk membuangnya.

---

## 9. Membatalkan Pesanan (Void)

Klik **Batalkan** (merah, bawah tiket) → semua item di tiket dihapus, tiket bersih.

Ini hanya membersihkan tiket lokal — tidak ada transaksi yang dibuat, sehingga tidak ada yang perlu dibatalkan di sistem.

---

## 10. Pembayaran

### Pilih metode bayar
Tiga tombol di atas tombol bayar:
- **Tunai** — pembayaran uang tunai (default)
- **Kartu EDC** — kartu kredit/debit
- **QRIS** — pembayaran QR code

### Klik tombol hijau besar **Selesaikan**

**Tunai:**
Panel numpad muncul dari bawah.
- Ketik nominal uang yang diterima dari pelanggan.
- Baris atas menampilkan **Uang diterima**, baris bawah menampilkan **Kembalian** (hijau) atau **Kurang** (merah).
- Tombol cepat: **Uang Pas**, nominal terdekat ke 50rb, nominal terdekat ke 100rb.
- Klik **Konfirmasi Pembayaran** (hanya aktif saat uang cukup).

**Kartu EDC / QRIS:**
Tidak ada numpad — transaksi langsung diproses ke sistem.

### Layar sukses
Setelah konfirmasi:
- Layar hijau **Pembayaran Berhasil** muncul.
- Tampil: Total bayar, metode + nominal, Kembalian (khusus tunai).
- Nomor transaksi (`TRX-SAL-…`) ditampilkan.
- Dua tombol:
  - **Cetak Struk** — tampilkan notifikasi (integrasi printer terpisah)
  - **Transaksi Baru** — bersihkan tiket, siap transaksi berikutnya

---

## 11. Tips

| Situasi | Solusi |
|---|---|
| Produk tidak muncul | Stok habis atau kategori salah filter — cek filter kategori atau stok di menu Inventori |
| Outlet berubah | Hapus pilihan outlet di browser (hapus `localStorage`) atau buka di tab baru |
| Tombol bayar abu-abu | Tiket kosong — tambahkan produk terlebih dahulu |
| Error saat konfirmasi bayar | Konfigurasi akun POS belum lengkap — hubungi admin untuk setup di halaman Entitas Bisnis |
