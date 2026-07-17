# Fixed Asset — Pelepasan (Fase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan pencatatan pelepasan aset tetap (`AssetDisposal`) yang memicu jurnal pelepasan otomatis (jual/hibah/rusak/musnah), mendukung pelepasan sebagian, dan dapat dibatalkan kapan saja.

**Architecture:** Model baru `AssetDisposal` di `apps/aset_tetap` menyimpan snapshot pro-rata (perolehan/akumulasi/residu/laba-rugi). Engine `process_asset_disposal` menghitung snapshot, mengurangi state aset, dan membuat `JurnalHeader`+`JurnalDetail` yang balance. `reverse_asset_disposal` memulihkan aset dari snapshot dan menghapus jurnal (via `log_jurnal_terhapus`). Field `status` di `AsetTetapRecord` menonaktifkan aset yang habis dilepas dari penyusutan.

**Tech Stack:** Django (models/services/forms/views/templates), `django.test.TestCase`, Decimal arithmetic.

**Spec:** `docs/superpowers/specs/2026-07-17-fixedasset-pelepasan-fase4-design.md`

---

## File Structure

- **Modify** `apps/aset_tetap/models.py` — tambah `AsetTetapRecord.status` + model `AssetDisposal`.
- **Modify** `apps/aset_tetap/services.py` — `_next_disposal_journal_number`, `_resolve_asset_account`, `process_asset_disposal`, `reverse_asset_disposal`, guard di `process_depreciation`.
- **Modify** `apps/aset_tetap/forms.py` — `AssetDisposalForm`.
- **Modify** `apps/aset_tetap/views.py` — `aset_tetap_dispose`, `aset_tetap_disposal_delete`, wiring context di `aset_tetap_detail`, skip di `aset_tetap_bulk_depreciation`.
- **Modify** `apps/aset_tetap/urls.py` — 2 route baru.
- **Modify** `templates/aset_tetap/aset_tetap_detail.html` — tombol + form + riwayat pelepasan.
- **Create** `templates/aset_tetap/disposal_delete_confirm.html` — konfirmasi pembatalan.
- **Modify** `templates/aset_tetap/aset_tetap_list.html` — badge status (opsional, kolom kecil).
- **Modify** `apps/aset_tetap/tests.py` — test acceptance.
- **Create** migrasi via `makemigrations`.

**Test runner:** `python manage.py test apps.aset_tetap -v 2` (dijalankan dari `naveda_integra/`).

---

## Task 1: Model `status` + `AssetDisposal`

**Files:**
- Modify: `apps/aset_tetap/models.py`
- Create: migrasi `apps/aset_tetap/migrations/00XX_assetdisposal.py` (via makemigrations)
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tambah field `status` ke `AsetTetapRecord`**

Di `apps/aset_tetap/models.py`, di dalam class `AsetTetapRecord`, tambahkan choices + field (letakkan setelah `KONDISI_CHOICES`/`METODE_PENYUSUTAN_CHOICES`, dan field setelah `kondisi`):

```python
    STATUS_CHOICES = [
        ('aktif', 'Aktif'),
        ('dilepas', 'Dilepas'),
    ]
```

Dan sebagai field (mis. setelah `kondisi`):

```python
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='aktif',
        db_index=True,
        verbose_name='Status Aset',
    )
```

- [ ] **Step 2: Tambah model `AssetDisposal`**

Di akhir `apps/aset_tetap/models.py`, tambahkan:

```python
class AssetDisposal(models.Model):
    """Peristiwa pelepasan aset tetap — memicu jurnal pelepasan & laba/rugi."""
    JENIS_CHOICES = [
        ('jual', 'Jual'),
        ('hibah', 'Hibah'),
        ('rusak', 'Rusak'),
        ('musnah', 'Musnah'),
    ]

    disposal_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name='Nomor Pelepasan')
    aset = models.ForeignKey('AsetTetapRecord', on_delete=models.PROTECT, related_name='disposals', verbose_name='Aset')
    tanggal = models.DateField(default=timezone.now, db_index=True, verbose_name='Tanggal Pelepasan')
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES, verbose_name='Jenis Pelepasan')
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity Dilepas')
    harga_jual = models.DecimalField(max_digits=19, decimal_places=4, default=0, verbose_name='Harga Jual')
    akun_kas = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='disposal_kas', verbose_name='Akun Kas/Piutang',
    )
    akun_laba_rugi = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='disposal_laba_rugi', verbose_name='Akun Laba/Rugi Pelepasan',
    )
    perolehan_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    akumulasi_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    residu_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    laba_rugi = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    keterangan = models.TextField(blank=True, verbose_name='Keterangan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pelepasan Aset'
        verbose_name_plural = 'Pelepasan Aset'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['aset', 'tanggal'], name='idx_disposal_aset_tgl'),
        ]

    def __str__(self) -> str:
        return self.disposal_number

    def save(self, *args, **kwargs):
        if not self.disposal_number:
            self.disposal_number = self._generate_disposal_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_disposal_number() -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                AssetDisposal.objects
                .select_for_update()
                .filter(disposal_number__startswith='DSP-')
                .order_by('-disposal_number')
                .values_list('disposal_number', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'DSP-{seq:03d}'
```

- [ ] **Step 3: Buat migrasi**

Run: `python manage.py makemigrations aset_tetap`
Expected: migrasi baru dibuat berisi `AddField status` + `CreateModel AssetDisposal`.

- [ ] **Step 4: Tulis test model**

Di `apps/aset_tetap/tests.py`, tambahkan import dan class test:

```python
from decimal import Decimal
from apps.master_data.models import Akun
from .models import AsetTetapRecord, AssetDisposal


class AssetDisposalModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        self.record = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, harga_perolehan=1_000_000,
        )
        self.akun_akum = Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_kas = Akun.objects.create(kategori_id='aset', kode_akun='1.1.1.01', nama='Kas')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan Aset')

    def test_status_default_aktif(self):
        self.assertEqual(self.record.status, 'aktif')

    def test_disposal_number_auto(self):
        d = AssetDisposal.objects.create(
            aset=self.record, jenis='jual', quantity=1,
            akun_laba_rugi=self.akun_lr,
        )
        self.assertTrue(d.disposal_number.startswith('DSP-'))
```

- [ ] **Step 5: Run tests**

Run: `python manage.py test apps.aset_tetap.tests.AssetDisposalModelTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/aset_tetap/models.py apps/aset_tetap/migrations/ apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): model AssetDisposal + status aset"
```

---

## Task 2: Engine `process_asset_disposal`

**Files:**
- Modify: `apps/aset_tetap/services.py`
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tulis test skenario jual (laba, rugi, impas) — failing**

Di `apps/aset_tetap/tests.py` tambahkan class (memakai `setUp` fixture pola Task 1; ulangi fixture agar mandiri):

```python
class ProcessDisposalTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        self.akun_akum = Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_kas = Akun.objects.create(kategori_id='aset', kode_akun='1.1.1.01', nama='Kas')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan')

    def _make_record(self, qty='1', harga='1000000', akum='0', residu='0'):
        return AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal(qty), harga_perolehan=Decimal(harga),
            akumulasi_penyusutan=Decimal(akum), nilai_residu=Decimal(residu),
        )

    def _sum_debit_kredit(self, header):
        from apps.jurnal.models import JurnalDetail
        d = sum(x.debit for x in JurnalDetail.objects.filter(jurnal_header=header))
        k = sum(x.kredit for x in JurnalDetail.objects.filter(jurnal_header=header))
        return d, k

    def test_jual_laba(self):
        # perolehan 1jt, akum 600rb -> nilai buku 400rb; jual 500rb -> laba 100rb
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('500000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.kredit, Decimal('100000.0000'))  # laba di kredit
        self.assertEqual(lr.debit, Decimal('0'))
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'dilepas')
        self.assertEqual(rec.quantity, Decimal('0.0000'))

    def test_jual_rugi(self):
        # nilai buku 400rb; jual 300rb -> rugi 100rb (debit)
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('300000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.debit, Decimal('100000.0000'))
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)

    def test_jual_impas(self):
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('400000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        self.assertFalse(JurnalDetail.objects.filter(jurnal_header=header, akun=self.akun_lr).exists())
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)
```

Tambahkan import di header test file: `from .services import process_asset_disposal` (akan gagal impor dulu).

- [ ] **Step 2: Run test — verify fail**

Run: `python manage.py test apps.aset_tetap.tests.ProcessDisposalTests -v 2`
Expected: FAIL (ImportError: cannot import name 'process_asset_disposal').

- [ ] **Step 3: Implementasi engine**

Di `apps/aset_tetap/services.py`, tambahkan import model dan fungsi (setelah `process_depreciation`):

```python
from .models import AsetTetapRecord, AssetDisposal  # perbarui import baris atas file


def _next_disposal_journal_number() -> str:
    """Nomor jurnal pelepasan sekuensial: TRX-DSP-xxx."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-DSP-')
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'TRX-DSP-{seq:03d}'


def _resolve_asset_account(record: AsetTetapRecord):
    """Akun aset yang didebit saat perolehan: purchase_item.coa_account -> item.coa_account."""
    if record.purchase_item_id and record.purchase_item and record.purchase_item.coa_account:
        return record.purchase_item.coa_account
    if record.item and record.item.coa_account:
        return record.item.coa_account
    return None


def process_asset_disposal(disposal: AssetDisposal) -> JurnalHeader:
    """Proses pelepasan aset: hitung snapshot, kurangi aset, buat jurnal pelepasan.

    Jurnal:
        Kredit Aset (perolehan dilepas)
        Debit  Akumulasi Penyusutan (akumulasi dilepas)
        Debit  Kas/Piutang (harga jual) -- hanya jenis 'jual' & harga_jual > 0
        Laba (kredit) / Rugi (debit) pada akun_laba_rugi -- selisih
    """
    quantize = Decimal('0.0001')
    aset = disposal.aset
    jenis = disposal.jenis
    quantity = disposal.quantity

    # Normalisasi non-jual
    if jenis != 'jual':
        disposal.harga_jual = Decimal('0')
        disposal.akun_kas = None
    harga_jual = disposal.harga_jual or Decimal('0')

    # Validasi
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas dan tidak dapat dilepas lagi.')
    if quantity is None or quantity <= 0:
        raise ValueError('Quantity pelepasan harus lebih dari 0.')
    if quantity > aset.quantity:
        raise ValueError(
            f'Quantity pelepasan ({quantity}) melebihi sisa quantity aset ({aset.quantity}).'
        )
    if harga_jual < 0:
        raise ValueError('Harga jual tidak boleh negatif.')
    if jenis == 'jual' and harga_jual > 0 and not disposal.akun_kas:
        raise ValueError('Akun Kas/Piutang wajib dipilih untuk pelepasan jenis jual.')
    if not disposal.akun_laba_rugi_id:
        raise ValueError('Akun Laba/Rugi Pelepasan wajib dipilih.')

    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')
    akun_akumulasi = Akun.objects.filter(kode_akun__startswith='1.2.7').first()
    if not akun_akumulasi:
        raise ValueError('Akun Akumulasi Penyusutan (1.2.7.xx) belum tersedia di Chart of Accounts.')

    # Snapshot pro-rata
    fraksi = quantity / aset.quantity
    perolehan_dilepas = (quantity * aset.harga_perolehan).quantize(quantize)
    akumulasi_dilepas = (aset.akumulasi_penyusutan * fraksi).quantize(quantize)
    residu_dilepas = (aset.nilai_residu * fraksi).quantize(quantize)
    nilai_buku_dilepas = perolehan_dilepas - akumulasi_dilepas
    laba_rugi = (harga_jual - nilai_buku_dilepas).quantize(quantize)

    # Baris jurnal: (akun, debit, kredit)
    lines = [
        (akun_aset, Decimal('0'), perolehan_dilepas),        # Kredit aset
        (akun_akumulasi, akumulasi_dilepas, Decimal('0')),   # Debit akumulasi
    ]
    if jenis == 'jual' and harga_jual > 0:
        lines.append((disposal.akun_kas, harga_jual, Decimal('0')))   # Debit kas
    if laba_rugi > 0:
        lines.append((disposal.akun_laba_rugi, Decimal('0'), laba_rugi))   # Kredit laba
    elif laba_rugi < 0:
        lines.append((disposal.akun_laba_rugi, -laba_rugi, Decimal('0')))  # Debit rugi

    total_debit = sum((d for _, d, _ in lines), Decimal('0'))
    total_kredit = sum((k for _, _, k in lines), Decimal('0'))
    if total_debit != total_kredit:
        raise ValueError(
            f'Jurnal pelepasan tidak balance: debit {total_debit} != kredit {total_kredit}.'
        )

    with transaction.atomic():
        disposal.perolehan_dilepas = perolehan_dilepas
        disposal.akumulasi_dilepas = akumulasi_dilepas
        disposal.residu_dilepas = residu_dilepas
        disposal.laba_rugi = laba_rugi

        aset.quantity -= quantity
        aset.akumulasi_penyusutan -= akumulasi_dilepas
        aset.nilai_residu -= residu_dilepas
        if aset.quantity <= 0:
            aset.status = 'dilepas'
        aset.save()

        header = JurnalHeader.objects.create(
            tanggal=disposal.tanggal,
            nomor_transaksi=_next_disposal_journal_number(),
            uraian_transaksi=f'Pelepasan {aset.aset_number} ({jenis}) — {aset.item.nama}',
            entitas_bisnis=aset.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
            for akun, d, k in lines
        ])
        disposal.jurnal_header = header
        disposal.save()

    return header
```

Catatan: `AsetTetapRecord.save()` menghitung ulang `total_value = quantity * harga_perolehan`, sehingga basis penyusutan sisa otomatis benar.

- [ ] **Step 4: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.ProcessDisposalTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Tambah test non-jual, partial, validasi**

Tambahkan method ke `ProcessDisposalTests`:

```python
    def test_non_jual_full_loss(self):
        # hibah: tidak ada kas, seluruh nilai buku jadi rugi
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          harga_jual=Decimal('999'), akun_kas=self.akun_kas,  # harus diabaikan
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        self.assertFalse(JurnalDetail.objects.filter(jurnal_header=header, akun=self.akun_kas).exists())
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.debit, Decimal('400000.0000'))  # seluruh nilai buku = rugi
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)

    def test_partial_prorata(self):
        # qty 10, harga 1jt/unit -> total 10jt, akum 2jt, residu 1jt; lepas 3
        rec = self._make_record(qty='10', harga='1000000', akum='2000000', residu='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('3'),
                          akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d)
        d.refresh_from_db()
        self.assertEqual(d.perolehan_dilepas, Decimal('3000000.0000'))
        self.assertEqual(d.akumulasi_dilepas, Decimal('600000.0000'))   # 2jt * 0.3
        self.assertEqual(d.residu_dilepas, Decimal('300000.0000'))      # 1jt * 0.3
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('7.0000'))
        self.assertEqual(rec.status, 'aktif')
        self.assertEqual(rec.total_value, Decimal('7000000.0000'))
        self.assertEqual(rec.akumulasi_penyusutan, Decimal('1400000.0000'))
        self.assertEqual(rec.nilai_residu, Decimal('700000.0000'))

    def test_validasi_qty_melebihi(self):
        rec = self._make_record(qty='2', harga='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('5'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)

    def test_validasi_akun_aset_kosong(self):
        item2 = ItemMasterPurchase.objects.create(nama='Tanpa COA', tipe_item='ATP')  # coa_account None
        rec = AsetTetapRecord.objects.create(
            item=item2, entitas_bisnis=self.entitas, quantity=1, harga_perolehan=1000000,
        )
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)

    def test_validasi_akumulasi_akun_hilang(self):
        self.akun_akum.delete()
        rec = self._make_record(qty='1', harga='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)
```

- [ ] **Step 6: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.ProcessDisposalTests -v 2`
Expected: PASS (8 tests).

- [ ] **Step 7: Commit**

```bash
git add apps/aset_tetap/services.py apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): engine process_asset_disposal + jurnal pelepasan"
```

---

## Task 3: Reversal `reverse_asset_disposal`

**Files:**
- Modify: `apps/aset_tetap/services.py`
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tulis test reversal — failing**

Tambahkan class ke `apps/aset_tetap/tests.py`:

```python
class ReverseDisposalTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan')

    def test_reversal_restores_state(self):
        from apps.jurnal.models import JurnalHeader
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal('10'), harga_perolehan=Decimal('1000000'),
            akumulasi_penyusutan=Decimal('2000000'), nilai_residu=Decimal('1000000'),
        )
        # dua pelepasan
        d1 = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('3'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d1)
        rec.refresh_from_db()
        d2 = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('2'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d2)
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('5.0000'))

        # reversal d1 (yang pertama — bebas kapan saja)
        header_pk = d1.jurnal_header_id
        reverse_asset_disposal(d1)
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('8.0000'))              # 5 + 3
        self.assertEqual(rec.status, 'aktif')
        self.assertFalse(JurnalHeader.objects.filter(pk=header_pk).exists())
        self.assertFalse(AssetDisposal.objects.filter(pk=d1.pk).exists())

    def test_reversal_logs_deletion(self):
        from apps.jurnal.models import JurnalTerhapus
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal('1'), harga_perolehan=Decimal('1000000'),
        )
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d)
        reverse_asset_disposal(d)
        self.assertTrue(JurnalTerhapus.objects.exists())
```

Tambahkan import: `from .services import process_asset_disposal, reverse_asset_disposal`.

Catatan: model log adalah `JurnalTerhapus` (`apps/jurnal/models.py:146`) — sudah diverifikasi.

- [ ] **Step 2: Run test — verify fail**

Run: `python manage.py test apps.aset_tetap.tests.ReverseDisposalTests -v 2`
Expected: FAIL (ImportError: reverse_asset_disposal).

- [ ] **Step 3: Implementasi reversal**

Di `apps/aset_tetap/services.py` tambahkan:

```python
def reverse_asset_disposal(disposal: AssetDisposal, request=None) -> None:
    """Batalkan pelepasan: hapus jurnal (dengan log), pulihkan state aset dari snapshot,
    lalu hapus record disposal. Boleh dilakukan kapan saja (tidak harus yang terakhir).
    """
    from apps.jurnal.utils import log_jurnal_terhapus

    aset = disposal.aset
    with transaction.atomic():
        header = disposal.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()

        aset.quantity += disposal.quantity
        aset.akumulasi_penyusutan += disposal.akumulasi_dilepas
        aset.nilai_residu += disposal.residu_dilepas
        aset.status = 'aktif'
        aset.save()

        disposal.delete()
```

- [ ] **Step 4: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.ReverseDisposalTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/aset_tetap/services.py apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): reverse_asset_disposal (pulihkan aset + hapus jurnal)"
```

---

## Task 4: Guard penyusutan untuk aset dilepas

**Files:**
- Modify: `apps/aset_tetap/services.py` (`process_depreciation`)
- Modify: `apps/aset_tetap/views.py` (`aset_tetap_bulk_depreciation`)
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tulis test guard — failing**

Tambahkan ke `apps/aset_tetap/tests.py`:

```python
class DepreciationGuardTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akum')
        Akun.objects.create(kategori_id='beban', kode_akun='5.1.19.01', nama='Beban Penyusutan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Mesin X', tipe_item='ATP', coa_account=akun_aset,
        )

    def test_process_depreciation_blocks_disposed(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=1000000, status='dilepas',
        )
        with self.assertRaises(ValueError):
            process_depreciation(rec, Decimal('1000'))
```

Import: `from .services import process_depreciation`.

- [ ] **Step 2: Run test — verify fail**

Run: `python manage.py test apps.aset_tetap.tests.DepreciationGuardTests -v 2`
Expected: FAIL (tidak ada ValueError; jurnal dibuat).

- [ ] **Step 3: Tambah guard di `process_depreciation`**

Di `apps/aset_tetap/services.py`, di awal `process_depreciation` (setelah `if tanggal is None:` block, sebelum cek `depreciation_amount <= 0`), tambahkan:

```python
    if record.status == 'dilepas':
        raise ValueError('Aset sudah dilepas — penyusutan tidak dapat diproses.')
```

- [ ] **Step 4: Tambah skip di bulk view**

Di `apps/aset_tetap/views.py`, dalam `aset_tetap_bulk_depreciation`, di dalam loop `for record in records:`, setelah baris `if record.nilai_buku <= record.nilai_residu:` block (yang menaikkan `skip_count`), tambahkan cek pertama:

```python
        if record.status == 'dilepas':
            skip_count += 1
            continue
```

Letakkan sebelum pengecekan `nilai_buku` agar aset dilepas selalu di-skip.

- [ ] **Step 5: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.DepreciationGuardTests -v 2`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add apps/aset_tetap/services.py apps/aset_tetap/views.py apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): blokir penyusutan untuk aset yang sudah dilepas"
```

---

## Task 5: Form `AssetDisposalForm`

**Files:**
- Modify: `apps/aset_tetap/forms.py`
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tulis test form — failing**

Tambahkan ke `apps/aset_tetap/tests.py`:

```python
class AssetDisposalFormTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=akun_aset)
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='LR')
        self.akun_kas = Akun.objects.create(kategori_id='aset', kode_akun='1.1.1.01', nama='Kas')
        self.rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas, quantity=Decimal('5'), harga_perolehan=Decimal('1000000'),
        )

    def test_qty_melebihi_invalid(self):
        from .forms import AssetDisposalForm
        form = AssetDisposalForm(data={
            'jenis': 'hibah', 'tanggal': '2026-07-17', 'quantity': '9',
            'harga_jual': '0', 'akun_laba_rugi': self.akun_lr.pk,
        }, aset=self.rec)
        self.assertFalse(form.is_valid())
        self.assertIn('quantity', form.errors)

    def test_jual_tanpa_kas_invalid(self):
        from .forms import AssetDisposalForm
        form = AssetDisposalForm(data={
            'jenis': 'jual', 'tanggal': '2026-07-17', 'quantity': '1',
            'harga_jual': '500000', 'akun_laba_rugi': self.akun_lr.pk,
        }, aset=self.rec)
        self.assertFalse(form.is_valid())
        self.assertIn('akun_kas', form.errors)

    def test_valid_hibah(self):
        from .forms import AssetDisposalForm
        form = AssetDisposalForm(data={
            'jenis': 'hibah', 'tanggal': '2026-07-17', 'quantity': '2',
            'harga_jual': '0', 'akun_laba_rugi': self.akun_lr.pk,
        }, aset=self.rec)
        self.assertTrue(form.is_valid(), form.errors)
```

- [ ] **Step 2: Run test — verify fail**

Run: `python manage.py test apps.aset_tetap.tests.AssetDisposalFormTests -v 2`
Expected: FAIL (ImportError: AssetDisposalForm).

- [ ] **Step 3: Implementasi form**

Di `apps/aset_tetap/forms.py`, tambahkan import dan class:

```python
from decimal import Decimal
from apps.master_data.models import Akun
from .models import AsetTetapRecord, AssetDisposal


class AssetDisposalForm(forms.ModelForm):
    class Meta:
        model = AssetDisposal
        fields = ('jenis', 'tanggal', 'quantity', 'harga_jual', 'akun_kas', 'akun_laba_rugi', 'keterangan')
        widgets = {
            'jenis': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'harga_jual': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'akun_kas': forms.Select(attrs={'class': 'ni-input'}),
            'akun_laba_rugi': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, aset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aset = aset
        self.fields['akun_kas'].queryset = Akun.objects.all().order_by('kode_akun')
        self.fields['akun_laba_rugi'].queryset = Akun.objects.all().order_by('kode_akun')
        self.fields['akun_kas'].required = False
        self.fields['harga_jual'].required = False
        self.fields['keterangan'].required = False

    def clean(self):
        cleaned = super().clean()
        jenis = cleaned.get('jenis')
        qty = cleaned.get('quantity')
        harga = cleaned.get('harga_jual') or Decimal('0')

        if qty is not None and qty <= 0:
            self.add_error('quantity', 'Quantity harus lebih dari 0.')
        elif self.aset is not None and qty is not None and qty > self.aset.quantity:
            self.add_error('quantity', f'Melebihi sisa quantity aset ({self.aset.quantity}).')

        if jenis != 'jual':
            cleaned['harga_jual'] = Decimal('0')
            cleaned['akun_kas'] = None
        elif harga > 0 and not cleaned.get('akun_kas'):
            self.add_error('akun_kas', 'Akun Kas/Piutang wajib untuk pelepasan jenis jual.')

        return cleaned
```

- [ ] **Step 4: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.AssetDisposalFormTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/aset_tetap/forms.py apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): AssetDisposalForm dengan validasi jenis/qty/kas"
```

---

## Task 6: Views + URLs

**Files:**
- Modify: `apps/aset_tetap/views.py`
- Modify: `apps/aset_tetap/urls.py`
- Test: `apps/aset_tetap/tests.py`

- [ ] **Step 1: Tulis test view — failing**

Tambahkan ke `apps/aset_tetap/tests.py`:

```python
class DisposalViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='v@test.com', password='pass')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akum')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='LR')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=akun_aset)
        self.rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas, quantity=Decimal('5'), harga_perolehan=Decimal('1000000'),
        )

    def test_dispose_post_creates_disposal(self):
        res = self.client.post(reverse('aset_tetap:dispose', args=[self.rec.pk]), {
            'jenis': 'hibah', 'tanggal': '2026-07-17', 'quantity': '2',
            'harga_jual': '0', 'akun_laba_rugi': self.akun_lr.pk,
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(AssetDisposal.objects.filter(aset=self.rec).count(), 1)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.quantity, Decimal('3.0000'))

    def test_disposal_delete_reverses(self):
        d = AssetDisposal(aset=self.rec, jenis='hibah', quantity=Decimal('2'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d)
        res = self.client.post(reverse('aset_tetap:disposal_delete', args=[self.rec.pk, d.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(AssetDisposal.objects.filter(pk=d.pk).exists())
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.quantity, Decimal('5.0000'))
```

- [ ] **Step 2: Run test — verify fail**

Run: `python manage.py test apps.aset_tetap.tests.DisposalViewTests -v 2`
Expected: FAIL (NoReverseMatch: 'dispose').

- [ ] **Step 3: Tambah import + views**

Di `apps/aset_tetap/views.py`:

Perbarui import:
```python
from .forms import AsetTetapRecordForm, AssetDisposalForm
from .models import AsetTetapRecord, AssetDisposal
from .services import (
    calculate_depreciation, process_depreciation,
    process_asset_disposal, reverse_asset_disposal,
)
```

Tambahkan views (mis. setelah `delete_depreciation_journal`):

```python
@login_required
def aset_tetap_dispose(request: HttpRequest, pk: int) -> HttpResponse:
    """Proses pelepasan aset dari halaman detail."""
    record = get_object_or_404(
        AsetTetapRecord.objects.select_related('item', 'entitas_bisnis', 'purchase_item'),
        pk=pk,
    )
    if request.method != 'POST':
        return redirect('aset_tetap:detail', pk=pk)

    form = AssetDisposalForm(request.POST, aset=record)
    if not form.is_valid():
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f'{field}: {e}')
        return redirect('aset_tetap:detail', pk=pk)

    disposal = form.save(commit=False)
    disposal.aset = record
    try:
        header = process_asset_disposal(disposal)
        messages.success(
            request,
            f'Pelepasan {record.aset_number} berhasil diproses. Jurnal: {header.nomor_transaksi}.',
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('aset_tetap:detail', pk=pk)


@login_required
def aset_tetap_disposal_delete(request: HttpRequest, pk: int, disposal_pk: int) -> HttpResponse:
    """Batalkan pelepasan aset dan pulihkan aset."""
    record = get_object_or_404(AsetTetapRecord, pk=pk)
    disposal = get_object_or_404(AssetDisposal, pk=disposal_pk, aset=record)
    if request.method == 'POST':
        reverse_asset_disposal(disposal, request)
        messages.success(
            request,
            f'Pelepasan {disposal.disposal_number} dibatalkan. Aset dipulihkan.',
        )
        return redirect('aset_tetap:detail', pk=pk)
    return render(request, 'aset_tetap/disposal_delete_confirm.html', {
        'record': record,
        'disposal': disposal,
    })
```

- [ ] **Step 4: Tambah routes**

Di `apps/aset_tetap/urls.py`, tambahkan sebelum penutup list:

```python
    path('<int:pk>/lepas/', views.aset_tetap_dispose, name='dispose'),
    path('<int:pk>/pelepasan/<int:disposal_pk>/batal/', views.aset_tetap_disposal_delete, name='disposal_delete'),
```

- [ ] **Step 5: Wiring context di `aset_tetap_detail`**

Di `apps/aset_tetap/views.py`, dalam `aset_tetap_detail`, sebelum `return render(...)`, tambahkan:

```python
    from datetime import date as _dc
    disposal_form = AssetDisposalForm(aset=record, initial={'tanggal': _dc.today(), 'quantity': record.quantity})
    disposals = record.disposals.select_related('akun_kas', 'akun_laba_rugi', 'jurnal_header').all()
```

Lalu tambahkan ke dict context `render`:

```python
        'disposal_form': disposal_form,
        'disposals': disposals,
        'can_dispose': record.status == 'aktif' and record.quantity > 0,
```

- [ ] **Step 6: Run test — verify pass**

Run: `python manage.py test apps.aset_tetap.tests.DisposalViewTests -v 2`
Expected: PASS (2 tests).

Catatan: template `disposal_delete_confirm.html` belum ada; test hanya memakai POST (tidak render GET), jadi lolos. Template dibuat di Task 7.

- [ ] **Step 7: Commit**

```bash
git add apps/aset_tetap/views.py apps/aset_tetap/urls.py apps/aset_tetap/tests.py
git commit -m "feat(aset_tetap): view + url dispose & disposal_delete"
```

---

## Task 7: Templates (detail + konfirmasi + list badge)

**Files:**
- Modify: `templates/aset_tetap/aset_tetap_detail.html`
- Create: `templates/aset_tetap/disposal_delete_confirm.html`
- Modify: `templates/aset_tetap/aset_tetap_list.html`

- [ ] **Step 1: Tambah section pelepasan di detail**

Di `templates/aset_tetap/aset_tetap_detail.html`, sebelum baris terakhir `{% endblock %}` (saat ini baris 175), sisipkan:

Ikuti pola kartu yang sudah ada di file (`ni-card ni-animate-fade-in` + `ni-card__body` + `<h3>` sebagai header + `ni-form-row`/`ni-form-group` + `ni-btn-row`):

```html
<!-- Pelepasan Aset -->
<div class="ni-card ni-animate-fade-in" style="margin-top:16px;">
  <div class="ni-card__body">
    <h3 style="margin:0 0 16px;font-size:1rem;color:var(--ni-primary);">
      <i data-lucide="log-out" style="width:16px;height:16px;vertical-align:text-bottom;"></i>
      Pelepasan Aset
    </h3>
    {% if can_dispose %}
    <form method="post" action="{% url 'aset_tetap:dispose' record.pk %}">
      {% csrf_token %}
      <div class="ni-form-row">
        <div class="ni-form-group"><label class="ni-form-label">Jenis</label>{{ disposal_form.jenis }}</div>
        <div class="ni-form-group"><label class="ni-form-label">Tanggal</label>{{ disposal_form.tanggal }}</div>
        <div class="ni-form-group"><label class="ni-form-label">Quantity (sisa {{ record.quantity|floatformat:"-4" }})</label>{{ disposal_form.quantity }}</div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group"><label class="ni-form-label">Harga Jual (isi bila jenis Jual)</label>{{ disposal_form.harga_jual }}</div>
        <div class="ni-form-group"><label class="ni-form-label">Akun Kas/Piutang</label>{{ disposal_form.akun_kas }}</div>
        <div class="ni-form-group"><label class="ni-form-label">Akun Laba/Rugi Pelepasan</label>{{ disposal_form.akun_laba_rugi }}</div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group" style="flex:1"><label class="ni-form-label">Keterangan</label>{{ disposal_form.keterangan }}</div>
      </div>
      <div class="ni-btn-row" style="margin-top:12px;">
        <button type="submit" class="ni-btn ni-btn--primary"
                onclick="return confirm('Proses pelepasan aset ini?')">
          <i data-lucide="log-out" style="width:14px;height:14px"></i> Lepas Aset
        </button>
      </div>
    </form>
    {% else %}
      <p style="color:var(--ni-text-muted);">Aset ini sudah dilepas seluruhnya (status: {{ record.get_status_display }}).</p>
    {% endif %}
  </div>
</div>

<!-- Riwayat Pelepasan -->
{% if disposals %}
<div class="ni-card ni-animate-fade-in" style="margin-top:16px;">
  <div class="ni-card__body">
    <h3 style="margin:0 0 16px;font-size:1rem;color:var(--ni-primary);">Riwayat Pelepasan</h3>
    <table class="ni-table">
      <thead>
        <tr>
          <th>Nomor</th><th>Tanggal</th><th>Jenis</th>
          <th class="ni-text-right">Qty</th><th class="ni-text-right">Harga Jual</th>
          <th class="ni-text-right">Laba/Rugi</th><th>Jurnal</th><th></th>
        </tr>
      </thead>
      <tbody>
        {% for d in disposals %}
        <tr>
          <td>{{ d.disposal_number }}</td>
          <td>{{ d.tanggal }}</td>
          <td>{{ d.get_jenis_display }}</td>
          <td class="ni-text-right">{{ d.quantity|floatformat:"-4" }}</td>
          <td class="ni-text-right">{{ d.harga_jual|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ d.laba_rugi|floatformat:0|intcomma }}</td>
          <td>{% if d.jurnal_header %}{{ d.jurnal_header.nomor_transaksi }}{% endif %}</td>
          <td>
            <a href="{% url 'aset_tetap:disposal_delete' record.pk d.pk %}" class="ni-btn ni-btn--outline-danger ni-btn--sm">
              Batalkan
            </a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: Buat template konfirmasi**

Create `templates/aset_tetap/disposal_delete_confirm.html`:

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Batalkan Pelepasan {{ disposal.disposal_number }}{% endblock %}
{% block content %}
<div class="ni-card" style="max-width:560px;margin:2rem auto">
  <div class="ni-card__header">Batalkan Pelepasan Aset</div>
  <div class="ni-card__body">
    <p>Yakin membatalkan pelepasan <strong>{{ disposal.disposal_number }}</strong>
       ({{ disposal.get_jenis_display }}, qty {{ disposal.quantity|floatformat:"-4" }})
       untuk aset <strong>{{ record.aset_number }}</strong>?</p>
    <p class="ni-text-muted">Jurnal
       {% if disposal.jurnal_header %}<strong>{{ disposal.jurnal_header.nomor_transaksi }}</strong>{% endif %}
       akan dihapus dan aset dipulihkan (quantity +{{ disposal.quantity|floatformat:"-4" }},
       akumulasi & residu dikembalikan).</p>
    <form method="post">
      {% csrf_token %}
      <a href="{% url 'aset_tetap:detail' record.pk %}" class="ni-btn ni-btn--outline">Batal</a>
      <button type="submit" class="ni-btn ni-btn--danger">Ya, Batalkan Pelepasan</button>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Badge status di daftar (opsional tapi disarankan)**

Di `templates/aset_tetap/aset_tetap_list.html`, pada baris tabel aset, tambahkan indikator status. Cari kolom nomor aset dan tambahkan badge:

```html
{% if record.status == 'dilepas' %}<span class="ni-badge ni-badge--secondary">Dilepas</span>{% endif %}
```

(Sesuaikan nama variabel loop dengan yang dipakai di template — mis. `record` atau `item`.)

- [ ] **Step 4: Verifikasi render halaman detail & konfirmasi**

Run seluruh test app untuk memastikan tidak ada regresi template/route:
`python manage.py test apps.aset_tetap -v 2`
Expected: seluruh test PASS.

Lalu verifikasi manual (opsional, via `/run` skill atau server): buka halaman detail aset, submit pelepasan, cek jurnal terbentuk, lalu batalkan.

- [ ] **Step 5: Commit**

```bash
git add templates/aset_tetap/aset_tetap_detail.html templates/aset_tetap/disposal_delete_confirm.html templates/aset_tetap/aset_tetap_list.html
git commit -m "feat(aset_tetap): UI pelepasan aset (form, riwayat, konfirmasi batal)"
```

---

## Task 8: Verifikasi menyeluruh

- [ ] **Step 1: Jalankan seluruh test app aset_tetap**

Run: `python manage.py test apps.aset_tetap -v 2`
Expected: seluruh test PASS (model, engine, reversal, guard, form, view).

- [ ] **Step 2: Jalankan test terkait (jurnal, purchase) untuk regresi**

Run: `python manage.py test apps.jurnal apps.purchase -v 1`
Expected: PASS (tidak ada regresi dari perubahan model/migrasi).

- [ ] **Step 3: Cek migrasi konsisten**

Run: `python manage.py makemigrations --check --dry-run`
Expected: "No changes detected" (semua perubahan model sudah termigrasi).

- [ ] **Step 4: Commit akhir bila ada perubahan**

```bash
git add -A
git commit -m "test(aset_tetap): verifikasi menyeluruh Fase 4 pelepasan" || echo "nothing to commit"
```

---

## Self-Review Notes

- **Spec coverage:** Model (C.1/C.2 → Task 1), penomoran (C.3 → Task 1/2), engine snapshot+jurnal+balance (D → Task 2), reversal (E → Task 3), guard penyusutan (F → Task 4), form (G.3 → Task 5), view/url (G.1/G.2 → Task 6), template detail/konfirmasi/list (G.4/G.5 → Task 7), migrasi (I → Task 1), test acceptance (H → tersebar Task 2–6, agregasi Task 8).
- **Sudah diverifikasi terhadap kode:** `JurnalTerhapus` (`apps/jurnal/models.py:146`), `log_jurnal_terhapus(header, module, request)`, `Akun(kategori_id, kode_akun, nama)`, `ItemMasterPurchase.coa_account` (nullable), `JurnalHeader/JurnalDetail` fields, kelas CSS template (`ni-card__body`+`<h3>`, `ni-form-row/group`, `ni-btn-row`, `ni-badge--secondary`), runner `python manage.py test`.
- **Type consistency:** `process_asset_disposal(disposal)`, `reverse_asset_disposal(disposal, request=None)`, `_resolve_asset_account(record)`, `_next_disposal_journal_number()` konsisten dipakai lintas Task 2/3/6.
