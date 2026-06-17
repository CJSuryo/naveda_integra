# Desain: Rombak Modul Pendapatan — PSAK 72 / SAK Full
**Tanggal:** 2026-06-18  
**Standar Acuan:** PSAK 72 / PSAK 115 (Pendapatan dari Kontrak dengan Pelanggan)  
**Scope:** Implementasi SAK (PSAK 72) penuh. SAK EP dan SAK EMKM menyusul iterasi berikutnya.

---

## 1. Konteks & Latar Belakang

NIF adalah aplikasi POS + Akuntansi lengkap yang dikembangkan untuk jasa akuntan profesional. Modul Pendapatan saat ini sudah memiliki struktur dasar (Header → EB Group → Item, deferred revenue, recurring), tetapi belum sesuai PSAK 72 karena:

- Tidak ada konsep **Kewajiban Pelaksanaan (KP)** formal dengan alokasi harga
- Tidak ada pemisahan **pengakuan titik waktu vs sepanjang waktu**
- Tidak ada **Aset Kontrak** (contract asset)
- **Jurnal pajak tidak balance** (bug existing)
- Tidak ada field `standar_akuntansi` per transaksi

Modul Piutang sudah matang (PSAK 71, ECL, angsuran, approval) dan akan diintegrasikan langsung: setiap transaksi kredit dan konversi Aset Kontrak membuka form PiutangHeader dari modul Piutang.

### Pendekatan yang Dipilih
**Evolusi model existing** — bukan green field. Struktur `PendapatanHeader → PendapatanEntitasBisnis → PendapatanItem` dipertahankan, dengan rename dan enhancement signifikan pada layer Item dan layer Jadwal/Entry.

---

## 2. Arsitektur Model

### 2.1 `PendapatanHeader` — Perubahan Minor

Tambah satu field:

```python
standar_akuntansi = CharField(
    max_length=10, blank=True,
    choices=STANDAR_AKUNTANSI_CHOICES,
    verbose_name='Standar Akuntansi (Override)',
    help_text='Kosongkan untuk mengikuti standar entitas bisnis. Isi untuk override.',
)
```

Choices: `psak` | `sak_ep` | `sak_emkm` (konsisten dengan `EntitasBisnis` dan `PiutangHeader`).

Semua field lain (`transaction_id`, `tanggal`, `deskripsi`, `payment_type`, `status`, `source_type`, `source_sales`, `source_recurring`, `is_locked`, `created_by`) **tidak berubah**.

---

### 2.2 `PendapatanItem` → `KewajibabPelaksanaan`

Rename tabel via `Meta.db_table`. Ini adalah perubahan terbesar — model lama di-enhance menjadi entitas **Kewajiban Pelaksanaan (KP)** sesuai PSAK 72.

**Field dipertahankan:**
- `pendapatan_eb` FK
- `deskripsi_item`, `kategori`, `sub_transaction_type`
- `revenue_account`, `payment_account`
- Semua field pajak: `tax`, `tax_type`, `tax_account`, `tax_payment`, `tax_payment_account`

**Field diganti nama:**
- `jumlah_bruto` → `nilai_kontrak` *(harga terdaftar KP sebelum alokasi)*

**Field baru:**
```python
harga_jual_tersendiri = DecimalField(
    max_digits=19, decimal_places=4, null=True, blank=True,
    verbose_name='Harga Jual Tersendiri (SSP)',
    help_text='Berapa harga layanan ini jika dijual terpisah. Jika tidak tahu, isi sama dengan Nilai Kontrak.',
)
harga_dialokasikan = DecimalField(
    max_digits=19, decimal_places=4, null=True, blank=True,
    verbose_name='Harga Dialokasikan',
    help_text='Otomatis dihitung. Pendapatan yang benar-benar diakui setelah alokasi proporsional.',
)
recognition_type = CharField(
    max_length=20,
    choices=[('point_in_time', 'Titik Waktu'), ('over_time', 'Sepanjang Waktu')],
    default='point_in_time',
    verbose_name='Tipe Pengakuan',
    help_text='Titik Waktu: layanan selesai sekaligus. Sepanjang Waktu: layanan berlangsung beberapa periode.',
)
status_kp = CharField(
    max_length=20,
    choices=[
        ('belum_dimulai', 'Belum Dimulai'),
        ('sedang_berjalan', 'Sedang Berjalan'),
        ('selesai', 'Selesai'),
    ],
    default='belum_dimulai',
    verbose_name='Status KP',
)
jumlah_diakui = DecimalField(
    max_digits=19, decimal_places=4, default=0,
    verbose_name='Jumlah Diakui',
    help_text='Total pendapatan yang sudah diakui untuk KP ini (auto-update).',
)
```

**Field dihapus** (dipindah ke `JadwalPengakuan`):
- `is_deferred`, `deferred_account`, `recognition_account`
- `deferred_tanggal_mulai`, `deferred_tanggal_selesai`, `deferred_metode`

---

### 2.3 `DeferredRevenueSchedule` → `JadwalPengakuan`

Menggantikan model lama sepenuhnya. Mendukung semua tipe aliran kas dan metode pengukuran kemajuan.

```python
class JadwalPengakuan(Model):
    kp = OneToOneField('KewajibabPelaksanaan', on_delete=CASCADE, related_name='jadwal')

    # Akun
    recognition_account = FK(Akun, ...)           # Akun pendapatan yang dikredit saat pengakuan
    liabilitas_kontrak_acct = FK(Akun, null=True) # "Pendapatan Diterima di Muka" — untuk advance payment
    aset_kontrak_acct = FK(Akun, null=True)       # "Aset Kontrak / Piutang Kontrak" — untuk performance_first
    piutang_account = FK(Akun, null=True)         # Akun piutang — untuk periodic_billing & performance_first

    # Aliran & Metode
    tipe_aliran = CharField(choices=[
        ('advance_payment_cash', 'Bayar di Muka (Cash)'),
        ('periodic_billing',     'Tagih Per Periode'),
        ('performance_first',    'Kinerja Dulu Baru Tagih'),
    ])
    progress_method = CharField(choices=[
        ('straight_line',       'Garis Lurus (Rata per Bulan)'),
        ('percentage_manual',   'Persentase Penyelesaian Manual'),
        ('milestone',           'Berbasis Milestone / Tahapan'),
        ('cost_incurred',       'Berdasarkan Biaya Terjadi'),
    ])

    # Periode
    tanggal_mulai = DateField()
    tanggal_selesai = DateField(null=True, blank=True)  # nullable untuk milestone

    # Nilai
    jumlah_total = DecimalField(...)   # = harga_dialokasikan saat jadwal dibuat
    jumlah_diakui = DecimalField(default=0)

    # Khusus cost_incurred
    biaya_estimasi_total = DecimalField(null=True, blank=True,
        help_text='Total estimasi biaya proyek. Digunakan untuk menghitung % kemajuan dari biaya terjadi.')

    created_at = DateTimeField(auto_now_add=True)
```

---

### 2.4 `DeferredRevenueEntry` → `EntriPengakuan`

```python
class EntriPengakuan(Model):
    jadwal = FK(JadwalPengakuan, on_delete=CASCADE, related_name='entries')
    periode = DateField()                       # Hari pertama bulan/periode
    jumlah = DecimalField(...)                  # Jumlah yang diakui periode ini
    persentase_kemajuan = DecimalField(         # Kumulatif %, nullable
        null=True, blank=True,
        help_text='Total kemajuan dari awal kontrak (kumulatif, bukan per periode).',
    )
    deskripsi_milestone = TextField(blank=True) # Deskripsi tahapan yang selesai
    status = CharField(choices=[
        ('pending',    'Belum Diakui'),
        ('recognized', 'Sudah Diakui'),
        ('reversed',   'Dibalik'),
    ], default='pending')
    jurnal_header = FK(JurnalHeader, null=True, blank=True)
    recognized_at = DateTimeField(null=True, blank=True)
    recognized_by = FK(User, null=True, blank=True)

    class Meta:
        unique_together = ('jadwal', 'periode')
        ordering = ['periode']
```

---

### 2.5 `AsetKontrak` — Model Baru

Dibuat ketika kinerja mendahului penagihan (`tipe_aliran = performance_first`).

```python
class AsetKontrak(Model):
    kp = FK(KewajibabPelaksanaan, on_delete=CASCADE, related_name='aset_kontrak_entries')
    tanggal = DateField()
    jumlah_diakui = DecimalField(...)      # Total revenue yang sudah diakui tapi belum ditagihkan
    jumlah_dikonversi = DecimalField(default=0)  # Berapa yang sudah jadi Piutang
    aset_kontrak_account = FK(Akun, ...)
    status = CharField(choices=[
        ('aktif',             'Aktif'),
        ('dikonversi',        'Sudah Dikonversi ke Piutang'),
        ('dilunasi_langsung', 'Dilunasi Langsung'),
    ], default='aktif')
    piutang_header = FK(
        'piutang.PiutangHeader', null=True, blank=True,
        help_text='Diisi otomatis saat dikonversi ke Piutang.',
    )
    jurnal_pengakuan = FK(JurnalHeader, null=True, related_name='aset_kontrak_pengakuan')
    jurnal_konversi  = FK(JurnalHeader, null=True, related_name='aset_kontrak_konversi')
    catatan = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)

    @property
    def sisa(self):
        return self.jumlah_diakui - self.jumlah_dikonversi
```

**Saat konversi ke Piutang:** sistem membuka form `PiutangHeader` dari modul Piutang dengan nilai pre-filled. `source_pendapatan` = PendapatanHeader. Lifecycle collection (pembayaran, ECL, angsuran) sepenuhnya dikelola modul Piutang.

---

### 2.6 Model Tidak Berubah

- `PendapatanEntitasBisnis` — tidak ada perubahan
- `PendapatanEventLog` — tidak ada perubahan (tambah event types baru saja)
- `RecurringTemplate` — tidak ada perubahan

---

## 3. Logic Jurnal

Semua nilai menggunakan **`harga_dialokasikan`** per KP (bukan `nilai_kontrak`), sesuai PSAK 72 Langkah 4.

**Resolusi Cash vs Credit:**
- Untuk KP **point-in-time**: ditentukan oleh `PendapatanHeader.payment_type` (`cash` atau `credit`)
- Untuk KP **over-time**: ditentukan oleh `JadwalPengakuan.tipe_aliran` — header `payment_type` diabaikan untuk KP jenis ini

### Kasus 1 — Point-in-time, Cash
*Saat `confirm_pendapatan()`:*
```
Dr  Kas/Bank (payment_account)       harga_dialokasikan
    Cr  Pendapatan (revenue_account)     harga_dialokasikan
```

### Kasus 2 — Point-in-time, Credit
*Saat `confirm_pendapatan()`:*
```
Dr  Piutang (coa_piutang_account)    harga_dialokasikan
    Cr  Pendapatan (revenue_account)     harga_dialokasikan
```
→ Sistem membuka form `PiutangHeader` pre-filled. `source_pendapatan` = PendapatanHeader.

### Kasus 3 — Over-time, Bayar di Muka Cash (Contract Liability)
*Saat `confirm_pendapatan()`:*
```
Dr  Kas/Bank (payment_account)                   harga_dialokasikan
    Cr  Liabilitas Kontrak (liabilitas_kontrak_acct)  harga_dialokasikan
```
*Saat tiap `EntriPengakuan` diakui:*
```
Dr  Liabilitas Kontrak (liabilitas_kontrak_acct)  jumlah_periode
    Cr  Pendapatan (recognition_account)               jumlah_periode
```

### Kasus 4 — Over-time, Tagih Per Periode (Billing = Performance)
*Saat `confirm_pendapatan()`:* tidak ada jurnal.  
*Saat tiap `EntriPengakuan` diakui:*
```
Dr  Piutang (piutang_account)        jumlah_periode
    Cr  Pendapatan (recognition_account)  jumlah_periode
```
→ Sistem membuka form `PiutangHeader` pre-filled per periode.

### Kasus 5 — Over-time, Kinerja Dulu Baru Tagih (Contract Asset)
*Saat `confirm_pendapatan()`:* tidak ada jurnal.  
*Saat tiap `EntriPengakuan` diakui:*
```
Dr  Aset Kontrak (aset_kontrak_acct)   jumlah_periode
    Cr  Pendapatan (recognition_account)    jumlah_periode
```
*Saat konversi ke Piutang:*
```
Dr  Piutang (piutang_account)          jumlah_dikonversi
    Cr  Aset Kontrak (aset_kontrak_acct)   jumlah_dikonversi
```
→ Sistem membuka form `PiutangHeader` pre-filled. `AsetKontrak.piutang_header` diisi.  
→ Revenue tetap tercatat di modul Pendapatan; collection dikelola modul Piutang.

### Perbaikan Bug — Jurnal Pajak

**Sebelum (salah — tidak balance):**
```
Dr  Kas          jumlah_bruto
    Cr  Pendapatan   jumlah_bruto
    Cr  Pajak        tax           ← kredit ekstra tanpa debit
```

**PPN Keluaran** *(entity memungut PPN dari customer)*:
```
Dr  Kas/Piutang     harga_dialokasikan + nominal_ppn
    Cr  Pendapatan      harga_dialokasikan
    Cr  Hutang PPN      nominal_ppn
```

**PPh 23 / PPh 4(2)** *(customer memotong PPh sebelum bayar)*:
```
Dr  Kas/Piutang             harga_dialokasikan − nominal_pph
Dr  PPh Dibayar Dimuka      nominal_pph
    Cr  Pendapatan               harga_dialokasikan
```

### Void / Reversal
Semua jurnal terkait di-reverse (debit ↔ kredit). `AsetKontrak` dengan status `aktif` di-reverse. `PiutangHeader` yang masih `open` di-cancel.

---

## 4. Service Layer

### 4.1 Services Dimodifikasi

**`create_pendapatan_header()`**
Menerima list `kps` (menggantikan `items`). Setiap KP berisi: `deskripsi_item`, `kategori`, `sub_transaction_type`, `nilai_kontrak`, `harga_jual_tersendiri`, `recognition_type`, `revenue_account`, `payment_account`, field pajak, dan opsional data `jadwal_pengakuan`. Memanggil `compute_alokasi_harga()` setelah semua KP tersimpan.

**`confirm_pendapatan(header, user)`**
```
1. Resolve standar_akuntansi (header override atau ikuti EB)
2. Validasi semua KP: revenue_account, SSP, recognition_type
3. Validasi over-time KP: JadwalPengakuan lengkap
4. compute_alokasi_harga(header)
5. Per KP:
   - point_in_time + cash   → _journal_poin_cash(kp)
   - point_in_time + credit → _journal_poin_credit(kp) + buat PiutangHeader
   - over_time + advance_payment_cash → _journal_liabilitas_kontrak(kp)
   - over_time + periodic_billing    → tidak ada jurnal sekarang
   - over_time + performance_first   → tidak ada jurnal sekarang
6. set status = 'confirmed', log CONFIRMED
```

**`void_pendapatan(header, user)`**
Tambahan dari logic existing:
- Reverse jurnal `AsetKontrak` yang status=`aktif`
- Cancel `PiutangHeader` terkait AsetKontrak yang masih `open`

---

### 4.2 Services Baru

**`compute_alokasi_harga(header: PendapatanHeader) → None`**
```
all_kps = semua KP dari semua EB group header ini
total_ssp = Σ kp.harga_jual_tersendiri
total_harga = Σ kp.nilai_kontrak

untuk setiap KP (kecuali terakhir):
    kp.harga_dialokasikan = round(kp.harga_jual_tersendiri / total_ssp × total_harga, 4)

KP terakhir = total_harga − Σ kp.harga_dialokasikan sebelumnya  # anti-rounding error

bulk_update(semua KP, fields=['harga_dialokasikan'])
```
*Jika hanya 1 KP: `harga_dialokasikan = nilai_kontrak` (tidak perlu alokasi).*

---

**`create_jadwal_pengakuan(kp: KewajibabPelaksanaan) → JadwalPengakuan`**
Menggantikan `create_deferred_schedule()`. Idempoten (return existing jika sudah ada).

Generates `EntriPengakuan` berdasarkan `progress_method`:
- `straight_line` → entries dengan jumlah rata per bulan, remainder ke periode terakhir
- `percentage_manual` | `milestone` → entries kosong (`jumlah=0`), user isi saat akui
- `cost_incurred` → entries kosong, user isi `persentase_kemajuan` berdasar biaya

---

**`recognize_entry(entry: EntriPengakuan, user) → dict`**
Menggantikan `recognize_deferred_entry()`. Branches berdasarkan `entry.jadwal.tipe_aliran`:

```python
if tipe_aliran == 'advance_payment_cash':
    jurnal: Dr Liabilitas Kontrak → Cr Pendapatan
    return {'jurnal': jh}

elif tipe_aliran == 'periodic_billing':
    jurnal: Dr Piutang → Cr Pendapatan
    return {'jurnal': jh, 'buka_form_piutang': True, 'piutang_prefill': {...}}

elif tipe_aliran == 'performance_first':
    jurnal: Dr Aset Kontrak → Cr Pendapatan
    # Satu AsetKontrak per KP — cari existing atau buat baru
    # Jika sudah ada dan status 'aktif': update jumlah_diakui += entry.jumlah
    # Jika belum ada: buat baru dengan jumlah_diakui = entry.jumlah
    buat_atau_update AsetKontrak (OneToOne per KP, kecuali yang sudah 'dikonversi' → buat baru)
    return {'jurnal': jh, 'aset_kontrak': aset_kontrak}

# Semua kasus:
entry.status = 'recognized'
entry.jurnal_header = jh
entry.recognized_at = now()
entry.recognized_by = user
update KP.jumlah_diakui, KP.status_kp
update JadwalPengakuan.jumlah_diakui
log PendapatanEventLog('RECOGNITION', ...)
```

---

**`konversi_aset_kontrak_ke_piutang(aset_kontrak, jumlah, user) → dict`**
```
Validasi: jumlah ≤ aset_kontrak.sisa
Jurnal: Dr Piutang → Cr Aset Kontrak (jumlah)
aset_kontrak.jumlah_dikonversi += jumlah
Jika fully converted → aset_kontrak.status = 'dikonversi'
log PendapatanEventLog('ASET_KONTRAK_KONVERSI', ...)

Return dict prefill untuk form PiutangHeader:
{
    'jumlah_pokok': jumlah,
    'source_pendapatan_id': header.pk,
    'source_type': 'from_pendapatan',
    'coa_piutang_account_id': jadwal.piutang_account_id,
    'deskripsi': f'Piutang dari Aset Kontrak — {header.transaction_id}',
}
```
*View redirect ke `piutang:create` dengan prefill data via session/GET params.*

---

### 4.3 Deprecated

| Lama | Pengganti |
|---|---|
| `create_deferred_schedule()` | `create_jadwal_pengakuan()` |
| `recognize_deferred_entry()` | `recognize_entry()` |
| `reverse_deferred_entry()` | Logic dalam `void_pendapatan()` |
| `_create_pendapatan_journals()` | `_journal_poin_cash/credit()` + per-entry journals |

---

## 5. Forms & UI

### 5.1 Form Create/Edit

**`PendapatanHeaderForm`** — tambah `standar_akuntansi` (Select, blank="Ikuti Standar Entitas Bisnis").

**`KewajibabPelaksanaanForm`** (menggantikan `PendapatanItemForm`):

| Field | Keterangan |
|---|---|
| `deskripsi_item`, `kategori`, `sub_transaction_type` | Sama seperti sekarang |
| `nilai_kontrak` (was `jumlah_bruto`) | Harga terdaftar KP ini |
| `harga_jual_tersendiri` | SSP — diisi manual user |
| `harga_dialokasikan` | Read-only, JS live preview |
| `recognition_type` | Radio: Titik Waktu / Sepanjang Waktu |
| `revenue_account`, `payment_account`, field pajak | Sama seperti sekarang |

Ketika `recognition_type = over_time` → tampilkan **`JadwalPengakuanForm` inline**.

**`JadwalPengakuanForm`** (inline conditional):

| Field | Kondisi Tampil |
|---|---|
| `tipe_aliran` | Selalu (jika over_time) |
| `progress_method` | Selalu |
| `tanggal_mulai`, `tanggal_selesai` | Selalu |
| `recognition_account` | Selalu |
| `biaya_estimasi_total` | Hanya jika `cost_incurred` |
| `liabilitas_kontrak_acct` | Hanya jika `advance_payment_cash` |
| `aset_kontrak_acct` | Hanya jika `performance_first` |
| `piutang_account` | Jika `periodic_billing` atau `performance_first` |

### 5.2 SSP Allocation Preview (JS Live)

Panel dinamis di bawah semua KP form. Update real-time setiap `nilai_kontrak` atau `harga_jual_tersendiri` berubah:

```
┌─ Alokasi Harga Transaksi ─────────────────────────────────────────┐
│  ⓘ Mengapa perlu dialokasikan?                                     │
│  Setiap layanan diakui sesuai porsinya berdasarkan harga tersendiri│
│  (PSAK 72 Langkah 4 — Alokasi Harga Transaksi)                    │
│                                                                     │
│  KP 1 — Jasa Setup         SSP: 30jt  →  Dialokasikan: 30jt       │
│  KP 2 — Maintenance 12bln  SSP: 90jt  →  Dialokasikan: 90jt       │
│                                                                     │
│  Total SSP: 120jt  │  Σ Dialokasikan: 120jt  ✓                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.3 Indikator 5-Langkah PSAK 72

Ditampilkan di atas form sebagai progress bar ringan (step aktif di-highlight):
```
① Kontrak  →  ② KP  →  ③ Harga Transaksi  →  ④ Alokasi  →  ⑤ Pengakuan
```

### 5.4 Detail Page — Command Center

```
[TRX-PND-XXX]  Status: Confirmed  |  SAK PSAK 72  |  18-Jun-2026
[Tombol: Void]

══ Kewajiban Pelaksanaan ═══════════════════════════════════════════

  ┌─ KP 1: Jasa Setup (Titik Waktu) ──────────────────────────────┐
  │  Nilai Kontrak: 30jt │ Dialokasikan: 30jt │ ✓ Selesai         │
  │  Jurnal: TRX-PND-J-0001  │  Piutang: TRX-PIU-005              │
  └───────────────────────────────────────────────────────────────┘

  ┌─ KP 2: Maintenance 12 Bln (Sepanjang Waktu · Bayar di Muka) ──┐
  │  Nilai Kontrak: 90jt │ Dialokasikan: 90jt                      │
  │  Diakui: 22,5jt / 90jt (25%)  │  Sedang Berjalan              │
  │  Liabilitas Kontrak Tersisa: 67,5jt                             │
  │                                                                 │
  │  Periode      Jumlah     Status      Aksi                       │
  │  Jan 2026     7.500.000  ✓ Diakui   —                          │
  │  Feb 2026     7.500.000  ✓ Diakui   —                          │
  │  Mar 2026     7.500.000  ○ Pending  [Akui]                     │
  │  ...                                                            │
  └───────────────────────────────────────────────────────────────┘

══ Piutang Terkait ════════════════════════════════════════════════
  TRX-PIU-005 │ 30jt │ Open │ Jatuh Tempo: 01-Jul-2026

══ Event Log ══════════════════════════════════════════════════════
  2026-06-18  CREATED     user@nif.id
  2026-06-18  CONFIRMED   user@nif.id  → TRX-PND-J-0001
  ...
```

### 5.5 Mini-Form Recognition Entry

**`straight_line`** → tombol **[Akui]** langsung (jumlah sudah pasti).

**`percentage_manual` / `milestone` / `cost_incurred`** → modal:
```
┌─ Akui Pendapatan — Mar 2026 ─────────────────────────────────────┐
│  ⓘ Mengakui pendapatan artinya Anda menyatakan bahwa layanan     │
│  untuk periode ini sudah selesai diberikan kepada pelanggan.      │
│  Sistem akan membuat jurnal otomatis.                             │
│                                                                   │
│  Kemajuan kumulatif sebelumnya:  25%                              │
│  Kemajuan kumulatif periode ini: [____] %                         │
│  ⓘ Isi total kemajuan dari awal kontrak (kumulatif).             │
│                                                                   │
│  Jumlah yang diakui: Rp _______ (otomatis dihitung)              │
│  Catatan / milestone: [_____________________________]             │
│                                                                   │
│                       [Batal]  [Akui & Buat Jurnal]              │
└───────────────────────────────────────────────────────────────────┘
```
Formula: `jumlah = (% baru − % kumulatif lama) × jadwal.jumlah_total`

**Setelah akui `performance_first`** → notifikasi inline:
> *"Aset Kontrak bertambah Rp X. [Konversi ke Piutang →]"*

---

## 6. Standar UX Wajib

Berlaku di **semua halaman baru** modul pendapatan:

1. **Banner panduan** di atas setiap form — menjelaskan konteks dalam bahasa sederhana
2. **`help_text`** di setiap field teknis — penjelasan awam, bukan definisi PSAK verbatim
3. **Ikon ⓘ tooltip** untuk setiap istilah PSAK (Kewajiban Pelaksanaan, SSP, Liabilitas Kontrak, dll.)
4. **Indikator 5-langkah** PSAK 72 di atas form create/edit
5. **Istilah berpasangan** — selalu tampilkan istilah PSAK + padanan awam, contoh: *"Liabilitas Kontrak (Uang Muka Belum Diakui)"*

### Glosarium Istilah (untuk tooltip & help_text)

| Istilah PSAK | Penjelasan Awam |
|---|---|
| Kewajiban Pelaksanaan (KP) | Setiap jenis layanan atau barang yang dijanjikan dalam kontrak |
| Harga Jual Tersendiri (SSP) | Harga layanan ini jika dijual sendiri, tanpa paket |
| Harga Dialokasikan | Pendapatan yang menjadi hak entitas untuk KP ini setelah dibagi proporsional |
| Liabilitas Kontrak | Uang muka dari pelanggan yang belum menjadi pendapatan karena layanan belum selesai |
| Aset Kontrak | Layanan yang sudah diberikan tapi belum ditagihkan ke pelanggan |
| Titik Waktu | Layanan selesai sekaligus (mis. pengiriman barang, jasa singkat) |
| Sepanjang Waktu | Layanan berlangsung beberapa periode (mis. langganan, proyek bertahap) |
| Garis Lurus | Pendapatan dibagi rata per bulan selama masa kontrak |
| Persentase Penyelesaian | Pendapatan diakui sesuai seberapa jauh pekerjaan sudah selesai |

---

## 7. Batasan Scope (Iterasi Ini)

- **Hanya SAK (PSAK 72 penuh).** SAK EP dan SAK EMKM menyusul iterasi berikutnya.
- **Imbalan variabel** (diskon, bonus, rabat) belum diimplementasi — `nilai_kontrak` dianggap fixed.
- **Komponen pembiayaan signifikan** (PV adjustment untuk kontrak > 1 tahun) belum diimplementasi.
- **Modul Sales tidak disentuh** — integrasi `source_sales` tetap berjalan seperti sekarang.
- **Recurring Template** tidak berubah strukturnya — hanya perlu update agar KP baru yang dihasilkan punya field `recognition_type` default `point_in_time`.

---

## 8. Migrasi Data

Migration Django yang diperlukan:
1. Rename tabel `pendapatan_pendapatanitem` → `pendapatan_kewajibabpelaksanaan` (via `db_table`)
2. `RenameField`: `jumlah_bruto` → `nilai_kontrak`
3. `AddField`: `harga_jual_tersendiri`, `harga_dialokasikan`, `recognition_type`, `status_kp`, `jumlah_diakui`
4. `RemoveField`: `is_deferred`, `deferred_account`, `recognition_account`, `deferred_tanggal_mulai`, `deferred_tanggal_selesai`, `deferred_metode`
5. Buat tabel baru: `JadwalPengakuan`, `EntriPengakuan`, `AsetKontrak`
6. Hapus tabel lama: `DeferredRevenueSchedule`, `DeferredRevenueEntry`
7. `AddField` ke `PendapatanHeader`: `standar_akuntansi`

**Data existing:**
- Item dengan `is_deferred=True` → migrate ke `KewajibabPelaksanaan` dengan `recognition_type='over_time'` + buat `JadwalPengakuan` dari data deferred yang ada
- Item dengan `is_deferred=False` → migrate ke `recognition_type='point_in_time'`
- `DeferredRevenueSchedule` → migrate ke `JadwalPengakuan`
- `DeferredRevenueEntry` → migrate ke `EntriPengakuan`
- Data migration script diperlukan (RunPython)
