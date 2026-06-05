# Setup Guide: Akun User & Entitas Bisnis untuk Kasir

Panduan langkah demi langkah untuk mengaktifkan sistem kasir dari nol. Ikuti urutan ini — setiap langkah bergantung pada langkah sebelumnya.

---

## Ringkasan Langkah

```
1. Buat akun CoA (akun akuntansi) yang dibutuhkan
2. Buat Sub-Transaction Type untuk POS
3. Buat Entitas Bisnis (lv1 → lv2 → lv3)
4. Setup POS Config di lv1 (merchant defaults)
5. Setup Outlet POS Config di lv3 (opsional override)
6. Masukkan stok inventory untuk outlet
7. Buat akun user kasir
8. Hubungkan user ke Entitas Bisnis
9. Test kasir
```

---

## Langkah 1: Siapkan Akun CoA

Kasir membutuhkan 3 akun CoA minimum. Buka **Master Data → Chart of Accounts**.

Buat atau tandai akun-akun berikut:

| Kebutuhan | Tipe Akun | Contoh Nama |
|---|---|---|
| **Pendapatan penjualan** | Pendapatan | `4-1001 Pendapatan Penjualan` |
| **HPP / Biaya pokok penjualan** | Beban | `5-1001 Harga Pokok Penjualan` |
| **Kas atau rekening bank** | Aset | `1-1001 Kas Tunai` atau `1-1002 Kas Bank` |
| **Persediaan** (per item) | Aset | sudah ada di Item Master masing-masing |

> Catat ID akun-akun ini — akan dipakai di Langkah 4.

---

## Langkah 2: Buat Sub-Transaction Type untuk POS

Buka **Master Data → Tipe Transaksi → Sub-Transaction Type**.

Klik **Tambah**, isi:
- **Nama:** `Penjualan Kasir` (atau nama bebas)
- **Module:** `sales`
- **Default Offset Account (HPP):** pilih akun HPP dari Langkah 1
- **Default Revenue Account:** pilih akun Pendapatan dari Langkah 1
- **Default Payment Account:** pilih akun Kas dari Langkah 1

Simpan. Catat ID Sub-Transaction Type ini.

---

## Langkah 3: Buat Entitas Bisnis

Buka **Entitas Bisnis** di sidebar.

### 3a. Buat Level 1 (Merchant / Brand)
Klik **+ Tambah Entitas Bisnis**.
- **Nama:** contoh `Naveda Kopi`
- **Tipe Entitas:** pilih tipe yang sesuai (buat baru jika belum ada)
- **Relasi:** `Pelanggan`
- **Status:** Aktif
- Simpan.

### 3b. Buat Level 2 (Area / Wilayah)
Di halaman Entitas Bisnis, klik tombol **+** hijau di baris lv1 yang baru dibuat.
- **Nama:** contoh `Area Selatan`
- **Status:** Aktif
- Simpan.

### 3c. Buat Level 3 (Outlet / Toko)
Di baris lv2, klik tombol **+** hijau.
- **Nama:** contoh `Outlet Senopati`
- **Status:** Aktif
- Simpan.

> Lv3 adalah **outlet** yang muncul di layar pilih kasir. Nama lv3 = nama yang kasir pilih.

---

## Langkah 4: Setup POS Config di Level 1

Klik ikon **pencil (edit)** di baris lv1 → halaman edit lv1 terbuka.

Scroll ke bawah, temukan section **"POS Configuration"**. Klik **Setup POS Config**.

Isi form:
- **Is POS Active:** ✓ centang
- **Default Tax %:** `11` (PPN Indonesia) atau `0` jika tidak kena pajak
- **Sub-Transaction Type:** pilih yang dibuat di Langkah 2
- **Revenue Account:** akun Pendapatan dari Langkah 1
- **HPP Account:** akun HPP dari Langkah 1
- **Default Payment Account:** akun Kas dari Langkah 1
- **QRIS Image:** upload gambar QRIS jika ada (opsional)

Klik **Simpan**.

> Konfigurasi lv1 adalah **default** untuk semua outlet di bawahnya. Jika semua outlet pakai pengaturan sama, cukup isi di sini.

---

## Langkah 5: Setup Outlet Config di Level 3 (Opsional)

Hanya diperlukan jika outlet tertentu butuh pengaturan berbeda dari merchant default (misalnya pajak berbeda atau akun kas berbeda).

Klik ikon **pencil** di baris lv3 → halaman edit lv3 terbuka.

Scroll ke bawah, section **"Outlet POS Config"**. Klik **Kelola Outlet POS Config**.

Isi hanya field yang ingin di-override. Kosongkan field = ikut setting merchant (lv1).

Simpan.

---

## Langkah 6: Masukkan Stok Inventory

Produk hanya muncul di kasir jika ada **stok di InventoryRecord** untuk outlet tersebut.

### 6a. Pastikan Item Master ada
Buka **Inventory → Item Master**. Setiap produk yang akan dijual harus ada sebagai item dengan:
- Tipe item: `FG` (Finished Good) atau `ITM` (Item)
- **CoA Account (Persediaan):** harus diset — ini akun neraca untuk stok item tersebut
- **Kategori:** isi untuk filter kategori di kasir

### 6b. Masukkan stok
Ada dua cara:
1. **Melalui transaksi pembelian** — buat Purchase, otomatis mengisi InventoryRecord
2. **Saldo Awal** — buka Jurnal → Saldo Awal, masukkan stok awal

Pastikan `InventoryRecord` untuk item tersebut memiliki field `entitas_bisnis_lv3` yang menunjuk ke outlet lv3 yang baru dibuat, atau `entitas_bisnis` (lv1) sebagai fallback.

> Kasir akan otomatis menampilkan produk dari lv3-specific inventory. Jika tidak ada, fallback ke lv1.

---

## Langkah 7: Buat Akun User Kasir

Buka **User** di sidebar (hanya visible untuk admin/superuser).

Klik **+ Tambah User**.
- **Email:** email kasir (dipakai untuk login)
- **Nama:** nama lengkap kasir (muncul di brandbar kasir)
- **Password:** set password awal
- **Role:** pilih role yang sesuai (atau biarkan kosong untuk permission manual)
- **Status:** Aktif

Simpan.

---

## Langkah 8: Hubungkan User ke Entitas Bisnis

Dari daftar user, klik nama user kasir → halaman detail user.

Scroll ke section **"Akses Entitas Bisnis"**.

Di dropdown, pilih Entitas Bisnis lv1 yang dibuat di Langkah 3 (contoh: `Naveda Kopi`). Klik tambah.

Badge nama EB muncul di section tersebut = akses sudah terhubung.

> User yang tidak punya akses ke EB manapun tidak bisa login ke dashboard secara penuh.

---

## Langkah 9: Test Kasir

1. Login dengan akun kasir yang baru dibuat.
2. Klik **Kasir** di sidebar.
3. Layar **Pilih Outlet** muncul — outlet lv3 yang dibuat harus ada di sini.
4. Klik outlet → kasir memuat katalog produk.
5. Jika katalog kosong: periksa stok inventory di Langkah 6.
6. Klik satu produk → masuk ke tiket.
7. Klik **Selesaikan** → pilih metode bayar → konfirmasi.
8. Layar **Pembayaran Berhasil** muncul → transaksi berhasil.

Verifikasi di **Sales** (sidebar) — transaksi baru dengan prefix `TRX-SAL-` harus muncul di daftar.

---

## Troubleshooting

| Masalah | Penyebab | Solusi |
|---|---|---|
| Outlet tidak muncul di Pilih Outlet | lv3 tidak aktif atau belum ada | Aktifkan lv3 di edit entitas bisnis |
| Katalog kosong | Tidak ada stok di InventoryRecord | Masukkan stok (Langkah 6) |
| Error 500 saat pilih outlet | POS Config belum diset | Kerjakan Langkah 4 |
| "Sub-Transaction Type belum dikonfigurasi" | STT kosong di config | Isi STT di Langkah 4 atau 5 |
| "Revenue atau HPP account belum dikonfigurasi" | Akun kosong di config | Isi akun di Langkah 4 |
| Produk ada tapi item.coa_account kosong | Item Master tidak punya CoA Persediaan | Set CoA Account di Item Master |
| User tidak bisa akses kasir | Permission tidak ada | Set permission `sales_view` di halaman user |
