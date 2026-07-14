# Design Review — Account Mapping Engine → Posting Engine

Date: 2026-07-15
Reviewer: System Architect (design review, bukan implementasi)
Subjek: `docs/superpowers/specs/2026-07-14-account-mapping-engine-design.md`

---

## 0. Verdict

Spesifikasi 2026-07-14 **benar sebagai perbaikan kebersihan (hygiene fix)**, tetapi **salah sebagai fondasi ERP**.

Ia memperbaiki masalah yang nyata (magic string, kolom `default_*_account` yang fixed, FK config bertebaran) dan cara memperbaikinya sehat (registry deklaratif, resolver tunggal, strangler + fallback). Kalau tujuannya hanya "hentikan pendarahan", spec ini layak jalan hari ini.

Tapi ia **tidak akan pernah bisa memenuhi daftar 16 business event POS Anda**, dan bukan karena tabelnya kurang generik — justru karena ia menjawab pertanyaan yang salah.

> Account Mapping menjawab **"akun mana yang dipakai?"**
> Yang sebenarnya belum punya rumah adalah **"baris jurnal apa saja yang lahir dari kejadian bisnis ini, di sisi mana, senilai berapa?"**

Selama pertanyaan kedua dijawab oleh kode Python yang di-hardcode per modul, mengganti sumber akun dari magic string menjadi tabel mapping **tidak menambah satupun business event baru yang bisa dikonfigurasi admin**.

**Rekomendasi utama:** naikkan konsepnya dari *Account Mapping Engine* menjadi **Posting Engine** (unit kerjanya: Business Event → Posting Lines). Jangan langsung melompat ke "Business Event Engine" yang punya Tax Rule + Approval Rule + Workflow Rule + Notification Rule — itu overreach yang akan membunuh proyek ini (alasan di §7).

---

## 1. Temuan dari kode (bukan asumsi)

Review ini diverifikasi langsung ke kode, bukan dari spec saja.

### 1.1 Generator jurnal adalah hardcoded, dan itulah bottleneck sesungguhnya

`create_sales_automated_journals()` ([apps/sales/services.py:139-220](../../apps/sales/services.py#L139-L220)) — inilah yang benar-benar membuat jurnal untuk POS, karena kasir membuat `SalesHeader` langsung (`pos_orders/services/sales_integration.py` sudah jadi stub `NotImplementedError`; jalur aggregator belum ada).

Isinya secara efektif hanya dua blok:

```python
# 1. COGS entry:    Debit  si.offset_coa_account   / Credit si.inventory_account
# 2. Revenue entry: Debit  payment_akun            / Credit si.revenue_account
```

Konsekuensinya, terhadap 16 event POS Anda:

| Business Event POS (daftar Anda) | Bisa diposting hari ini? |
|---|---|
| Penjualan Barang | ya (blok Revenue) |
| Pengurangan Persediaan + HPP | ya (blok COGS) |
| Pajak (PPN Keluaran) | ya, tapi **lewat modul `pajak`, jurnal terpisah** |
| Pembayaran Tunai / QRIS / Transfer / Kartu Kredit | separuh — hanya lewat satu `payment_akun` per baris; tidak ada konsep multi-payment/split |
| Penjualan Jasa | tidak dibedakan dari penjualan barang |
| Retur Penjualan | **tidak ada** |
| Refund | **tidak ada** (`refund_service.complete_refund` → `NotImplementedError`) |
| Service Charge | **tidak ada** (persentasenya ada di `StorePOSConfig`, akunnya tidak ada, jurnalnya tidak ada) |
| Tips | **tidak ada** |
| Pembulatan | **tidak ada** |
| Diskon Penjualan | **tidak ada** (netting di harga, bukan akun kontra) |
| Pembayaran Piutang | ada di modul piutang, terpisah |

**Ini bukti keras.** `StorePOSConfig.service_charge_pct` sudah ada dan sudah dihitung (`effective_service_charge_pct()`), tapi **tidak ada satu baris pun kode yang menjurnalnya**. Menambah `AccountMapping('pos', 'service_charge', 'pendapatan_service_charge')` tidak akan mengubah apapun — tidak ada yang memanggilnya, karena tidak ada mesin yang tahu bahwa service charge harus melahirkan satu baris kredit senilai `subtotal × pct`.

Kesimpulan §1.1: **spec 2026-07-14 mengoptimalkan sisi yang tidak menjadi kendala.** Sisi yang menjadi kendala adalah *journal line generation*, dan spec itu secara eksplisit tidak menyentuhnya.

### 1.2 Modul `pajak` sudah membuktikan tesis Anda di §8 — sekaligus memperingatkannya

`PajakTransaksi` ([apps/pajak/models.py:95-140](../../apps/pajak/models.py#L95)) punya `jenis_pajak`, `sifat_pajak`, `akun_pajak`, `akun_lawan`, `source_type`/`source_id`, dan memposting jurnalnya sendiri.

Baca ulang itu: **`sifat_pajak` menentukan arah debit/kredit, dan ada dua akun (pajak + lawan).** Itu, secara struktural, adalah sebuah **posting rule** — persis konsep yang saya rekomendasikan — hanya saja dibangun sekali khusus untuk pajak, dengan tabelnya sendiri, jurnalnya sendiri, dan tidak bisa dipakai ulang siapapun.

Ini dua hal sekaligus:
- **Pembenaran** untuk intuisi Anda di §8: benar, satu event punya konsekuensi lebih dari sekadar "akun", dan tax rule memang sudah hidup di luar account mapping.
- **Peringatan**: jika setiap concern membangun mesinnya sendiri-sendiri, dalam 2 tahun Anda punya lima "engine" yang tidak saling kenal. Anda sudah punya **empat** sistem mapping yang tidak terkoordinasi hari ini (STT, magic string, FK bertebaran, cascade POS) — dan menambah engine #5 tanpa tulang punggung bersama hanya memindahkan masalah.

### 1.3 Scope `entitas_bisnis` tunggal adalah **regresi** untuk POS

Spec mengunci kunci mapping sebagai `(module, transaction_type, role, entitas_bisnis)`.

Tapi POS **sudah** punya cascade lebih kaya yang berjalan di produksi:

- `MerchantPOSConfig` (Lv1) → `OutletPOSConfig` (Lv3) override `revenue_account`, `offset_coa_account`, `default_payment_account`
- **plus** `PaymentMethod.payment_account` / `offset_coa_account` — akun per metode bayar, dan inilah yang secara langsung menjawab kebutuhan Anda "Pembayaran QRIS → Piutang QRIS, Kartu Kredit → Piutang Bank"

Spec sendiri sudah menyadari ini di catatan auditnya dan "menyerah" dengan menunda POS ke Tahap 3, sambil mengusulkan "kemungkinan `entitas_bisnis` sebagai satu-satunya scope alih-alih 3 level". **Itu keliru.** Memaksa POS turun ke satu level scope = kehilangan kemampuan yang sudah dimiliki hari ini. Sebuah "engine" yang lebih miskin dari sistem yang digantikannya bukan engine, tapi downgrade.

Ini bukan sekadar detail POS. Ini menunjukkan model scope-nya salah bentuk sejak awal: scope bukan **satu FK**, tapi sebuah **rantai spesifisitas**.

### 1.4 `module` di dalam kunci mapping adalah ambigu — event tidak dimiliki modul

Modul `aset_tetap` hanya punya **satu** otomatisasi jurnal: `process_depreciation()` ([apps/aset_tetap/services.py:138-205](../../apps/aset_tetap/services.py#L138)), dua leg dengan magic string `5.1.19` / `1.2.7`. Itu saja.

**Perolehan aset tidak dijurnal oleh aset_tetap.** `AsetTetapRecord.purchase_item` adalah FK ke Purchase — aset lahir dari alur pembelian, jurnalnya dibuat Purchase, dan akun asetnya dipilih oleh STT/item Purchase. Pelepasan, revaluasi, impairment: **tidak ada jurnalnya sama sekali** hari ini.

Ini membongkar asumsi diam-diam di spec 2026-07-14: bahwa event dimiliki oleh modul yang memegang master datanya. Ia tidak.

> "Perolehan Aset Tetap" adalah event akuntansi **aset tetap**, tetapi dipancarkan oleh alur **purchase**.

Maka `(module, transaction_type, role)` ambigu sejak kunci pertamanya. Perolehan aset didaftarkan di registry `purchase` atau `aset_tetap`? Di `purchase` → admin mencarinya di layar yang salah. Di `aset_tetap` → tidak ada kode aset_tetap yang memanggilnya. Spec tidak punya jawaban untuk ini, karena tidak pernah memisahkan **siapa yang memancarkan event** dari **konsekuensi akuntansi milik siapa**.

**Perbaikannya:** kunci mapping adalah **event**, bukan `(module, event)`. `module` turun status menjadi **label pengelompokan UI belaka** — event boleh ditampilkan di bawah grup yang paling masuk akal bagi admin ("Aset Tetap"), sepenuhnya terlepas dari kode modul mana yang memancarkannya (`purchase`). Ini juga alasan tambahan kenapa registry harus mendeklarasikan `group` secara eksplisit (§3.1), bukan menurunkannya dari nama app Django.

Efek samping yang perlu Anda sadari: daftar event per modul di §5 pertanyaan Anda (Aset Tetap: perolehan/penyusutan/pelepasan/revaluasi/impairment) **hampir seluruhnya belum ada** di sistem. Hanya penyusutan yang hidup. Sisanya greenfield — sama seperti service charge di POS. Ini kabar baik untuk rollout: lebih banyak permukaan nol-risiko untuk membuktikan engine, lebih sedikit perilaku lama untuk dirusak.

### 1.5 `Role.kategori` sebagai satu string terlalu kaku

Beberapa role secara sah boleh jatuh ke lebih dari satu kategori CoA:

- **Pembulatan** → bisa `pendapatan` (pembulatan ke atas) atau `beban` (ke bawah). Anda sendiri menuliskannya: "Pendapatan/Pengeluaran Pembulatan".
- **Selisih kas (cash over/short)** → sama.
- **Laba/Rugi Pelepasan Aset** → sama.

`kategori: str` memaksa admin memilih akun dari satu kategori saja, atau memaksa programmer memecah satu konsep jadi dua role. Sepele untuk diperbaiki (`kategori: tuple[str, ...]`), tapi menandakan registry-nya dirancang dari contoh-contoh mudah.

---

## 2. Jawaban langsung atas pertanyaan Anda

### §1 Apakah semua modul boleh memakai struktur konfigurasi yang sama?

**Ya untuk tulang punggungnya, tidak untuk bentuknya.** Ini pertanyaan yang paling sering dijawab salah di ERP, ke dua arah.

Yang **sama** di seluruh modul — dan wajib sama, kalau tidak Anda kembali punya 11 sistem:

1. Sebuah kejadian bisnis terjadi (Business Event).
2. Kejadian itu melahirkan sejumlah baris jurnal (posting lines) yang **harus balance**.
3. Setiap baris butuh: akun, arah (D/K), nilai, dimensi, entitas.
4. Akun dipilih berdasarkan konteks yang berlapis (global → EB → outlet → item → payment method).
5. Kalau konfigurasinya belum lengkap, sistem harus **gagal jelas**, bukan menjurnal salah diam-diam.

Itu invarian akuntansi, bukan preferensi modul. POS, Aset Tetap, Piutang, Pembelian — semuanya tunduk padanya.

Yang **berbeda** per modul: jumlah event, sumber nilai, dan cara admin ingin melihatnya. Aset Tetap punya ~5 event yang jarang berubah dan nilainya berasal dari skedul penyusutan. POS bisa punya 100+ event, nilainya berasal dari keranjang belanja, dan berubah tiap kali marketing bikin program baru.

**Kesalahan yang harus dihindari ada dua, bukan satu.** Spec sekarang jatuh ke kesalahan pertama; usulan Anda berisiko jatuh ke kedua:

- Terlalu seragam (spec sekarang): satu tabel `(module, tt, role, akun)`, semua modul dipaksa muat. Hasil: POS tidak muat, dan diam-diam dikeluarkan ke Tahap 3.
- Terlalu beragam (risiko usulan Anda): tiap modul punya struktur dan UI sendiri. Hasil: Anda menulis ulang resolver, validasi, audit trail, dan strict-mode 11 kali. Itu persis penyakit yang sedang Anda obati hari ini.

**Rekomendasi: satu spine, banyak presenter.** Model data, resolver, dan aturan balance **identik** untuk semua modul. Yang boleh berbeda per modul hanyalah *deklarasi* di registry (event apa saja, dikelompokkan bagaimana, label apa) dan *presenter* UI yang membaca deklarasi itu. Modul tidak boleh punya tabel mapping sendiri.

### §2 Business Event vs Technical Role — mana yang benar?

**Keduanya. Anda sedang membandingkan dua hal yang bukan alternatif satu sama lain.**

Ini poin terpenting dalam review ini, jadi izinkan saya lambatkan.

Dalam contoh Anda:

```
Penjualan Barang     → Pendapatan Barang Dagang
Pembayaran Tunai     → Kas
PPN Keluaran         → Hutang PPN
Pembulatan           → Pendapatan/Beban Pembulatan
```

Kolom kiri adalah **event**. Kolom kanan adalah **akun untuk satu peran (leg) di dalam event itu**. Peran itu tetap ada — Anda hanya tidak menamainya, karena setiap event di daftar Anda kebetulan hanya menampakkan **satu leg**.

Perhatikan: "Penjualan Barang → Pendapatan Barang Dagang" hanya menyebut sisi **kredit**. Sisi debitnya dari mana? Dari event lain: "Pembayaran Tunai → Kas". Ini bukan kelemahan cara berpikir Anda — ini justru **model yang benar dan canggih**, dan namanya ada di literatur: setiap business event menyumbang **posting legs** ke dalam satu dokumen, dan **seluruh dokumen** yang harus balance, bukan tiap event.

Sebuah order POS:

```
Event: Penjualan Barang      →  K  Pendapatan Barang Dagang     100.000
Event: Diskon Penjualan      →  D  Diskon Penjualan (kontra)     10.000
Event: Service Charge        →  K  Pendapatan Service Charge      5.000
Event: PPN Keluaran          →  K  Hutang PPN                    10.450
Event: Pembulatan            →  K  Pendapatan Pembulatan             50
Event: Pembayaran Tunai      →  D  Kas                          105.500
Event: HPP                   →  D  HPP                           60.000
Event: Pengurangan Persediaan→  K  Persediaan                    60.000
                                                    ─────────────────────
                                         Σ Debit = Σ Kredit  ✔ (invarian)
```

Ini indah, dan mesin yang bisa mencetak tabel di atas dari konfigurasi **akan** memenuhi seluruh daftar 16 event Anda. Tapi lihat apa yang dibutuhkan tiap baris, dan bandingkan dengan apa yang disimpan spec sekarang:

| Yang dibutuhkan | Disimpan spec 2026-07-14? |
|---|---|
| Akun | ya (`akun`) |
| Arah D/K | **tidak** — di-hardcode di Python |
| Sumber nilai | **tidak** — di-hardcode di Python |
| Boleh nol/berapa baris | **tidak** |
| Invarian balance | **tidak** — implisit, tidak dijaga |

**Jadi jawaban atas §2: Business Event adalah unit organisasi yang benar (adopsi), tapi ia tidak menggantikan role — ia mengandung role.** Yang harus diganti bukan "role", melainkan `transaction_type` yang anemik.

Dan soal `Role` yang generik (`revenue`, `offset`, `tax`, `inventory`) — **kritik Anda tepat, tapi bukan karena rolenya salah konsep, melainkan karena nama role itu dipakai lintas event.** Perbaikannya: role dinamai **lokal terhadap event**, dengan label bahasa bisnis:

```
Event 'penjualan_jasa':
    leg 'pendapatan'  label "Pendapatan Jasa"       K  required
Event 'retur_penjualan':
    leg 'kontra'      label "Retur Penjualan"       D  required
    leg 'pengembalian' label "Kas/Hutang Refund"    K  required
Event 'tips':
    leg 'liabilitas'  label "Hutang Tips"           K  required
```

Admin **tidak pernah melihat kata `leg` atau `offset`**. Ia melihat "Retur Penjualan → [pilih akun]". Bahasa bisnis di UI (permintaan Anda §6) tercapai **tanpa membuang struktur yang dibutuhkan mesin** untuk benar-benar menjurnal. Anda dapat keduanya. Membuang role demi bahasa bisnis akan membuang justru informasi yang membuat otomasi mungkin.

Satu koreksi akuntansi pada daftar Anda: **Refund** dan **Retur Penjualan** benar Anda pisahkan (retur = pembalikan pendapatan + barang kembali; refund = arus kas keluar). Tapi "Refund → Hutang Refund" hanya benar bila uang belum dibayarkan saat itu juga. Refund tunai di kasir mengkredit **Kas**, bukan Hutang Refund. Ini contoh nyata kenapa satu event butuh **beberapa leg dan beberapa varian**, bukan satu akun.

### §3 Separation of Concerns — sudah cukup jelas?

**Prinsip Anda benar dan harus ditulis besar-besar di spec.** Buy 1 Get 1, happy hour, voucher, loyalty adalah **milik POS**. Transaction Mapping hanya menentukan konsekuensi akuntansi setelah POS memutuskan apa yang terjadi. Setuju 100%.

Tapi spec 2026-07-14 **belum menyatakan batas ini sama sekali** — ia tidak punya konsep "POS menghasilkan transaksi bisnis, lalu engine menentukan konsekuensi". Yang ada hanya `resolve_account(...)` yang dipanggil dari dalam kode modul. Batasnya belum dilanggar hanya karena enginenya belum melakukan apa-apa.

Dan justru di sinilah bahaya laten yang harus dijaga sejak sekarang, karena godaannya besar begitu enginenya hidup:

> **Engine tidak boleh tahu apa itu "Buy 1 Get 1". Engine hanya boleh menerima: "event `diskon_penjualan` terjadi, nilai 10.000, konteks: outlet X, item Y".**

POS boleh punya 50 jenis promo; bagi engine, semuanya kemungkinan besar bermuara ke event yang sama (`diskon_penjualan`) — atau ke beberapa event kalau akuntansinya memang berbeda (diskon item vs diskon nota vs voucher pihak ketiga yang sebenarnya **piutang ke penerbit voucher**, bukan diskon sama sekali).

**Kontrak yang harus dikunci di spec:** modul mengirim **event payload** — event code, nilai, konteks — dan **tidak pernah** menyebut akun, debit, atau kredit. Engine mengembalikan baris jurnal. Kalau ada satu saja `if promo_type == 'bogo'` di dalam engine, arsitekturnya sudah bocor.

### §4 Apakah mapping selalu ke Account?

**Tidak, tapi jawabannya bukan "bikin tabel mapping generik ke sembarang objek".** Daftar Anda perlu dipisah tiga, karena ketiganya berperilaku sangat berbeda dan menggabungkannya adalah jebakan desain klasik:

**(a) Yang sebenarnya adalah *scope* (input pemilih akun), bukan target mapping:**
Outlet, Warehouse, Sales Channel, Business Unit, Customer Group, Payment Method.
Ini menjawab *"akun mana yang dipakai **kalau** transaksinya di outlet A / dibayar QRIS / channel GoFood"*. Mereka masuk ke **kunci** resolver, bukan ke nilainya. Ini sudah terbukti dibutuhkan hari ini — `PaymentMethod.payment_account` adalah persis ini.

**(b) Yang sebenarnya adalah *dimensi* pada baris jurnal, bukan mapping:**
Cost Center, Department, Project, Segment.
Ini bukan "akun mana", melainkan **atribut tambahan pada baris jurnal** untuk pelaporan multi-dimensi. Tempatnya di `JurnalDetail` (kolom nullable, atau tabel dimensi), dan nilainya dibawa oleh event payload. Memodelkannya sebagai "mapping" adalah salah kamar — dan salah kamar yang mahal, karena akan menyandera desain resolver Anda selamanya.

**(c) Yang memang aturan tersendiri (bukan akun):**
Tax Profile, Currency.
Tax Profile sudah ada rumahnya (`TarifPajak`). Currency adalah masalah tersendiri yang jauh lebih besar dari mapping (revaluasi, selisih kurs) — jangan diseret ke sini.

**Kesimpulan §4:** Anda **tidak** butuh mapping generik ke sembarang objek. Anda butuh: **(a) scope chain yang extensible**, **(b) dimensi pada baris jurnal**, dan **(c) engine yang outputnya adalah baris jurnal, bukan sekadar akun.** Ketiganya konkret, ber-FK, ber-integritas, dan tidak butuh EAV. Alternatif "target_content_type + target_id" saya bahas dan tolak di §7.

### §5 Apakah UI per modul harus berbeda?

**Beda tampilan: ya. Beda mesin: tidak. Beda tabel: tidak.**

Registry mendeklarasikan bentuk; satu framework UI merendernya. Modul menyumbang: grup event, urutan, label, ikon, help text, preset. Tidak ada satupun modul yang boleh menulis halaman setting mapping-nya sendiri dari nol — begitu boleh, dalam 18 bulan Anda punya 11 halaman yang berperilaku beda, dan audit trail yang bocor di 7 di antaranya.

Kebutuhan berbeda yang Anda sebut (Pembelian: ongkos angkut, PPN masukan, retur; Piutang: denda, bunga, write-off; Aset Tetap: perolehan, penyusutan, revaluasi) — semuanya **event dengan leg-nya masing-masing**. Tidak satupun butuh struktur tabel baru. Itu justru bukti kekuatan model event-leg, bukan bukti butuh 11 struktur.

### §6 Business-first configuration

**Setuju, dan ini murni masalah presentasi — yang berarti Anda bisa mendapatkannya tanpa membayar apapun secara arsitektural**, asalkan registry menyimpan `label` bahasa bisnis (sudah ada di spec) **dan** event dinamai dalam bahasa bisnis (belum ada).

Yang perlu ditambahkan agar benar-benar terasa business-first, dan tidak ada di spec sekarang:

- Preview jurnal langsung di halaman setting: *"Dengan konfigurasi ini, penjualan tunai Rp100.000 akan menghasilkan: D Kas 111.000 / K Pendapatan 100.000 / K Hutang PPN 11.000"*. Ini satu-satunya cara admin non-akuntan bisa memverifikasi konfigurasinya benar. Menurut saya ini fitur paling bernilai di seluruh desain, dan **hanya mungkin kalau engine tahu arah dan nilai** — mustahil dibangun di atas spec 2026-07-14.
- Preset per jenis usaha (F&B, Retail, Jasa) — lihat §7.

### §7 Scalability: 100+ event di POS

Dengan spec sekarang: **matriks datar 100 baris × N role, tanpa grouping, tanpa search, tanpa preset, di satu halaman.** Tidak terpakai. Template Tahap 0 (`templates/mapping/settings.html`) merender nested `{% for %}` seluruh registry tanpa paginasi — ini akan roboh jauh sebelum 100 event.

Yang benar-benar dibutuhkan pada skala itu, diurut berdasarkan nilai:

1. **Preset / template per jenis usaha** — paling penting. Admin baru tidak boleh dihadapkan 100 dropdown kosong. Ia memilih "F&B", 90% terisi, ia menyesuaikan sisanya. Ini juga membuat onboarding merchant baru hitungan menit, bukan hari.
2. **Grouping & kategori** — event dikelompokkan (Penjualan / Pembayaran / Pajak / Penyesuaian / Persediaan), deklaratif dari registry.
3. **Inheritance lewat scope chain** — bukan lewat hierarki event. Outlet mewarisi merchant, merchant mewarisi global. Admin outlet hanya melihat yang di-override. Ini **sudah** bagaimana POS bekerja hari ini; jangan dibuang.
4. **Filter "belum di-set"** + indikator kelengkapan per modul.
5. Search.

Yang **tidak** dibutuhkan: hierarchical transaction type (event mewarisi event). Kelihatan elegan, praktiknya membingungkan — ketika `penjualan_barang_promo` mewarisi `penjualan_barang` lalu meng-override satu leg, tidak ada seorangpun yang bisa menjawab "akun apa yang sebenarnya dipakai" tanpa menelusuri pohon. Inheritance sudah cukup lewat scope chain (dimensi vertikal). Jangan tambahkan dimensi kedua.

### §8 Haruskah berkembang jadi "Business Event Engine"?

**Setengah ya — dan bagian "tidak"-nya penting, karena di sinilah proyek seperti ini biasanya mati.**

**Ya:** Business Event adalah konsep pengorganisasian yang benar, dan Account Mapping memang seharusnya menjadi *salah satu* konfigurasi milik event, bukan pusat semesta. Intuisi Anda benar, dan modul `pajak` sudah membuktikannya secara empiris di kode Anda sendiri (§1.2).

**Tidak:** membangun Tax Rule + Inventory Rule + Cost Center Rule + Approval Rule + Loyalty Rule + Notification Rule + Workflow Rule **sekarang, dalam satu engine**, adalah bagaimana proyek platform mati. Alasannya konkret, bukan retoris:

- **Approval Rule dan Workflow Rule bukan konsekuensi event — mereka mendahului event.** Approval terjadi *sebelum* transaksi sah; posting terjadi *sesudah*. Menggabungkan keduanya dalam satu "engine" mencampur dua fase siklus hidup yang berbeda dan akan melahirkan state machine yang tidak bisa dipahami siapapun.
- **Notification Rule adalah side effect, bukan konsekuensi akuntansi.** Ia tidak boleh punya kekuatan untuk menggagalkan jurnal, dan jurnal tidak boleh menunggu notifikasi. Beda transactional boundary → beda mesin.
- **Loyalty Rule adalah business rule POS** — yang Anda sendiri, dengan benar, sudah letakkan di luar batas engine di §3. Memasukkannya kembali di §8 adalah kontradiksi. (Konsekuensi akuntansi dari loyalty — "Hutang Poin Loyalty" — **iya** milik posting engine. Aturan *kapan poin diberikan* tidak.)
- **Tax Rule sudah punya rumah** (`TarifPajak`) yang berfungsi.

Yang benar-benar mengikat semuanya bukanlah "satu engine besar", melainkan **satu registry event bersama (shared spine)**. Event didefinisikan sekali. Setiap concern menempel padanya lewat tabelnya sendiri yang konkret, dengan kunci yang sama `(event, scope)`:

```
                    Business Event Registry  ← satu-satunya definisi event
                              │
        ┌────────────┬────────┴────────┬──────────────┐
   PostingRule    TaxRule         (nanti)         (nanti)
   [BANGUN INI]   [sudah ada,      DimensionRule   ApprovalRule
                   tinggal          — kalau         — kalau
                   didaftarkan]     terbukti        terbukti
                                    perlu           perlu
```

Ini memberi Anda **extensibility tanpa membangun apapun yang belum terbukti dibutuhkan**. Menambah rule type baru di masa depan = tabel baru + presenter baru, **tanpa migrasi** pada yang sudah ada, karena spine-nya tidak berubah. Itulah definisi fondasi yang kuat — bukan "satu tabel yang bisa menyimpan apa saja".

**Nama:** `Posting Engine` (atau `Transaction Engine`). Bukan `Account Mapping Engine` (terlalu sempit — hanya memilih akun) dan bukan `Business Event Engine` (terlalu luas — menjanjikan workflow/approval/notifikasi yang sengaja tidak Anda bangun, dan nama yang menjanjikan terlalu banyak akan menarik scope creep seperti magnet).

---

## 3. Rekomendasi desain

### 3.1 Model konseptual

```
BusinessEvent  (registry, di kode)
    code             -- GLOBAL & unik; ini satu-satunya kunci (lihat §1.4)
    label            -- bahasa bisnis, tampil ke admin
    group            -- label pengelompokan UI ('Aset Tetap'), BUKAN nama app Django;
                     -- event 'perolehan_aset' dipancarkan purchase, tapi grup-nya 'Aset Tetap'
    emitted_by       -- informasional saja (untuk developer), tidak masuk kunci
    context_schema   -- nilai apa yang wajib dikirim modul (mis. 'amount', 'cogs')
    legs: [ PostingLeg ]

PostingLeg  (registry, di kode)   -- inilah "role", tapi tidak anemik
    code, label            -- label = bahasa bisnis, tampil ke admin
    direction              -- DEBIT | CREDIT | SIGNED
    amount_source          -- key ke context_schema, ATAU fungsi terdaftar
                           -- mis. 'fifo_cost' (§7.3) -- nilai tidak boleh diketik user
    account_source         -- STRATEGI resolusi (lihat 3.3)  ← krusial
    scope_ref              -- scope mana yang me-resolve akun leg ini:
                           -- 'default' | 'asal' | 'tujuan'   (§7.1, mutasi antar cabang)
    skip_if_zero           -- leg bernilai nol DIHILANGKAN, bukan ditulis (§7.2)
    required
    allowed_kategori       -- tuple, bukan str

    -- Untuk direction = SIGNED: DUA slot akun, bukan satu akun dua arah (§7.2).
    -- Laba (4.x, kredit) dan Rugi (5.x, debit) adalah AKUN BERBEDA.
    account_if_credit      -- Role, dipakai saat nilai positif
    account_if_debit       -- Role, dipakai saat nilai negatif
```

Berlaku untuk: Laba/Rugi Pelepasan Aset, Pembulatan, Selisih Kas (over/short).

Kalimat yang harus benar setelah perubahan ini:

> **Modul mengirim event + nilai + konteks. Engine mengembalikan baris jurnal yang balance. Modul tidak pernah menyebut akun, debit, atau kredit.**

### 3.2 Scope sebagai rantai, bukan satu FK

Ganti kolom `entitas_bisnis` (nullable) dengan:

```
PostingRuleAccount
    event, leg                  -- pasangan dari registry; TANPA 'module' (§1.4)
    scope_type                  -- 'global' | 'entitas_bisnis' | 'outlet' | 'payment_method' | ...
    scope_id                    -- nullable untuk 'global'
    specificity                 -- int; resolver ambil match dengan specificity tertinggi
    akun                        -- FK, PROTECT
```

Resolusi = ambil semua baris yang cocok dengan konteks, pilih `specificity` tertinggi.

**Ini yang membuat POS tidak lagi jadi warga kelas dua.** Cascade Lv1→Lv3 dan `PaymentMethod.payment_account` yang sudah berjalan hari ini bisa dipetakan **tanpa kehilangan kemampuan** — dan `scope_type` baru (warehouse, sales channel, customer group) bisa ditambah **tanpa migrasi skema**, hanya menambah konstanta + specificity.

Bandingkan dengan spec sekarang, yang untuk mendukung outlet saja butuh kolom baru + migrasi + perubahan resolver + perubahan UI. Inilah perbedaan antara "generik" dan "extensible". Spec 2026-07-14 generik tapi tidak extensible; ia bisa menyimpan apa saja asal bentuknya persis `(module, tt, role, EB)`.

### 3.3 `account_source` — strategi, bukan selalu akun tetap

Ini temuan yang paling mudah terlewat, dan **paling merusak kalau salah**.

Akun HPP dan Persediaan **tidak boleh** datang dari mapping global. Ia harus datang dari **item master** (`item.coa_account` — sudah dipakai hari ini di `process_sales_fifo`: `si.inventory_account_id = si.item.coa_account_id`). Kalau engine memaksa semua akun berasal dari tabel mapping, Anda akan **merusak akuntansi persediaan** — semua item bermuara ke satu akun persediaan, dan pelacakan persediaan per kategori hancur. Ini bukan risiko teoretis; ini akan langsung terjadi pada hari POS dimigrasikan.

Maka setiap leg mendeklarasikan **dari mana akunnya berasal**:

| `account_source` | Contoh leg |
|---|---|
| `RULE` (dari tabel mapping) | Pendapatan, PPN Keluaran, Service Charge, Tips, Pembulatan |
| `FROM_ITEM` (field di item master) | Persediaan, HPP |
| `FROM_CONTEXT` (dibawa event payload) | Kas/Bank dari `PaymentMethod` terpilih |
| `FROM_PARTNER` (customer/supplier) | Piutang Usaha per customer group |

Tanpa ini, engine hanya cocok untuk modul-modul mudah (Ekuitas, Aset Tetap) — dan akan patah persis di POS, Persediaan, dan Piutang, yaitu modul-modul yang paling Anda butuhkan.

### 3.4 Invarian yang dijaga engine

1. **Balance.** Σ debit = Σ kredit per dokumen. Ditolak di level engine, bukan dipercayakan ke kode modul. Hari ini tidak ada yang menjaga ini — `create_sales_automated_journals` menulis baris tanpa pernah memverifikasi totalnya.
2. **Fail loud.** Leg `required` tanpa akun → error jelas, jangan pernah menjurnal separuh.
2b. **Nol baris adalah hasil yang sah.** Event boleh menghasilkan nol baris jurnal (mutasi antar cabang dengan akun persediaan yang sama, §7.1). Jangan perlakukan sebagai error — tapi tetap catat bahwa event-nya terjadi.
2c. **Satu pintu untuk pemilihan akun, bukan untuk penulisan jurnal.** Modul tetap boleh menulis `JurnalDetail` sendiri; yang dilarang adalah mengambil akun dari luar resolver (magic string / FK config baru). Balance dijaga saat `JurnalHeader` di-post, bukan dengan memusatkan penulisan baris (§7.4).
3. **Idempotent + reversible.** Setiap posting membawa `source_type`/`source_id` (pola ini sudah benar di `PajakTransaksi`), sehingga void/refund adalah pembalikan yang dapat dilacak, bukan penghapusan.
4. **Auditable.** Perubahan mapping punya `effective_date` + riwayat. Jurnal bulan lalu tidak boleh berubah artinya karena admin mengganti dropdown hari ini. **Spec sekarang tidak punya ini sama sekali** — `update_or_create` menimpa baris di tempat. Untuk sistem akuntansi, ini cacat serius yang berdiri sendiri, terlepas dari seluruh perdebatan event-vs-role.

---

## 4. Rollout yang saya rekomendasikan

Prinsip strangler + fallback di spec 2026-07-14 **sudah benar** — pertahankan. Yang saya ubah adalah urutan dan pilihan pilotnya.

- **Tahap 0 — Spine.** Registry event/leg, `PostingRuleAccount` dengan scope chain, resolver dengan `account_source`, poster yang membentuk `JurnalDetail` + menegakkan balance. Nol pemanggil produksi.
- **Tahap 1 — Pilot: Penyusutan Aset Tetap, bukan Ekuitas.**
  Spec memilih Ekuitas karena "risiko rendah". Tapi Ekuitas hanya punya **satu leg** (`akun_modal`, sisi debitnya per-record) — ia **tidak akan menguji satupun bagian sulit** dari engine: tidak ada balance multi-leg, tidak ada scope chain, tidak ada `account_source` selain `RULE`. Pilot yang tidak bisa gagal tidak mengajarkan apapun.
  Penyusutan adalah pilot yang jauh lebih baik: dua leg, balance nyata, magic string yang siap dijadikan fallback, nilai dari skedul (menguji `amount_source`), dan tidak menyentuh alur kasir. **Dan cakupannya terkurung rapat**: seperti dibongkar di §1.4, penyusutan adalah **satu-satunya** jurnal yang dimiliki `aset_tetap` — satu fungsi (`process_depreciation`), tidak ada modul lain yang bergantung padanya. Perolehan aset **bukan** bagian dari pilot ini; ia milik alur Purchase dan tidak disentuh.
- **Tahap 2 — POS: satu event baru yang belum pernah ada.**
  Jangan mulai dengan memigrasikan penjualan (berisiko, tidak ada hasil terlihat). Mulai dengan **Service Charge** atau **Pembulatan** — event yang hari ini **belum dijurnal sama sekali**. Nol risiko regresi (tidak ada perilaku lama untuk dirusak), dan langsung membuktikan tesis utama: engine ini bisa menambah business event **tanpa mengubah kode posting**. Kalau ini berhasil, seluruh arsitektur terbukti. Kalau gagal, Anda tahu sebelum menyentuh apapun yang menghasilkan uang.
- **Tahap 3 — POS: migrasikan penjualan + pembayaran** ke engine, dengan cascade existing sebagai scope chain, fallback aktif, uji kesetaraan jurnal.
- **Tahap 4 — Piutang, Pembelian, dan kebijakan modul baru.**
- **STT:** tetap legacy, tapi **jangan janjikan selamanya**. Setelah Sales/Purchase pindah, STT menjadi mesin kelima yang menganggur. Jadwalkan pencabutannya, atau Anda hanya menambah satu sistem lagi ke empat yang sudah ada.

---

## 5. Yang saya rekomendasikan untuk TIDAK dibangun

Ini sama pentingnya dengan rekomendasi di atas.

| Ide | Kenapa tidak |
|---|---|
| Mapping generik `target_content_type` + `target_id` | Membunuh FK/PROTECT, membunuh dropdown terfilter, membunuh validasi. Anda menukar type safety demi fleksibilitas yang tidak Anda butuhkan (§4 menunjukkan daftar Anda sebenarnya adalah scope + dimensi, bukan target). Ini adalah EAV, dan EAV di jantung modul akuntansi adalah keputusan yang tidak bisa dibatalkan. |
| Approval / Workflow / Notification Rule dalam engine | Beda fase siklus hidup, beda transactional boundary. Bangun terpisah, ikat lewat event registry. |
| Loyalty / Promo Rule dalam engine | Milik POS — batas yang Anda sendiri tetapkan dengan benar di §3. Hanya *konsekuensi akuntansinya* yang masuk engine. |
| Hierarchical / inheritable transaction type | Inheritance sudah lewat scope chain. Dimensi warisan kedua = tidak terlacak. |
| Rule berbasis DSL / scripting | Terdengar powerful; pada praktiknya menjadi bahasa pemrograman kedua yang tidak punya debugger, tidak punya test, dan hanya dipahami satu orang. |

---

## 6. Keputusan yang perlu Anda ambil

1. **Scope engine.** Posting Engine (rekomendasi saya) vs Account Mapping Engine (spec sekarang) vs Business Event Engine penuh (terlalu luas).
2. **Nasib Tahap 0 yang sudah direncanakan.** Plan `2026-07-14-account-mapping-engine-tahap0.md` masih ~70% dapat dipakai ulang (app scaffold, registry, permission, pola AJAX). Yang berubah: `AccountMapping` → `PostingRuleAccount` (scope chain), `Role` → `PostingLeg` (direction + amount_source + account_source), plus komponen baru: poster + balance check. Karena Tahap 0 punya **nol pemanggil produksi**, mengubahnya sekarang **gratis** — dan ini alasan kuat untuk memutuskan sebelum satu baris pun ditulis.
3. **Nasib STT** — legacy selamanya, atau dijadwalkan dicabut.
4. **Effective-dated mapping** — apakah masuk v1. Rekomendasi saya: ya, karena menambahkannya belakangan berarti bermigrasi di atas data jurnal yang sudah hidup.

---

## 7. Stress test: fitur lanjutan Aset Tetap & Persediaan

Ditambahkan 2026-07-15 setelah klarifikasi. Fondasi hanya terbukti kalau ia menahan fitur yang **belum** dibangun — bukan hanya yang sudah ada. Tiga fitur yang direncanakan diuji ke desain §3.

**Parameter yang sudah dikunci pemilik produk:**
- **Cabang = EntitasBisnisLv2/Lv3 di dalam satu EntitasBisnis.** Satu badan usaha, satu laporan keuangan.
- Mutasi bernilai harga pokok; markup (bila ada) adalah fitur di luar scope engine ini.
- Alasan penghapusan **memengaruhi** akun beban.

### 7.1 Mutasi antar cabang — desain bertahan, tapi scope chain jadi syarat mutlak

Karena cabang berada di dalam **satu** entitas hukum, mutasi **tidak** melahirkan jurnal ganda antar entitas dan **tidak** butuh akun Piutang/Hutang Antar Cabang. Invarian "satu event → satu jurnal yang balance" (§3.4) **tetap utuh**. Ini menghapus risiko rework terbesar.

Tapi ia mengunci satu hal, dan ini pembunuh bagi spec 2026-07-14:

> Scope **wajib** turun sampai Lv2/Lv3. Dengan scope = satu FK `entitas_bisnis`, mutasi antar cabang **tidak dapat dipetakan sama sekali** — engine tidak punya cara membedakan Persediaan Cabang Bandung dari Persediaan Cabang Jakarta.

Dua kemungkinan konfigurasi, dan **engine harus menangani keduanya tanpa perubahan kode**:

| Konfigurasi CoA | Jurnal mutasi | Konsekuensi desain |
|---|---|---|
| Satu akun persediaan untuk semua cabang | **nol baris jurnal** — hanya kuantitas & lokasi yang berpindah | Engine **harus mengizinkan event sah menghasilkan nol baris.** Jangan perlakukan sebagai error. |
| Akun persediaan per cabang | D Persediaan (cabang tujuan) / K Persediaan (cabang asal) | Dua leg dengan **akun yang di-resolve dari scope berbeda**: satu dari scope asal, satu dari scope tujuan. |

Baris kedua menuntut amandemen desain: leg boleh mendeklarasikan **scope mana yang dipakai untuk me-resolve akunnya** (`scope_ref: 'asal' | 'tujuan' | 'default'`). Tanpa ini, kedua leg akan me-resolve ke akun yang sama dan jurnalnya menjadi D/K pada akun yang identik — nol efek, dan salah.

**Peringatan akuntansi (di luar scope engine, tapi harus tercatat):** di dalam satu badan usaha, **markup antar cabang tidak boleh diakui sebagai pendapatan di GL** — entitas tidak dapat memperoleh laba dari dirinya sendiri. Markup masuk akun pendapatan = laba fiktif di laporan laba rugi + persediaan cabang tujuan overstated. Markup antar cabang adalah alat *transfer pricing untuk penilaian kinerja*, tempatnya di lapisan **pelaporan manajemen**, bukan di jurnal. Jurnal tetap at cost. (Bila kelak cabang menjadi PT terpisah, barulah akun antar cabang + eliminasi konsolidasi relevan — dan itu proyek tersendiri.)

Untuk **Aset Tetap**, mutasi antar cabang memindahkan **dua** nilai sekaligus (harga perolehan **dan** akumulasi penyusutan), sehingga event yang sama menghasilkan hingga 4 leg. Skedul penyusutan berlanjut, tidak di-reset. Ini menguji multi-leg + `scope_ref` sekaligus — kandidat kuat sebagai event kedua yang dibangun di atas engine.

### 7.2 Penghapusan Aset Tetap — menemukan cacat di desain §3.1 saya

Penghapusan (bukan lewat penjualan) menghasilkan:

```
D  Akumulasi Penyusutan        sebesar akumulasi s/d tanggal hapus
K  Aset Tetap                  sebesar harga perolehan
D  Rugi Penghapusan Aset       sebesar nilai buku tersisa      ← hanya jika nilai buku > 0
```

Dua kebutuhan yang **tidak tercakup** desain saya di §3.1:

1. **Conditional leg.** Aset yang sudah habis disusutkan → nilai buku nol → leg rugi **tidak boleh muncul** (baris bernilai nol adalah sampah di buku besar). Aset baru → akumulasi nol → leg akumulasi tidak muncul. Engine harus **menghilangkan leg bernilai nol**, bukan memaksakannya.

2. **Leg bertanda butuh DUA akun, bukan sekadar dua arah.** Ini koreksi penting terhadap `direction: SIGNED` yang saya usulkan. Pada pelepasan **dengan** hasil penjualan, selisihnya bisa laba **atau** rugi — dan keduanya adalah **akun yang berbeda**, bukan akun sama dengan arah berbeda:
   - Laba Pelepasan Aset → akun **pendapatan** (4.x), sisi kredit
   - Rugi Pelepasan Aset → akun **beban** (5.x), sisi debit

   Maka leg bertanda mendeklarasikan **dua slot akun**:

   ```
   PostingLeg('selisih_pelepasan',
       direction    = SIGNED,
       amount_source= 'proceeds_minus_book_value',
       account_if_credit = Role('laba_pelepasan', kategori='pendapatan'),   # nilai positif
       account_if_debit  = Role('rugi_pelepasan', kategori='beban'),        # nilai negatif
   )
   ```

   Pola identik berlaku untuk **Pembulatan** dan **Selisih Kas (over/short)** di POS — yang Anda sendiri tulis sebagai "Pendapatan/Pengeluaran Pembulatan". Jadi ini bukan kasus tepi aset tetap; ini pola yang berulang, dan spec 2026-07-14 (`role → satu akun`) **tidak bisa menyatakannya sama sekali**.

### 7.3 Penghapusan Persediaan — membuktikan scope chain, dan menemukan `amount_source` derived

```
D  Beban Kerugian Persediaan   ← dari mapping, di-scope oleh ALASAN
K  Persediaan                  ← dari item master (item.coa_account), BUKAN dari mapping
```

Dua konfirmasi penting:

**Alasan sebagai scope, bukan sebagai event.** Karena alasan memengaruhi akun beban, godaannya adalah membuat event terpisah (`penghapusan_rusak`, `penghapusan_hilang`, `penghapusan_expired`, …) — dan itulah bagaimana registry membengkak jadi 100+ event yang Anda khawatirkan di §7 pertanyaan. Dengan scope chain, cukup **satu** event dan **satu** leg:

```
Event 'penghapusan_persediaan', leg 'beban':
    scope global           → Beban Kerugian Persediaan
    scope alasan=rusak     → Beban Barang Rusak
    scope alasan=hilang    → Beban Kehilangan Persediaan
    scope alasan=expired   → Beban Barang Kadaluarsa
    scope alasan=hilang + entitas_bisnis=X  → (override khusus EB X)
```

Satu event, N pemetaan, nol event baru, nol migrasi. **Inilah jawaban struktural atas kekhawatiran "100+ business event"**: sebagian besar ledakan event yang Anda bayangkan sebenarnya adalah ledakan **scope**, dan scope chain menyerapnya secara mendatar. Registry tetap kecil dan terbaca; yang bertambah adalah baris data, bukan definisi.

**`amount_source` harus boleh *derived*, bukan hanya dibawa payload.** Nilai persediaan yang dihapus **bukan input user** — ia harus berasal dari FIFO (`consume_fifo`, sudah ada dan dipakai `process_sales_fifo`). Kalau admin boleh mengetik nilainya, buku persediaan dan buku besar akan menyimpang, dan itu tidak dapat diperbaiki tanpa audit. Jadi `amount_source` punya dua bentuk: dari payload, atau dari fungsi terdaftar (`fifo_cost`) yang dipanggil engine.

Catatan pajak yang perlu dibawa ke modul `pajak` (bukan ke engine): atas persediaan yang **hilang/susut**, PPN masukan yang telah dikreditkan pada umumnya harus dikoreksi. Engine cukup memancarkan event dengan `alasan=hilang`; modul pajak yang menempel pada event yang sama (§8, shared spine) yang menanganinya. Ini contoh konkret pertama di mana spine bersama membayar dividen.

### 7.4 "Satu pintu" — yang mana yang harus satu pintu

**Revisi 2026-07-15 (koreksi atas rekomendasi awal reviewer).** Versi pertama dokumen ini menuntut agar poster menjadi **satu-satunya penulis `JurnalDetail`**, dan melarang 12 modul menulisnya sendiri. Itu over-reach: menuntut refactor besar lintas modul yang **tidak menghasilkan nilai apapun bagi user**, demi kemurnian arsitektur.

Tiga hal berbeda tercampur di situ, dan hanya satu yang benar-benar harus dipusatkan:

| Pertanyaan | Satu pintu? | Di mana |
|---|---|---|
| Siapa **memilih akun** | **Ya** — inti kebutuhan | Registry + resolver |
| Siapa **menulis** `JurnalDetail` | **Tidak** | Tetap di modul masing-masing |
| Siapa **menjamin balance** | Ya, tapi ringan | Penjaga saat `JurnalHeader` di-post |

Balance dapat ditegakkan **tanpa** memusatkan penulisan: validasi Σ debit = Σ kredit saat header di-post, siapapun yang membangun barisnya. Invarian akuntansi (§3.4) tetap didapat, refactor 12 modul tidak diperlukan.

**Yang tetap wajib satu pintu: pemilihan akun.** Tidak ada lagi magic string, tidak ada lagi FK akun config bertebaran. Modul boleh menulis jurnalnya sendiri — tapi akun yang ditulisnya **harus** berasal dari resolver.

### 7.5 Registry men-drive tiga hal, bukan satu

Kebutuhan sesungguhnya, dari pemilik produk:

> *User memilih jenis transaksi di modul → semua akun otomatis terisi → ia hanya mengisi data yang perlu. Tiap modul beda: ada yang 2 akun, 3 akun, 6 akun sesuai pilihannya.*

Agar itu mungkin, sistem harus tahu — **per jenis transaksi**:

- ada berapa leg (2 / 3 / 6, tergantung pilihan)
- leg mana yang akunnya **otomatis dari mapping**, dan mana yang **dipilih user per transaksi** (mis. `ModalDisetorDebit.akun` di Ekuitas — genuinely per-record)
- data apa yang **wajib diisi user** (nilai, qty, tanggal)
- leg mana yang **muncul/hilang tergantung pilihan** (ada PPN? ada ongkos angkut? ada retur?)

Itu persis isi registry (§3.1). Konsekuensinya, registry bukan hanya sumber halaman setting admin — **ia juga sumber form input transaksi di tiap modul**:

```
              Registry (jenis transaksi + leg-nya)
                              │
        ┌─────────────────────┼─────────────────────┐
   Halaman Setting       Form input modul        Resolver
   (admin isi akun       (field apa muncul,      (akun mana
    per leg)              akun mana auto-fill)    saat posting)
```

Inilah yang membuat "2 akun / 3 akun / 6 akun sesuai pilihan" menjadi **wajar dan deklaratif**, bukan kasus khusus per modul: jumlah leg adalah properti jenis transaksi, ditulis sekali, dibaca tiga konsumen. Modul tetap menulis `JurnalDetail`-nya sendiri — tapi dari akun yang sudah di-resolve, bukan dari magic string atau FK bertebaran.

**Konsekuensi yang diterima secara sadar:** karena modul tetap memegang penulisan jurnal, **menambah jenis transaksi baru tetap membutuhkan programmer** (entri registry + kode modul). Ini konsisten dengan Pendekatan A yang sudah dikunci di spec 2026-07-14 (definisi di kode, bukan oleh user), jadi bukan regresi. Tapi artinya admin **tidak** dapat menciptakan business event baru sendiri lewat UI. Bila kelak itu diinginkan, barulah poster terpusat menjadi wajib — **jangan dikejar sekarang**.

---

## 8. Model operasi: vendor multi-klien — membatalkan keputusan "Pendekatan A"

Ditambahkan 2026-07-15 setelah klarifikasi model bisnis.

**Fakta yang sebelumnya tidak diketahui reviewer:** yang mengkonfigurasi mapping adalah **superuser = pemilik aplikasi Naveda (vendor)**. Klien adalah Entitas Bisnis. Klien **tidak** menyentuh mapping sama sekali.

Ini membatalkan dasar keputusan yang dikunci di spec 2026-07-14:

> *"**Pendekatan A (registry deklaratif di kode)**, bukan B (role didefinisikan user via UI). … Ini mencegah 'beda persepsi' role antara kode dan UI."*

Pendekatan A dipilih untuk **melindungi user awam dari dirinya sendiri**. Tapi operatornya bukan user awam — ia vendor yang paham akuntansi, meng-onboard klien satu per satu, dan butuh menambah jenis transaksi **tanpa deploy** setiap kali klien baru punya kebutuhan berbeda. Perlindungan itu kini menjadi belenggu tanpa manfaat.

**Keputusan baru: Pendekatan C (hybrid).**

> **Kode menyediakan bahan (angka). Superuser meracik resep (baris jurnal) lewat UI.**

### 8.1 Apa yang boleh, dan tidak boleh, didefinisikan lewat UI

Batasnya bukan soal kehati-hatian — ini batas struktural. **Setiap baris jurnal butuh angka, dan angka harus datang dari suatu tempat.** "Service charge = subtotal × 5%" dan "HPP = biaya batch FIFO" dihitung oleh kode. Rumus tidak bisa diketik ke dropdown — kecuali dengan membangun DSL/scripting, yang sudah ditolak di §5.

| | Sumber |
|---|---|
| **Kode (programmer)** | Memancarkan event + **mengumumkan angka apa saja yang tersedia** (`subtotal`, `diskon`, `pajak`, `service_charge`, `tip`, `pembulatan`, `hpp`, `nilai_bayar`, …) |
| **UI (superuser)** | Menyusun jenis transaksi: **baris mana saja**, tiap baris memakai **angka yang mana**, **debit/kredit**, dan **akun apa** |

Contoh yang disusun sepenuhnya lewat UI, tanpa deploy:

```
Jenis Transaksi: "Penjualan Kasir F&B"
  angka: subtotal        K   → Pendapatan Barang Dagang
  angka: diskon          D   → Diskon Penjualan
  angka: service_charge  K   → Pendapatan Service Charge
  angka: pajak           K   → Hutang PPN
  angka: pembulatan     +/−  → Pend. Pembulatan / Beban Pembulatan
  angka: nilai_bayar     D   → (dari metode bayar)
  angka: hpp             D   → HPP
  angka: hpp             K   → (dari master item)
```

Klien retail tanpa service charge → hapus barisnya. Tanpa tips → tidak dipasang.

**Ini yang akhirnya membuka gembok service charge** (§1.1): angkanya **sudah ada** di kode (`effective_service_charge_pct()` sudah menghitungnya bertahun-tahun). Yang tidak pernah ada hanyalah **barisnya**. Begitu baris dapat dipasang lewat UI, masalahnya selesai — tanpa satu baris kode pun di modul.

Dropdown "angka" di UI **hanya menampilkan yang diumumkan modul**, sehingga tidak mungkin ada baris yang merujuk angka yang tidak ada. Inilah yang membuat Pendekatan C aman, sementara Pendekatan B yang murni (user bebas mendefinisikan apapun) tidak.

### 8.2 Konsekuensi yang harus diterima

**(a) Generator jurnal hardcoded harus dibongkar.** `create_sales_automated_journals` (dua blok tetap: HPP & Pendapatan) menjadi **perulangan yang membaca konfigurasi**. Modul **tetap** yang menulis `JurnalDetail` (sesuai §7.4) — tapi dengan "baca daftar baris, tulis satu per satu", bukan blok tetap. Pekerjaan nyata, tapi sekali saja, dan tanpa ini seluruh §8 tidak berfungsi.

**(b) Superuser kini dapat membuat pembukuan yang salah.** Itu harga dari kekuatan yang diminta. Tiga pengaman, dan ketiganya wajib:

- **Cek keseimbangan** (§3.4) — otomatis menangkap kesalahan tersering: ada angka yang tidak dipasangkan ke baris manapun. Kasir menagih service charge tapi barisnya lupa dipasang → jurnal tidak balance → ditolak, bukan diam-diam salah.
- **Preview jurnal di halaman setting** — *"penjualan tunai Rp100.000 → D Kas 111.000 / K Pendapatan 100.000 / K Hutang PPN 11.000"*. Fitur paling bernilai di seluruh desain; hanya mungkin karena engine tahu arah **dan** angka.
- **Riwayat bertanggal (effective-dated)** — kini **wajib**, bukan opsional (§3.4 poin 4). Superuser akan menyunting konfigurasi klien yang sedang berjalan; jurnal bulan lalu tidak boleh berubah artinya karena dropdown diganti hari ini.

**(c) Halaman ini superuser-only.** Spec 2026-07-14 menggantungnya pada permission `settings_view`/`settings_update` yang dapat diberikan ke user biasa — **terlalu longgar**. Klien EB tidak boleh melihatnya sama sekali (atau maksimal read-only).

### 8.3 Hadiah terbesarnya: onboarding klien

Struktur scope (§3.2) kini klop dengan model bisnis vendor:

```
Template Global / Preset  (milik vendor)     ← default untuk semua klien
    └── Klien A (EntitasBisnis)              ← override bila perlu
          └── Outlet A1 (Lv2/Lv3)            ← override bila perlu
```

Preset per jenis usaha (**F&B / Retail / Jasa**) — klien baru masuk, pilih preset, ~90% terisi, sesuaikan sisanya. Onboarding dari berhari-hari menjadi hitungan menit. Ini berhenti menjadi kerapian teknis dan menjadi **keunggulan komersial**.

---

## 9. Ringkasan satu paragraf

Desain 2026-07-14 memperbaiki *bagaimana akun dipilih*, padahal masalah sesungguhnya adalah *tidak ada mesin yang tahu baris jurnal apa yang harus lahir dari sebuah kejadian bisnis*. Karena itu ia terasa "terlalu generik" — ia generik pada dimensi yang salah: cukup lentur untuk menyimpan pasangan `(peran → akun)` apapun, tapi terlalu miskin untuk mencetak satupun jurnal baru tanpa menulis kode. Naikkan unit kerjanya dari *account* menjadi *posting line*, dari *transaction type* menjadi *business event*, dan dari *satu FK entitas bisnis* menjadi *scope chain*. Pertahankan disiplin yang sudah bagus di spec itu (registry deklaratif, resolver tunggal, strangler + fallback, admin-gated). Tolak godaan membangun Tax/Approval/Workflow/Notification Rule sekarang — ikat mereka nanti lewat satu registry event bersama. Hasilnya: sebuah fondasi yang bisa menambah business event baru — service charge, tips, pembulatan, event ke-101 — **tanpa migrasi dan tanpa menyentuh kode posting**, yang justru adalah definisi sebenarnya dari "fondasi ERP jangka panjang" yang Anda cari.
