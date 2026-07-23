# Menghubungkan GoFood / GrabFood / ShopeeFood — Panduan Operator

**Untuk siapa:** staf yang menghubungkan channel pesan antar untuk sebuah perusahaan.
Tidak perlu latar belakang teknis.

**Aturan emas:**

1. Kerjakan **satu cabang dulu** sampai benar-benar live, baru sisanya.
2. **Jangan tekan Go Live** selama masih ada pemeriksaan merah.
3. Kalau tidak yakin sebuah nilai itu apa — **berhenti dan tanya**. Jangan menebak ID.

---

## 0. Struktur yang harus dipahami dulu

| Level | Artinya | Yang disimpan di sini |
|---|---|---|
| **Level 1** | Grup / holding / induk | Tidak ada pengaturan POS |
| **Level 2** | Perusahaan operasional | **Konfigurasi POS + akun merchant aggregator** |
| **Level 3** | Cabang / outlet fisik | **Konfigurasi cabang + hubungan ke outlet aggregator** |

Satu akun merchant GoFood/GrabFood/ShopeeFood dimiliki **Level 2**.
Setiap **Level 3** dipetakan ke satu outlet di aggregator.

---

## 1. Sebelum mulai — daftar periksa

Anda memerlukan:

- [ ] Akses **admin** ke akun merchant klien di portal aggregator (bukan akun kasir).
- [ ] Akses **admin** di Naveda untuk perusahaan tersebut.
- [ ] Akses **Partner API sudah disetujui** oleh aggregator.
      Ini proses komersial dengan pihak aggregator dan **tidak bisa dipercepat dari Naveda**.
      Tanpa ini, langkah "Hubungkan Akun" pasti gagal.
- [ ] Semua cabang sudah dibuat sebagai **Entitas Bisnis Level 3** dan sudah punya
      **Konfigurasi POS Cabang**.
- [ ] **Katalog sudah benar** di Naveda. Yang dikirim ke aggregator adalah isi katalog ini —
      kalau harga salah di Naveda, harga akan salah juga di aplikasi pesan antar.

> ⚠️ **Kredensial (Client ID / Secret)** dimasukkan oleh administrator, sekali saja,
> per perusahaan. Operator cabang tidak perlu melihat nilai tersebut.

---

## 2. Alur umum

```
Sidebar → Entitas Bisnis → Channel Pesan Antar → Hubungkan Channel
   → 1 Prasyarat → 2 Kredensial → 3 Hubungkan Akun → 4 Webhook
   → 5 Hubungkan Cabang → 6 Pengaturan → 7 Kirim Menu
   → 8 Pemeriksaan → 9 Go Live
```

Wizard **menyimpan posisi Anda**. Tutup tab kapan saja, buka lagi, lanjut dari langkah terakhir.
Menekan tombol dua kali aman — semua langkah dirancang tidak menggandakan apa pun.

---

## 3. GrabFood — paling otomatis

**Perkiraan waktu:** 15 menit + 2 menit per cabang.

### Langkah 3 — Hubungkan Akun
Tekan **Hubungkan Akun**. Anda diarahkan ke situs Grab. Masuk dengan akun **admin**
klien, lalu setujui.

- ✅ Berhasil: kembali ke Naveda, muncul "Akun terhubung".
- ❌ Gagal dua kali berturut-turut: ambil tangkapan layar pesan errornya, eskalasi.

### Langkah 5 — Hubungkan Cabang
Untuk setiap cabang tekan **Aktifkan**. Anda diarahkan ke Grab, setujui, kembali.

- ✅ Berhasil: kolom **Store ID** terisi **otomatis**. *Anda tidak pernah mengetik ID ini.*
- ⏳ Status **Menunggu**: Grab masih memproses. **Tunggu. Jangan tekan Aktifkan lagi** —
  Grab memblokir aktivasi ulang hingga 24 jam.
- ❌ "Store already registered": sudah terhubung sebelumnya. Lanjut saja.

Lanjut ke §6.

---

## 4. GoFood — outlet terbaca otomatis

**Perkiraan waktu:** 10 menit + 1 menit per cabang.

> **Prasyarat perusahaan (sekali seumur hidup, oleh tim teknis):**
> Naveda harus terdaftar sebagai **GoBiz Partner (Facilitator)**. Pengajuan ini punya
> waktu tunggu eksternal yang tidak bisa diprediksi — **ajukan lebih awal**.

### Langkah 3 — Hubungkan Akun
**Siapkan HP admin merchant sekarang** — OTP dikirim ke sana dan hanya berlaku ±2 menit.

Tekan **Hubungkan Akun** →
1. Masukkan nomor HP admin merchant.
2. Ketik OTP yang masuk.
3. Baca layar persetujuan, tekan **Izinkan**.

- ❌ OTP tidak datang: pastikan nomornya milik pemilik akun. Jangan minta ulang lebih
  dari dua kali — nomor bisa diblokir sementara.
- ❌ "Code expired": tekan **Hubungkan Akun** lagi. Aman diulang.

### Langkah 4 — Daftarkan Webhook
Tekan **Daftarkan / Sinkronkan Ulang**. Semua event didaftarkan sekaligus.
Ada yang merah? Tekan sekali lagi — hanya yang gagal yang diperbaiki.
Masih merah setelah dua kali: eskalasi.

### Langkah 5 — Hubungkan Cabang
Tekan **Muat Daftar Outlet**. Outlet klien muncul lengkap dengan **alamat**.

Klik outlet → klik kolom Store ID pada baris cabang yang cocok → **Simpan**.

> 📍 **Cocokkan berdasarkan ALAMAT, bukan nama.** Nama cabang sering nyaris sama
> ("Cabang 1", "Cabang 2"). Salah pasang = pesanan masuk ke dapur yang salah dan
> omzet tercatat di cabang yang salah.

- ❌ Outlet tidak muncul: berarti belum terdaftar di GoBiz, atau akun yang Anda setujui
  bukan pemiliknya.

Lanjut ke §6.

---

## 5. ShopeeFood — satu nilai disalin manual

**Perkiraan waktu:** 5 menit per cabang.

> ShopeeFood **tidak punya alur persetujuan otomatis**. Ini bukan keterbatasan Naveda —
> API-nya memang tidak tersedia untuk umum. Yang bisa dicapai: **satu kali salin-tempel**
> per cabang, dengan pemeriksaan format otomatis.

### Langkah 2 — Kredensial (administrator)
Administrator memasukkan Partner ID dan Partner Secret dari Shopee, sekali per perusahaan.
Kalau tertulis "Kredensial belum diisi", **berhenti** dan minta tim teknis melakukannya.

### Langkah 5 — Hubungkan Cabang
Di portal Shopee, buka outlet, cari **Store ID** outlet tersebut.

> 🔍 Yang dicari: identitas milik **satu outlet** — bukan nama toko, bukan ID akun.
> ⚠️ Jangan menebak dan jangan memakai ulang ID cabang lain.

Tempel di baris cabang yang sesuai → **Simpan**.
Kalau muncul "Format Store ID tidak sesuai", kemungkinan besar Anda menyalin nilai
yang salah — kembali ke portal, jangan dipaksakan.

---

## 6. Langkah yang sama untuk ketiga channel

### Langkah 6 — Pengaturan Channel

| Pengaturan | Penjelasan |
|---|---|
| **Kirim ke dapur saat** | *Saat pesanan masuk* (default, paling aman) atau *Saat driver tiba* (mengurangi makanan terbuang bila dibatalkan). Ragu → pilih default. |
| **Tax %** | ⚠️ Salah isi membuat pajak dan omzet **setiap** pesanan salah. Tidak tahu → tanya bagian keuangan. Jangan menebak. |
| **Markup harga %** | Menaikkan harga jual di channel ini untuk menutup komisi aggregator. |

### Langkah 7 — Kirim Menu
Tekan **Kirim Menu Semua Cabang**.
Gagal? Pesan error menyebut item mana yang bermasalah. Perbaiki item itu di katalog
Naveda, lalu kirim lagi. Ulangi sampai hijau.

### Langkah 8 — Pemeriksaan
Tekan **Jalankan Pemeriksaan**. Setiap baris merah menyertakan **cara memperbaikinya**.
Tombol Go Live tetap terkunci sampai semua hijau — ini disengaja.

### Langkah 9 — Go Live
Tekan **Go Live**, lalu **buat satu pesanan sungguhan** dari aplikasi aggregator.
Pesanan harus muncul di **Pesanan Masuk** dalam hitungan detik.
Setelah itu batalkan/refund sesuai kebijakan klien.

**Belum selesai sampai pesanan uji benar-benar masuk.** Status "Live" hanya berarti
Naveda sudah siap; pesanan uji yang membuktikan jalurnya benar-benar tersambung.

---

## 7. Kalau ada masalah

| Yang terlihat | Artinya | Yang dilakukan |
|---|---|---|
| Menu macet "Berjalan" >30 menit | Aggregator belum konfirmasi | Tunggu 30 menit, kirim ulang sekali. Masih macet → eskalasi |
| Menu gagal, error menyebut item | Data katalog di Naveda | Perbaiki item tersebut, kirim ulang |
| Pemeriksaan **Autentikasi** merah | Kredensial ditolak/dicabut | Coba Hubungkan Ulang. Gagal → eskalasi |
| Pemeriksaan **Alamat publik** merah | Setelan server | **Eskalasi.** Tidak bisa diperbaiki dari halaman ini |
| Cabang **Menunggu** berjam-jam (Grab) | Grab masih memproses | **Tunggu.** Jangan tekan Aktifkan lagi |
| Pesanan masuk tapi "Belum terbukukan" | Akun akuntansi cabang belum lengkap | Lengkapi Konfigurasi POS Cabang, lalu tekan **Bukukan Ulang** |
| Item "Belum cocok" pada pesanan | Aggregator kirim item di luar katalog | Petakan item di katalog, lalu **Bukukan Ulang** |
| Pesanan ganda | Biasanya aggregator mengirim ulang | Laporkan. **Jangan batalkan sendiri** salah satunya |
| Harga salah di aplikasi | Markup/tax channel salah | Perbaiki di Pengaturan Channel, kirim menu ulang |

**Langsung eskalasi (jangan coba-coba) bila:** kredensial perlu diganti, pemeriksaan
tetap merah setelah dua kali, pesanan masuk ke cabang yang salah, atau angka uang terlihat
tidak wajar.

---

## 8. Yang masih perlu diverifikasi sebelum panduan ini dipakai staf

Bagian API di atas berasal dari dokumentasi resmi dan dari kode ini.
**Navigasi portal aggregator belum diverifikasi** — tata letaknya privat dan sering berubah.

Sebelum diserahkan ke staf, satu orang perlu:

1. Menangkap layar **jalur menu** ke bagian integrasi di tiap portal
   (Grab Merchant Portal, GoBiz, Shopee).
2. Mencatat **label tombol persetujuan** yang sebenarnya.
3. Untuk ShopeeFood: layar dan **label field** tempat Store ID berada, plus contoh
   bentuk nilainya (angka disamarkan).
4. Mencatat perbedaan istilah **Inggris vs Bahasa Indonesia**.

Lalu: **minta satu orang yang belum pernah melakukan setup mengikuti panduan ini
dari awal sampai akhir pada merchant uji.** Setiap kali dia ragu, di situ panduan
kurang satu kalimat. Uji coba itulah yang membuat panduan ini benar-benar bisa diikuti —
bukan penulisannya.
