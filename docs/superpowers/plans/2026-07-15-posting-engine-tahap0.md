# Posting Engine — Tahap 0 (Fondasi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bangun fondasi Posting Engine sesuai `docs/superpowers/specs/2026-07-15-posting-engine-design.md` — katalog angka (di kode), model `JenisTransaksi`/`BarisJurnal`/`PemetaanAkun` (rantai scope + effective-dated), resolver, poster (pembentuk baris jurnal + cek balance), dan UI superuser-only untuk menyusun jenis transaksi + **preview jurnal** — dengan **nol pemanggil produksi**, sehingga tahap ini nol risiko bagi modul manapun yang sedang berjalan.

**Architecture:** App Django baru `apps/posting` (label `posting`). Tiap modul domain mengumumkan **angka** apa saja yang bisa ia sediakan lewat `register_amounts()` di `AppConfig.ready()` (di Tahap 0: kosong di produksi, hanya diisi tes). Superuser menyusun `JenisTransaksi` + `BarisJurnal` lewat UI; tiap baris menyatakan **angka mana, arah D/K/bertanda, dari mana akunnya**. `PemetaanAkun` menyimpan akun per baris per **scope** (`global` → `entitas_bisnis` → `lv2` → `lv3` → `metode_bayar` → `alasan`) dan per **tanggal berlaku**. `resolve_baris()` memilih scope paling spesifik yang berlaku pada tanggal jurnal. `bangun_baris_jurnal()` mengubahnya jadi rencana baris jurnal (akun, debit, kredit), melewati baris bernilai nol, dan **menolak yang tidak balance**. Poster **tidak** menulis `JurnalDetail` — modul yang menulis (Tahap 1+).

**Tech Stack:** Django, Postgres, `TestCase` di paket `tests/`, view fungsi biasa, AJAX via `fetch`/`FormData` (pola modal Chart of Accounts).

## Global Constraints

- **Nol pemanggil produksi.** Tidak ada app selain `apps/posting` yang boleh meng-import `apps.posting.*` dalam plan ini. Registry angka kosong di produksi; hanya tes yang mengisinya.
- **STT tidak disentuh.** Tidak ada perubahan pada `apps/purchase`, `apps/sales`, `apps/pendapatan`.
- **`JurnalHeader`/`JurnalDetail` tidak disentuh.** Cek balance di Tahap 0 hanya berlaku pada output poster sendiri. Menegakkannya global akan **merusak modul yang jurnalnya saat ini mungkin tidak balance** — itu pekerjaan tahap lanjutan setelah tiap modul diverifikasi.
- **Superuser-only.** Halaman posting dijaga `request.user.is_superuser`, **bukan** `has_ni_perm('settings_view')` (spec §8.2c: permission itu bisa diberikan ke user biasa, terlalu longgar untuk halaman milik vendor).
- **Postgres.** `UniqueConstraint` biasa **tidak** mencegah dua baris `scope_id=NULL` yang sama (SQL: `NULL != NULL`). Invarian "satu baris global per (baris, sisi, tanggal)" butuh **partial unique index** (`condition=Q(scope_id__isnull=True)`), plus constraint normal untuk kasus non-null.
- **Akun.** `master_data.Akun` punya `kategori_id` dengan pilihan: `aset`, `kewajiban`, `ekuitas`, `pendapatan`, `beban`. Dipakai untuk memfilter dropdown akun per baris.
- **Tes:** Django `TestCase` (repo ini tidak punya pytest), di paket `tests/`, satu file per concern.
- **`scope_ref` sengaja belum dipakai.** Kolomnya dibuat di Task 3 (agar tidak perlu migrasi lagi nanti), tetapi resolver & poster Tahap 0 **mengabaikannya** — ia baru berfungsi di Tahap 4 (mutasi antar cabang, di mana satu baris me-resolve akun dari scope *asal* dan baris lain dari scope *tujuan*). Jangan menambahkan logikanya sekarang; tidak ada yang bisa mengujinya sampai ada pemanggil nyata.
- **Preset & pewarisan Template Global → Klien → Outlet** (spec §8.3) tidak dibangun di Tahap 0. Mekanisme dasarnya **sudah ada** lewat rantai scope pada `PemetaanAkun`; yang belum ada hanyalah UI penyalin preset. Dijadwalkan setelah pilot Tahap 1 membuktikan enginenya.

---

### Task 1: Scaffold app `apps.posting`

**Files:**
- Create: `apps/posting/__init__.py`
- Create: `apps/posting/apps.py`
- Create: `apps/posting/urls.py`
- Create: `apps/posting/migrations/__init__.py`
- Modify: `naveda_integra/settings/base.py` (INSTALLED_APPS)
- Modify: `naveda_integra/urls.py`

**Interfaces:**
- Produces: app `apps.posting` (label `posting`), namespace URL `posting` di `/posting/`.

- [ ] **Step 1: Buat paket app**

`apps/posting/__init__.py` — file kosong.

`apps/posting/migrations/__init__.py` — file kosong.

`apps/posting/apps.py`:
```python
from django.apps import AppConfig


class PostingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.posting'
    label = 'posting'
    verbose_name = 'Posting Engine'
```

`apps/posting/urls.py`:
```python
"""Posting Engine URLs."""
from django.urls import path

app_name = 'posting'

urlpatterns = []
```

- [ ] **Step 2: Daftarkan di INSTALLED_APPS**

Di `naveda_integra/settings/base.py`, cari:
```python
    'apps.aset_lainnya', 'apps.ekuitas', 'apps.manufacturing', 'apps.dashboard',
    'apps.customers',
```
Ganti jadi:
```python
    'apps.aset_lainnya', 'apps.ekuitas', 'apps.manufacturing', 'apps.dashboard',
    'apps.customers', 'apps.posting',
```

- [ ] **Step 3: Pasang URL namespace**

Di `naveda_integra/urls.py`, cari:
```python
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('', include('apps.accounts.urls_home')),
```
Ganti jadi:
```python
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('posting/', include('apps.posting.urls', namespace='posting')),
    path('', include('apps.accounts.urls_home')),
```

- [ ] **Step 4: Pastikan project masih boot**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add apps/posting/__init__.py apps/posting/apps.py apps/posting/urls.py apps/posting/migrations/__init__.py naveda_integra/settings/base.py naveda_integra/urls.py
git commit -m "feat(posting): scaffold apps.posting"
```

---

### Task 2: Katalog angka (registry di kode)

Bagian **satu-satunya** yang butuh programmer saat modul ingin menyediakan kemampuan baru. Spec §3.1.

**Files:**
- Create: `apps/posting/catalog.py`
- Create: `apps/posting/tests/__init__.py`
- Create: `apps/posting/tests/test_catalog.py`

**Interfaces:**
- Produces: `Amount(kode, label, signed=False)`; `register_amounts(*, module, label, amounts, contexts) -> None`; `get_catalog() -> dict[str, ModuleAmounts]` (snapshot read-only); `get_amount(module, kode) -> Amount`; `clear_catalog()` (khusus tes); `CatalogError(Exception)`.
- `ModuleAmounts(module, label, amounts: tuple[Amount, ...], contexts: tuple[str, ...])` dengan `.get_amount(kode) -> Amount`.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/__init__.py` — file kosong.

`apps/posting/tests/test_catalog.py`:
```python
"""Unit tests untuk katalog angka."""
from django.test import TestCase

from apps.posting.catalog import (
    Amount, CatalogError, clear_catalog, get_amount, get_catalog, register_amounts,
)


class CatalogTests(TestCase):
    def tearDown(self):
        clear_catalog()

    def test_register_and_read_back(self):
        register_amounts(
            module='sales',
            label='Penjualan / Kasir',
            amounts=[
                Amount('subtotal', 'Subtotal Penjualan'),
                Amount('pembulatan', 'Pembulatan', signed=True),
            ],
            contexts=['entitas_bisnis', 'metode_bayar'],
        )
        catalog = get_catalog()
        self.assertIn('sales', catalog)
        self.assertEqual(catalog['sales'].label, 'Penjualan / Kasir')
        self.assertEqual(len(catalog['sales'].amounts), 2)
        self.assertEqual(catalog['sales'].contexts, ('entitas_bisnis', 'metode_bayar'))

    def test_get_amount_returns_definition(self):
        register_amounts(
            module='sales', label='Penjualan',
            amounts=[Amount('pembulatan', 'Pembulatan', signed=True)],
            contexts=[],
        )
        amount = get_amount('sales', 'pembulatan')
        self.assertEqual(amount.label, 'Pembulatan')
        self.assertTrue(amount.signed)

    def test_amount_defaults_to_unsigned(self):
        self.assertFalse(Amount('subtotal', 'Subtotal').signed)

    def test_register_duplicate_module_raises(self):
        register_amounts(module='sales', label='Penjualan', amounts=[], contexts=[])
        with self.assertRaises(CatalogError):
            register_amounts(module='sales', label='Lagi', amounts=[], contexts=[])

    def test_get_amount_unknown_module_raises(self):
        with self.assertRaises(CatalogError):
            get_amount('nope', 'subtotal')

    def test_get_amount_unknown_code_raises(self):
        register_amounts(
            module='sales', label='Penjualan',
            amounts=[Amount('subtotal', 'Subtotal')], contexts=[],
        )
        with self.assertRaises(CatalogError):
            get_amount('sales', 'tidak_ada')

    def test_get_catalog_is_snapshot(self):
        register_amounts(module='sales', label='Penjualan', amounts=[], contexts=[])
        snapshot = get_catalog()
        snapshot['injected'] = 'tidak boleh nempel'
        self.assertNotIn('injected', get_catalog())
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_catalog -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.posting.catalog'`

- [ ] **Step 3: Implementasi katalog**

`apps/posting/catalog.py`:
```python
"""Katalog angka yang diumumkan tiap modul domain.

Ini batas antara kode dan UI (spec §2): kode menyediakan ANGKA, superuser meracik
BARIS JURNAL lewat UI. Dropdown "angka" di UI hanya menampilkan isi katalog ini,
sehingga mustahil menyusun baris yang merujuk angka yang tidak ada.

Diisi oleh AppConfig.ready() tiap modul (mulai Tahap 1). Di Tahap 0 katalog kosong
di produksi — hanya tes yang mengisinya.
"""
from dataclasses import dataclass


class CatalogError(Exception):
    """Modul mendaftar dua kali, atau ada yang merujuk angka yang tak terdaftar."""


@dataclass(frozen=True)
class Amount:
    kode: str
    label: str
    signed: bool = False  # True = nilainya bisa negatif (pembulatan, selisih kas)


@dataclass(frozen=True)
class ModuleAmounts:
    module: str
    label: str
    amounts: tuple[Amount, ...]
    contexts: tuple[str, ...]

    def get_amount(self, kode: str) -> Amount:
        for a in self.amounts:
            if a.kode == kode:
                return a
        raise CatalogError(f"Angka '{kode}' tidak diumumkan oleh modul '{self.module}'.")


_CATALOG: dict[str, ModuleAmounts] = {}


def register_amounts(*, module: str, label: str, amounts: list, contexts: list) -> None:
    if module in _CATALOG:
        raise CatalogError(f"Modul '{module}' sudah terdaftar di katalog angka.")
    _CATALOG[module] = ModuleAmounts(
        module=module, label=label,
        amounts=tuple(amounts), contexts=tuple(contexts),
    )


def get_catalog() -> dict:
    return dict(_CATALOG)


def get_amount(module: str, kode: str) -> Amount:
    if module not in _CATALOG:
        raise CatalogError(f"Modul '{module}' tidak terdaftar di katalog angka.")
    return _CATALOG[module].get_amount(kode)


def clear_catalog() -> None:
    """Reset katalog. Khusus tes — jangan pernah dipanggil dari kode produksi."""
    _CATALOG.clear()
```

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_catalog -v 2`
Expected: `OK` (7 tes)

- [ ] **Step 5: Commit**

```bash
git add apps/posting/catalog.py apps/posting/tests/__init__.py apps/posting/tests/test_catalog.py
git commit -m "feat(posting): add amount catalog registry"
```

---

### Task 3: Model `JenisTransaksi`, `BarisJurnal`, `PemetaanAkun`

Spec §3.2–3.5. `PemetaanAkun` memakai **rantai scope** + **effective-dated**.

**Files:**
- Create: `apps/posting/constants.py`
- Create: `apps/posting/models.py`
- Create: `apps/posting/admin.py`
- Create: `apps/posting/migrations/0001_initial.py` (dihasilkan `makemigrations`)
- Create: `apps/posting/tests/test_models.py`

**Interfaces:**
- Produces konstanta: `ARAH_DEBIT='debit'`, `ARAH_KREDIT='kredit'`, `ARAH_BERTANDA='bertanda'`; `SUMBER_MAPPING='mapping'`, `SUMBER_DARI_ITEM='dari_item'`, `SUMBER_DARI_KONTEKS='dari_konteks'`, `SUMBER_DARI_MITRA='dari_mitra'`, `SUMBER_INPUT_USER='input_user'`; `SISI_NORMAL=''`, `SISI_DEBIT='debit'`, `SISI_KREDIT='kredit'`; `SPESIFISITAS: dict[str, int]` = `{'global': 0, 'entitas_bisnis': 10, 'lv2': 20, 'lv3': 30, 'metode_bayar': 40, 'alasan': 50}`.
- Produces model: `JenisTransaksi`, `BarisJurnal`, `PemetaanAkun`.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/test_models.py`:
```python
"""Unit tests untuk model Posting Engine."""
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.posting.constants import ARAH_KREDIT, SISI_NORMAL, SUMBER_MAPPING
from apps.posting.models import BarisJurnal, JenisTransaksi, PemetaanAkun


def _akun(kode='4.1.1', kategori='pendapatan', nama='Pendapatan'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=nama)


def _eb(nama='Klien A'):
    tipe = TipeEntitas.objects.create(nama=f'Tipe {nama}')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe)


def _jt(kode='penjualan_kasir'):
    return JenisTransaksi.objects.create(
        kode=kode, label='Penjualan Kasir', grup='Penjualan', module='sales',
    )


def _baris(jt, kode='pendapatan'):
    return BarisJurnal.objects.create(
        jenis_transaksi=jt, urutan=1, kode=kode, label='Pendapatan Barang Dagang',
        angka='subtotal', arah=ARAH_KREDIT, sumber_akun=SUMBER_MAPPING,
        kategori_akun=['pendapatan'],
    )


class JenisTransaksiTests(TestCase):
    def test_kode_unik(self):
        _jt('penjualan_kasir')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _jt('penjualan_kasir')

    def test_default_global_tanpa_entitas_bisnis(self):
        self.assertIsNone(_jt().entitas_bisnis)

    def test_default_aktif(self):
        self.assertTrue(_jt().aktif)


class BarisJurnalTests(TestCase):
    def test_kode_baris_unik_per_jenis_transaksi(self):
        jt = _jt()
        _baris(jt, 'pendapatan')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _baris(jt, 'pendapatan')

    def test_kode_baris_sama_boleh_di_jenis_transaksi_beda(self):
        _baris(_jt('jt_a'), 'pendapatan')
        _baris(_jt('jt_b'), 'pendapatan')
        self.assertEqual(BarisJurnal.objects.filter(kode='pendapatan').count(), 2)

    def test_default_lewati_bila_nol_true(self):
        self.assertTrue(_baris(_jt()).lewati_bila_nol)

    def test_kategori_akun_tersimpan_sebagai_list(self):
        self.assertEqual(_baris(_jt()).kategori_akun, ['pendapatan'])


class PemetaanAkunTests(TestCase):
    def setUp(self):
        self.baris = _baris(_jt())
        self.akun = _akun()

    def test_buat_pemetaan_global(self):
        p = PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        self.assertIsNone(p.scope_id)
        self.assertEqual(p.sisi, SISI_NORMAL)
        self.assertEqual(p.spesifisitas, 0)

    def test_spesifisitas_diisi_otomatis_dari_scope_tipe(self):
        eb = _eb()
        p = PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='entitas_bisnis', scope_id=eb.pk,
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        self.assertEqual(p.spesifisitas, 10)

    def test_duplikat_global_untuk_baris_sisi_tanggal_sama_ditolak(self):
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PemetaanAkun.objects.create(
                    baris_jurnal=self.baris, scope_tipe='global',
                    akun=_akun('4.1.2'), berlaku_mulai=date(2026, 1, 1),
                )

    def test_tanggal_berlaku_beda_boleh_coexist(self):
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=_akun('4.1.2'), berlaku_mulai=date(2026, 6, 1),
        )
        self.assertEqual(PemetaanAkun.objects.count(), 2)

    def test_global_dan_scope_eb_boleh_coexist(self):
        eb = _eb()
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='entitas_bisnis', scope_id=eb.pk,
            akun=_akun('4.1.2'), berlaku_mulai=date(2026, 1, 1),
        )
        self.assertEqual(PemetaanAkun.objects.count(), 2)

    def test_akun_terpakai_tidak_boleh_dihapus(self):
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        with self.assertRaises(ProtectedError):
            self.akun.delete()

    def test_hapus_baris_menghapus_pemetaannya(self):
        PemetaanAkun.objects.create(
            baris_jurnal=self.baris, scope_tipe='global',
            akun=self.akun, berlaku_mulai=date(2026, 1, 1),
        )
        self.baris.delete()
        self.assertEqual(PemetaanAkun.objects.count(), 0)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_models -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.posting.constants'`

- [ ] **Step 3: Implementasi konstanta**

`apps/posting/constants.py`:
```python
"""Konstanta Posting Engine — spec §3.3–3.5."""

# Arah baris jurnal
ARAH_DEBIT = 'debit'
ARAH_KREDIT = 'kredit'
ARAH_BERTANDA = 'bertanda'  # nilai positif -> sisi kredit; negatif -> sisi debit
ARAH_CHOICES = [
    (ARAH_DEBIT, 'Debit'),
    (ARAH_KREDIT, 'Kredit'),
    (ARAH_BERTANDA, 'Bertanda (+/-)'),
]

# Dari mana akun sebuah baris berasal
SUMBER_MAPPING = 'mapping'            # dari PemetaanAkun (di-setting superuser)
SUMBER_DARI_ITEM = 'dari_item'        # dari master item (Persediaan, HPP)
SUMBER_DARI_KONTEKS = 'dari_konteks'  # dari konteks transaksi (metode bayar)
SUMBER_DARI_MITRA = 'dari_mitra'      # dari customer/supplier
SUMBER_INPUT_USER = 'input_user'      # dipilih user per transaksi (per-record)
SUMBER_CHOICES = [
    (SUMBER_MAPPING, 'Dari Pemetaan Akun'),
    (SUMBER_DARI_ITEM, 'Dari Master Item'),
    (SUMBER_DARI_KONTEKS, 'Dari Konteks Transaksi'),
    (SUMBER_DARI_MITRA, 'Dari Mitra (Customer/Supplier)'),
    (SUMBER_INPUT_USER, 'Dipilih User per Transaksi'),
]

# Sisi pemetaan. Baris ARAH_BERTANDA punya DUA pemetaan (laba vs rugi = akun berbeda).
SISI_NORMAL = ''
SISI_DEBIT = 'debit'
SISI_KREDIT = 'kredit'
SISI_CHOICES = [
    (SISI_NORMAL, 'Normal'),
    (SISI_DEBIT, 'Bila Debit (nilai negatif)'),
    (SISI_KREDIT, 'Bila Kredit (nilai positif)'),
]

# Rantai scope. Angka lebih besar = lebih spesifik = menang saat resolve.
SPESIFISITAS = {
    'global': 0,
    'entitas_bisnis': 10,
    'lv2': 20,
    'lv3': 30,
    'metode_bayar': 40,
    'alasan': 50,
}
SCOPE_CHOICES = [(k, k) for k in SPESIFISITAS]

# scope_ref: scope mana yang dipakai me-resolve akun baris ini (mutasi antar cabang)
SCOPE_REF_DEFAULT = 'default'
SCOPE_REF_ASAL = 'asal'
SCOPE_REF_TUJUAN = 'tujuan'
SCOPE_REF_CHOICES = [
    (SCOPE_REF_DEFAULT, 'Default'),
    (SCOPE_REF_ASAL, 'Scope Asal'),
    (SCOPE_REF_TUJUAN, 'Scope Tujuan'),
]
```

- [ ] **Step 4: Implementasi model**

`apps/posting/models.py`:
```python
"""Model Posting Engine — spec §3.2-3.5.

JenisTransaksi  : disusun superuser lewat UI ("Penjualan Kasir F&B")
BarisJurnal     : resep SATU baris jurnal (angka + arah + sumber akun)
PemetaanAkun    : akun untuk satu baris, per scope, per tanggal berlaku
"""
from django.db import models
from django.db.models import Q

from .constants import (
    ARAH_CHOICES, SCOPE_CHOICES, SCOPE_REF_CHOICES, SCOPE_REF_DEFAULT,
    SISI_CHOICES, SISI_NORMAL, SPESIFISITAS, SUMBER_CHOICES, SUMBER_MAPPING,
)


class JenisTransaksi(models.Model):
    kode = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=150, verbose_name='Nama (bahasa bisnis)')
    grup = models.CharField(
        max_length=60,
        help_text='Label pengelompokan di UI, mis. "Aset Tetap". BUKAN nama app Django — '
                  'event boleh dipancarkan modul lain (perolehan aset dipancarkan purchase).',
    )
    module = models.CharField(
        max_length=50,
        help_text='Modul yang memancarkan event ini. Informasional; bukan bagian kunci.',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.CASCADE,
        null=True, blank=True, related_name='jenis_transaksi',
        help_text='Kosong = template global vendor. Terisi = khusus klien ini.',
    )
    aktif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Jenis Transaksi'
        verbose_name_plural = 'Jenis Transaksi'
        ordering = ['grup', 'label']

    def __str__(self) -> str:
        return self.label


class BarisJurnal(models.Model):
    jenis_transaksi = models.ForeignKey(
        JenisTransaksi, on_delete=models.CASCADE, related_name='baris',
    )
    urutan = models.IntegerField(default=0)
    kode = models.CharField(max_length=60)
    label = models.CharField(max_length=150, verbose_name='Nama (bahasa bisnis)')
    angka = models.CharField(
        max_length=60,
        help_text='Kode angka dari katalog modul (apps/posting/catalog.py).',
    )
    arah = models.CharField(max_length=10, choices=ARAH_CHOICES)
    sumber_akun = models.CharField(
        max_length=20, choices=SUMBER_CHOICES, default=SUMBER_MAPPING,
    )
    scope_ref = models.CharField(
        max_length=10, choices=SCOPE_REF_CHOICES, default=SCOPE_REF_DEFAULT,
    )
    lewati_bila_nol = models.BooleanField(
        default=True,
        help_text='Baris bernilai nol dihilangkan, tidak ditulis ke jurnal. '
                  'Inilah mekanisme "varian" (spec §7a): PPN/ongkos angkut yang tidak '
                  'berlaku cukup dikirim bernilai nol.',
    )
    wajib = models.BooleanField(default=True)
    kategori_akun = models.JSONField(
        default=list,
        help_text='Kategori CoA yang boleh dipilih, mis. ["pendapatan"]. '
                  'Boleh lebih dari satu (pembulatan: pendapatan ATAU beban).',
    )

    class Meta:
        verbose_name = 'Baris Jurnal'
        verbose_name_plural = 'Baris Jurnal'
        ordering = ['urutan', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['jenis_transaksi', 'kode'], name='uniq_baris_per_jenis_transaksi',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.jenis_transaksi.kode}.{self.kode} ({self.arah})'


class PemetaanAkun(models.Model):
    baris_jurnal = models.ForeignKey(
        BarisJurnal, on_delete=models.CASCADE, related_name='pemetaan',
    )
    sisi = models.CharField(
        max_length=10, choices=SISI_CHOICES, default=SISI_NORMAL, blank=True,
        help_text='Untuk baris BERTANDA: "kredit" dipakai saat nilai positif (Laba), '
                  '"debit" saat negatif (Rugi) — akun berbeda, bukan sekadar arah berbeda.',
    )
    scope_tipe = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='global')
    scope_id = models.BigIntegerField(
        null=True, blank=True,
        help_text='PK objek scope. NULL untuk scope_tipe=global. '
                  'Untuk scope_tipe=alasan, pakai scope_kode.',
    )
    scope_kode = models.CharField(
        max_length=60, blank=True, default='',
        help_text='Scope bernilai teks, mis. alasan="rusak".',
    )
    spesifisitas = models.IntegerField(
        default=0, db_index=True,
        help_text='Diisi otomatis dari scope_tipe. Resolver memilih yang tertinggi.',
    )
    akun = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, related_name='+',
    )
    berlaku_mulai = models.DateField(
        help_text='Effective-dated: mengubah pemetaan TIDAK mengubah arti jurnal '
                  'yang sudah terbit.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pemetaan Akun'
        verbose_name_plural = 'Pemetaan Akun'
        indexes = [
            models.Index(
                fields=['baris_jurnal', 'sisi', 'berlaku_mulai'], name='idx_pemetaan_lookup',
            ),
        ]
        constraints = [
            # scope_id non-null: uniqueness SQL biasa berlaku.
            models.UniqueConstraint(
                fields=['baris_jurnal', 'sisi', 'scope_tipe', 'scope_id', 'scope_kode',
                        'berlaku_mulai'],
                name='uniq_pemetaan_per_scope',
            ),
            # Baris scope global punya scope_id NULL — dan SQL memperlakukan NULL != NULL,
            # sehingga constraint di atas TIDAK menangkapnya. Butuh partial unique index.
            models.UniqueConstraint(
                fields=['baris_jurnal', 'sisi', 'scope_tipe', 'scope_kode', 'berlaku_mulai'],
                condition=Q(scope_id__isnull=True),
                name='uniq_pemetaan_global',
            ),
        ]

    def save(self, *args, **kwargs):
        self.spesifisitas = SPESIFISITAS.get(self.scope_tipe, 0)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        scope = self.scope_tipe if self.scope_tipe == 'global' else (
            f'{self.scope_tipe}={self.scope_id or self.scope_kode}'
        )
        return f'{self.baris_jurnal} [{scope} @ {self.berlaku_mulai}] -> {self.akun}'
```

`apps/posting/admin.py`:
```python
from django.contrib import admin

from .models import BarisJurnal, JenisTransaksi, PemetaanAkun


class BarisJurnalInline(admin.TabularInline):
    model = BarisJurnal
    extra = 0


@admin.register(JenisTransaksi)
class JenisTransaksiAdmin(admin.ModelAdmin):
    list_display = ('kode', 'label', 'grup', 'module', 'entitas_bisnis', 'aktif')
    list_filter = ('grup', 'module', 'aktif')
    search_fields = ('kode', 'label')
    inlines = [BarisJurnalInline]


@admin.register(PemetaanAkun)
class PemetaanAkunAdmin(admin.ModelAdmin):
    list_display = (
        'baris_jurnal', 'sisi', 'scope_tipe', 'scope_id', 'scope_kode',
        'spesifisitas', 'akun', 'berlaku_mulai',
    )
    list_filter = ('scope_tipe', 'sisi')
    list_select_related = ('baris_jurnal', 'akun')
    raw_id_fields = ('baris_jurnal', 'akun')
```

- [ ] **Step 5: Buat & periksa migrasi**

Run: `python manage.py makemigrations posting`
Expected: `Migrations for 'posting': apps/posting/migrations/0001_initial.py` membuat `JenisTransaksi`, `BarisJurnal`, `PemetaanAkun`. Buka file yang dihasilkan dan pastikan **kedua** `UniqueConstraint` pada `PemetaanAkun` ada, dan yang bernama `uniq_pemetaan_global` punya `condition=models.Q(scope_id__isnull=True)`.

Run: `python manage.py migrate posting`
Expected: `Applying posting.0001_initial... OK`

- [ ] **Step 6: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_models -v 2`
Expected: `OK` (13 tes)

- [ ] **Step 7: Commit**

```bash
git add apps/posting/constants.py apps/posting/models.py apps/posting/admin.py apps/posting/migrations/0001_initial.py apps/posting/tests/test_models.py
git commit -m "feat(posting): add JenisTransaksi, BarisJurnal, PemetaanAkun models"
```

---

### Task 4: Resolver — rantai scope + effective-dated

Spec §4. Satu-satunya pintu baca pemetaan akun.

**Files:**
- Create: `apps/posting/resolver.py`
- Create: `apps/posting/tests/test_resolver.py`

**Interfaces:**
- Consumes: `apps.posting.models.PemetaanAkun`, `apps.posting.constants`.
- Produces: `resolve_akun(baris, konteks: dict, tanggal, sisi=SISI_NORMAL, *, fallback=None) -> Akun`; exception `PemetaanTidakAdaError(Exception)`.
- `konteks` adalah dict, mis. `{'entitas_bisnis': 3, 'lv3': 9, 'metode_bayar': 2, 'alasan': 'rusak'}`. Kunci yang tidak ada di konteks diabaikan.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/test_resolver.py`:
```python
"""Unit tests untuk resolve_akun — rantai scope + effective-dated."""
from datetime import date

from django.test import TestCase

from apps.master_data.models import Akun
from apps.posting.constants import (
    ARAH_BERTANDA, ARAH_KREDIT, SISI_DEBIT, SISI_KREDIT, SISI_NORMAL, SUMBER_MAPPING,
)
from apps.posting.models import BarisJurnal, JenisTransaksi, PemetaanAkun
from apps.posting.resolver import PemetaanTidakAdaError, resolve_akun


def _akun(kode, kategori='pendapatan'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


def _baris(arah=ARAH_KREDIT):
    jt = JenisTransaksi.objects.create(
        kode='penjualan', label='Penjualan', grup='Penjualan', module='sales',
    )
    return BarisJurnal.objects.create(
        jenis_transaksi=jt, urutan=1, kode='pendapatan', label='Pendapatan',
        angka='subtotal', arah=arah, sumber_akun=SUMBER_MAPPING,
        kategori_akun=['pendapatan'],
    )


def _petakan(baris, akun, scope_tipe='global', scope_id=None, scope_kode='',
             sisi=SISI_NORMAL, berlaku_mulai=date(2026, 1, 1)):
    return PemetaanAkun.objects.create(
        baris_jurnal=baris, akun=akun, scope_tipe=scope_tipe, scope_id=scope_id,
        scope_kode=scope_kode, sisi=sisi, berlaku_mulai=berlaku_mulai,
    )


class ResolveAkunTests(TestCase):
    def setUp(self):
        self.baris = _baris()
        self.tanggal = date(2026, 7, 15)

    def test_pakai_global_bila_tak_ada_override(self):
        akun = _akun('4.1.1')
        _petakan(self.baris, akun)
        self.assertEqual(resolve_akun(self.baris, {}, self.tanggal), akun)

    def test_scope_eb_menang_atas_global(self):
        global_akun = _akun('4.1.1')
        eb_akun = _akun('4.1.2')
        _petakan(self.baris, global_akun)
        _petakan(self.baris, eb_akun, scope_tipe='entitas_bisnis', scope_id=7)
        hasil = resolve_akun(self.baris, {'entitas_bisnis': 7}, self.tanggal)
        self.assertEqual(hasil, eb_akun)

    def test_scope_lebih_spesifik_menang(self):
        eb_akun = _akun('4.1.1')
        lv3_akun = _akun('4.1.2')
        _petakan(self.baris, eb_akun, scope_tipe='entitas_bisnis', scope_id=7)
        _petakan(self.baris, lv3_akun, scope_tipe='lv3', scope_id=9)
        hasil = resolve_akun(self.baris, {'entitas_bisnis': 7, 'lv3': 9}, self.tanggal)
        self.assertEqual(hasil, lv3_akun)

    def test_scope_yang_tak_cocok_konteks_diabaikan(self):
        global_akun = _akun('4.1.1')
        eb_lain = _akun('4.1.2')
        _petakan(self.baris, global_akun)
        _petakan(self.baris, eb_lain, scope_tipe='entitas_bisnis', scope_id=99)
        hasil = resolve_akun(self.baris, {'entitas_bisnis': 7}, self.tanggal)
        self.assertEqual(hasil, global_akun)

    def test_scope_bernilai_teks_alasan(self):
        umum = _akun('5.1.1', 'beban')
        rusak = _akun('5.1.2', 'beban')
        _petakan(self.baris, umum)
        _petakan(self.baris, rusak, scope_tipe='alasan', scope_kode='rusak')
        self.assertEqual(resolve_akun(self.baris, {'alasan': 'rusak'}, self.tanggal), rusak)
        self.assertEqual(resolve_akun(self.baris, {'alasan': 'hilang'}, self.tanggal), umum)

    def test_effective_date_memilih_yang_berlaku_pada_tanggal_jurnal(self):
        lama = _akun('4.1.1')
        baru = _akun('4.1.2')
        _petakan(self.baris, lama, berlaku_mulai=date(2026, 1, 1))
        _petakan(self.baris, baru, berlaku_mulai=date(2026, 6, 1))
        self.assertEqual(resolve_akun(self.baris, {}, date(2026, 3, 1)), lama)
        self.assertEqual(resolve_akun(self.baris, {}, date(2026, 7, 15)), baru)

    def test_pemetaan_yang_belum_berlaku_diabaikan(self):
        lama = _akun('4.1.1')
        _petakan(self.baris, lama, berlaku_mulai=date(2026, 1, 1))
        _petakan(self.baris, _akun('4.1.2'), berlaku_mulai=date(2027, 1, 1))
        self.assertEqual(resolve_akun(self.baris, {}, date(2026, 7, 15)), lama)

    def test_baris_bertanda_positif_pakai_akun_sisi_kredit(self):
        baris = _baris(arah=ARAH_BERTANDA)
        laba = _akun('4.9.1', 'pendapatan')
        rugi = _akun('5.9.1', 'beban')
        _petakan(baris, laba, sisi=SISI_KREDIT)
        _petakan(baris, rugi, sisi=SISI_DEBIT)
        self.assertEqual(resolve_akun(baris, {}, self.tanggal, sisi=SISI_KREDIT), laba)

    def test_baris_bertanda_negatif_pakai_akun_sisi_debit(self):
        baris = _baris(arah=ARAH_BERTANDA)
        laba = _akun('4.9.1', 'pendapatan')
        rugi = _akun('5.9.1', 'beban')
        _petakan(baris, laba, sisi=SISI_KREDIT)
        _petakan(baris, rugi, sisi=SISI_DEBIT)
        self.assertEqual(resolve_akun(baris, {}, self.tanggal, sisi=SISI_DEBIT), rugi)

    def test_tanpa_pemetaan_dan_tanpa_fallback_raise(self):
        with self.assertRaises(PemetaanTidakAdaError):
            resolve_akun(self.baris, {}, self.tanggal)

    def test_pesan_error_menyebut_label_baris(self):
        with self.assertRaises(PemetaanTidakAdaError) as ctx:
            resolve_akun(self.baris, {}, self.tanggal)
        self.assertIn('Pendapatan', str(ctx.exception))

    def test_fallback_dipakai_bila_pemetaan_kosong(self):
        akun = _akun('4.1.1')
        hasil = resolve_akun(self.baris, {}, self.tanggal, fallback=lambda: akun)
        self.assertEqual(hasil, akun)

    def test_pemetaan_menang_atas_fallback(self):
        dipetakan = _akun('4.1.1')
        cadangan = _akun('4.1.9')
        _petakan(self.baris, dipetakan)
        hasil = resolve_akun(self.baris, {}, self.tanggal, fallback=lambda: cadangan)
        self.assertEqual(hasil, dipetakan)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_resolver -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.posting.resolver'`

- [ ] **Step 3: Implementasi resolver**

`apps/posting/resolver.py`:
```python
"""Satu-satunya pintu baca pemetaan akun — spec §4.

Urutan: scope paling spesifik yang cocok konteks & berlaku pada tanggal jurnal
-> ... -> global -> fallback (masa transisi) -> error yang jelas.

Effective-dated: pemetaan dipilih berdasarkan TANGGAL JURNAL, bukan "yang terbaru".
Mengubah pemetaan hari ini tidak boleh mengubah arti jurnal bulan lalu.
"""
from .constants import SISI_NORMAL
from .models import PemetaanAkun


class PemetaanTidakAdaError(Exception):
    """Baris wajib tidak punya pemetaan akun, dan tidak ada fallback."""


def _cocok_konteks(pemetaan, konteks: dict) -> bool:
    if pemetaan.scope_tipe == 'global':
        return True
    nilai = konteks.get(pemetaan.scope_tipe)
    if nilai is None:
        return False
    if pemetaan.scope_kode:
        return str(nilai) == pemetaan.scope_kode
    return pemetaan.scope_id == nilai


def resolve_akun(baris, konteks: dict, tanggal, sisi: str = SISI_NORMAL, *, fallback=None):
    """Akun untuk satu baris jurnal, pada satu konteks, pada satu tanggal.

    Raise PemetaanTidakAdaError bila tidak ada pemetaan dan fallback None.
    """
    kandidat = (
        PemetaanAkun.objects
        .filter(baris_jurnal=baris, sisi=sisi, berlaku_mulai__lte=tanggal)
        .select_related('akun')
        .order_by('-spesifisitas', '-berlaku_mulai')
    )

    for pemetaan in kandidat:
        if _cocok_konteks(pemetaan, konteks):
            return pemetaan.akun

    if fallback is not None:
        akun = fallback()
        if akun is not None:
            return akun

    raise PemetaanTidakAdaError(
        f"Akun untuk '{baris.label}' ({baris.jenis_transaksi.label}) belum di-set."
    )
```

> **Catatan untuk pelaksana:** `order_by('-spesifisitas', '-berlaku_mulai')` lalu ambil yang **pertama cocok** memberi dua hal sekaligus — scope paling spesifik menang, dan di antara pemetaan pada scope yang sama, yang tanggal berlakunya paling akhir (tapi tidak melewati tanggal jurnal) yang menang.

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_resolver -v 2`
Expected: `OK` (13 tes)

- [ ] **Step 5: Commit**

```bash
git add apps/posting/resolver.py apps/posting/tests/test_resolver.py
git commit -m "feat(posting): add resolve_akun with scope chain and effective dating"
```

---

### Task 5: Poster — bentuk baris jurnal, lewati nol, cek balance

Spec §4–5. Poster **tidak menulis** `JurnalDetail`; ia mengembalikan **rencana** baris. Modul yang menulis (Tahap 1+).

**Files:**
- Create: `apps/posting/poster.py`
- Create: `apps/posting/tests/test_poster.py`

**Interfaces:**
- Consumes: `apps.posting.resolver.resolve_akun`, `apps.posting.constants`.
- Produces: `BarisTerisi` (dataclass: `kode`, `label`, `akun`, `debit: Decimal`, `kredit: Decimal`); `bangun_baris_jurnal(jenis_transaksi, angka: dict, konteks: dict, tanggal, *, akun_eksternal: dict | None = None) -> list[BarisTerisi]`; `cek_balance(baris_terisi) -> None` (raise `TidakBalanceError`); exceptions `TidakBalanceError`, `AkunEksternalHilangError`.
- `akun_eksternal`: dict `{kode_baris: Akun}` untuk baris ber-`sumber_akun` selain `MAPPING` (Persediaan dari master item, Kas dari metode bayar, dst). Modul yang menyediakannya.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/test_poster.py`:
```python
"""Unit tests untuk poster — pembentuk baris jurnal."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.master_data.models import Akun
from apps.posting.constants import (
    ARAH_BERTANDA, ARAH_DEBIT, ARAH_KREDIT, SISI_DEBIT, SISI_KREDIT, SISI_NORMAL,
    SUMBER_DARI_ITEM, SUMBER_MAPPING,
)
from apps.posting.models import BarisJurnal, JenisTransaksi, PemetaanAkun
from apps.posting.poster import (
    AkunEksternalHilangError, TidakBalanceError, bangun_baris_jurnal, cek_balance,
)
from apps.posting.resolver import PemetaanTidakAdaError

TANGGAL = date(2026, 7, 15)


def _akun(kode, kategori='pendapatan'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


def _jt():
    return JenisTransaksi.objects.create(
        kode='penjualan', label='Penjualan Kasir', grup='Penjualan', module='sales',
    )


def _baris(jt, kode, angka, arah, urutan=1, sumber=SUMBER_MAPPING, lewati_bila_nol=True):
    return BarisJurnal.objects.create(
        jenis_transaksi=jt, urutan=urutan, kode=kode, label=kode.title(),
        angka=angka, arah=arah, sumber_akun=sumber,
        lewati_bila_nol=lewati_bila_nol, kategori_akun=['pendapatan'],
    )


def _petakan(baris, akun, sisi=SISI_NORMAL):
    return PemetaanAkun.objects.create(
        baris_jurnal=baris, akun=akun, scope_tipe='global', sisi=sisi,
        berlaku_mulai=date(2026, 1, 1),
    )


class BangunBarisJurnalTests(TestCase):
    def test_baris_kredit_dan_debit_terbentuk(self):
        jt = _jt()
        kas = _akun('1.1.1', 'aset')
        pendapatan = _akun('4.1.1')
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT, urutan=1), kas)
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, urutan=2), pendapatan)

        hasil = bangun_baris_jurnal(
            jt,
            angka={'nilai_bayar': Decimal('100000'), 'subtotal': Decimal('100000')},
            konteks={}, tanggal=TANGGAL,
        )

        self.assertEqual(len(hasil), 2)
        self.assertEqual(hasil[0].akun, kas)
        self.assertEqual(hasil[0].debit, Decimal('100000'))
        self.assertEqual(hasil[0].kredit, Decimal('0'))
        self.assertEqual(hasil[1].akun, pendapatan)
        self.assertEqual(hasil[1].kredit, Decimal('100000'))

    def test_baris_bernilai_nol_dilewati(self):
        """Inilah mekanisme 'varian' (spec §7a): PPN nol -> barisnya lenyap."""
        jt = _jt()
        kas = _akun('1.1.1', 'aset')
        pendapatan = _akun('4.1.1')
        ppn = _akun('2.1.1', 'kewajiban')
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT, urutan=1), kas)
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, urutan=2), pendapatan)
        _petakan(_baris(jt, 'ppn', 'pajak', ARAH_KREDIT, urutan=3), ppn)

        hasil = bangun_baris_jurnal(
            jt,
            angka={
                'nilai_bayar': Decimal('100000'),
                'subtotal': Decimal('100000'),
                'pajak': Decimal('0'),
            },
            konteks={}, tanggal=TANGGAL,
        )

        self.assertEqual(len(hasil), 2)
        self.assertNotIn(ppn, [b.akun for b in hasil])

    def test_baris_nol_tetap_ditulis_bila_lewati_bila_nol_false(self):
        jt = _jt()
        pendapatan = _akun('4.1.1')
        _petakan(
            _baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, lewati_bila_nol=False),
            pendapatan,
        )
        hasil = bangun_baris_jurnal(
            jt, angka={'subtotal': Decimal('0')}, konteks={}, tanggal=TANGGAL,
        )
        self.assertEqual(len(hasil), 1)

    def test_angka_tak_dikirim_dianggap_nol(self):
        jt = _jt()
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT), _akun('4.1.1'))
        hasil = bangun_baris_jurnal(jt, angka={}, konteks={}, tanggal=TANGGAL)
        self.assertEqual(hasil, [])

    def test_jenis_transaksi_tanpa_baris_menghasilkan_nol_baris(self):
        """Nol baris adalah hasil yang SAH (spec §5.3), bukan error."""
        hasil = bangun_baris_jurnal(_jt(), angka={}, konteks={}, tanggal=TANGGAL)
        self.assertEqual(hasil, [])

    def test_bertanda_positif_masuk_kredit_dengan_akun_laba(self):
        jt = _jt()
        baris = _baris(jt, 'pembulatan', 'pembulatan', ARAH_BERTANDA)
        laba = _akun('4.9.1', 'pendapatan')
        rugi = _akun('5.9.1', 'beban')
        _petakan(baris, laba, sisi=SISI_KREDIT)
        _petakan(baris, rugi, sisi=SISI_DEBIT)

        hasil = bangun_baris_jurnal(
            jt, angka={'pembulatan': Decimal('50')}, konteks={}, tanggal=TANGGAL,
        )
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0].akun, laba)
        self.assertEqual(hasil[0].kredit, Decimal('50'))
        self.assertEqual(hasil[0].debit, Decimal('0'))

    def test_bertanda_negatif_masuk_debit_dengan_akun_rugi(self):
        jt = _jt()
        baris = _baris(jt, 'pembulatan', 'pembulatan', ARAH_BERTANDA)
        laba = _akun('4.9.1', 'pendapatan')
        rugi = _akun('5.9.1', 'beban')
        _petakan(baris, laba, sisi=SISI_KREDIT)
        _petakan(baris, rugi, sisi=SISI_DEBIT)

        hasil = bangun_baris_jurnal(
            jt, angka={'pembulatan': Decimal('-50')}, konteks={}, tanggal=TANGGAL,
        )
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0].akun, rugi)
        self.assertEqual(hasil[0].debit, Decimal('50'))
        self.assertEqual(hasil[0].kredit, Decimal('0'))

    def test_sumber_akun_eksternal_dipakai(self):
        """Persediaan/HPP datang dari master item, BUKAN dari pemetaan (spec §3.5)."""
        jt = _jt()
        _baris(jt, 'persediaan', 'hpp', ARAH_KREDIT, sumber=SUMBER_DARI_ITEM)
        persediaan = _akun('1.3.1', 'aset')

        hasil = bangun_baris_jurnal(
            jt, angka={'hpp': Decimal('60000')}, konteks={}, tanggal=TANGGAL,
            akun_eksternal={'persediaan': persediaan},
        )
        self.assertEqual(hasil[0].akun, persediaan)

    def test_sumber_eksternal_tanpa_akun_raise(self):
        jt = _jt()
        _baris(jt, 'persediaan', 'hpp', ARAH_KREDIT, sumber=SUMBER_DARI_ITEM)
        with self.assertRaises(AkunEksternalHilangError):
            bangun_baris_jurnal(
                jt, angka={'hpp': Decimal('60000')}, konteks={}, tanggal=TANGGAL,
            )

    def test_baris_mapping_tanpa_pemetaan_raise(self):
        jt = _jt()
        _baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT)
        with self.assertRaises(PemetaanTidakAdaError):
            bangun_baris_jurnal(
                jt, angka={'subtotal': Decimal('100000')}, konteks={}, tanggal=TANGGAL,
            )

    def test_baris_diurutkan_sesuai_urutan(self):
        jt = _jt()
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, urutan=2), _akun('4.1.1'))
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT, urutan=1), _akun('1.1.1', 'aset'))
        hasil = bangun_baris_jurnal(
            jt,
            angka={'subtotal': Decimal('100000'), 'nilai_bayar': Decimal('100000')},
            konteks={}, tanggal=TANGGAL,
        )
        self.assertEqual([b.kode for b in hasil], ['kas', 'pendapatan'])


class CekBalanceTests(TestCase):
    def test_balance_lolos(self):
        jt = _jt()
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT, urutan=1), _akun('1.1.1', 'aset'))
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, urutan=2), _akun('4.1.1'))
        hasil = bangun_baris_jurnal(
            jt,
            angka={'nilai_bayar': Decimal('100000'), 'subtotal': Decimal('100000')},
            konteks={}, tanggal=TANGGAL,
        )
        cek_balance(hasil)  # tidak raise

    def test_tidak_balance_ditolak(self):
        """Angka yang tidak dipasangkan ke baris manapun tertangkap di sini.

        Kasir menagih service charge, tapi barisnya lupa dipasang -> jurnal tidak
        balance -> DITOLAK, bukan diam-diam salah (spec §5.1).
        """
        jt = _jt()
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT, urutan=1), _akun('1.1.1', 'aset'))
        _petakan(_baris(jt, 'pendapatan', 'subtotal', ARAH_KREDIT, urutan=2), _akun('4.1.1'))
        hasil = bangun_baris_jurnal(
            jt,
            angka={'nilai_bayar': Decimal('105000'), 'subtotal': Decimal('100000')},
            konteks={}, tanggal=TANGGAL,
        )
        with self.assertRaises(TidakBalanceError):
            cek_balance(hasil)

    def test_nol_baris_dianggap_balance(self):
        cek_balance([])  # tidak raise

    def test_pesan_error_menyebut_selisih(self):
        jt = _jt()
        _petakan(_baris(jt, 'kas', 'nilai_bayar', ARAH_DEBIT), _akun('1.1.1', 'aset'))
        hasil = bangun_baris_jurnal(
            jt, angka={'nilai_bayar': Decimal('5000')}, konteks={}, tanggal=TANGGAL,
        )
        with self.assertRaises(TidakBalanceError) as ctx:
            cek_balance(hasil)
        self.assertIn('5000', str(ctx.exception))
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_poster -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.posting.poster'`

- [ ] **Step 3: Implementasi poster**

`apps/posting/poster.py`:
```python
"""Pembentuk baris jurnal — spec §4-5.

Poster TIDAK menulis JurnalDetail. Ia mengembalikan RENCANA baris; modul yang
menulis (spec §7.4: modul tetap pemilik penulisan jurnal). Ini yang membuat
Tahap 0 nol risiko.

Menggantikan blok hardcoded seperti create_sales_automated_journals (yang hari ini
hanya mengenal HPP & Pendapatan) dengan perulangan atas konfigurasi.
"""
from dataclasses import dataclass
from decimal import Decimal

from .constants import (
    ARAH_BERTANDA, ARAH_DEBIT, SISI_DEBIT, SISI_KREDIT, SISI_NORMAL, SUMBER_MAPPING,
)
from .resolver import resolve_akun

NOL = Decimal('0')


class TidakBalanceError(Exception):
    """Total debit != total kredit."""


class AkunEksternalHilangError(Exception):
    """Baris ber-sumber_akun non-mapping tapi modul tidak menyediakan akunnya."""


@dataclass(frozen=True)
class BarisTerisi:
    kode: str
    label: str
    akun: object
    debit: Decimal
    kredit: Decimal


def _akun_untuk(baris, konteks, tanggal, nilai, akun_eksternal):
    if baris.sumber_akun != SUMBER_MAPPING:
        akun = akun_eksternal.get(baris.kode)
        if akun is None:
            raise AkunEksternalHilangError(
                f"Baris '{baris.label}' bersumber '{baris.sumber_akun}', "
                f"tetapi akunnya tidak disediakan modul."
            )
        return akun

    if baris.arah == ARAH_BERTANDA:
        sisi = SISI_KREDIT if nilai >= NOL else SISI_DEBIT
    else:
        sisi = SISI_NORMAL
    return resolve_akun(baris, konteks, tanggal, sisi=sisi)


def bangun_baris_jurnal(jenis_transaksi, angka: dict, konteks: dict, tanggal, *,
                        akun_eksternal: dict | None = None) -> list[BarisTerisi]:
    """Rencana baris jurnal untuk satu jenis transaksi.

    angka           : {'subtotal': Decimal('100000'), ...} — dari modul
    konteks         : {'entitas_bisnis': 3, 'metode_bayar': 2, 'alasan': 'rusak'}
    akun_eksternal  : {'persediaan': <Akun>} — untuk baris non-mapping
    """
    akun_eksternal = akun_eksternal or {}
    hasil: list[BarisTerisi] = []

    for baris in jenis_transaksi.baris.all():
        nilai = angka.get(baris.angka, NOL)
        if nilai == NOL and baris.lewati_bila_nol:
            continue

        akun = _akun_untuk(baris, konteks, tanggal, nilai, akun_eksternal)

        if baris.arah == ARAH_BERTANDA:
            besaran = abs(nilai)
            if nilai >= NOL:
                debit, kredit = NOL, besaran
            else:
                debit, kredit = besaran, NOL
        elif baris.arah == ARAH_DEBIT:
            debit, kredit = nilai, NOL
        else:
            debit, kredit = NOL, nilai

        hasil.append(BarisTerisi(
            kode=baris.kode, label=baris.label, akun=akun, debit=debit, kredit=kredit,
        ))

    return hasil


def cek_balance(baris_terisi) -> None:
    """Raise TidakBalanceError bila total debit != total kredit.

    Nol baris dianggap balance (spec §5.3 — mutasi antar cabang dengan akun
    persediaan yang sama menghasilkan nol baris; itu SAH, bukan error).
    """
    total_debit = sum((b.debit for b in baris_terisi), NOL)
    total_kredit = sum((b.kredit for b in baris_terisi), NOL)
    if total_debit != total_kredit:
        selisih = abs(total_debit - total_kredit)
        raise TidakBalanceError(
            f'Jurnal tidak balance: debit {total_debit} vs kredit {total_kredit} '
            f'(selisih {selisih}). Kemungkinan ada angka yang belum dipasangkan ke '
            f'baris jurnal manapun.'
        )
```

- [ ] **Step 4: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_poster -v 2`
Expected: `OK` (15 tes)

- [ ] **Step 5: Commit**

```bash
git add apps/posting/poster.py apps/posting/tests/test_poster.py
git commit -m "feat(posting): add poster with zero-skip, signed lines, balance check"
```

---

### Task 6: Views — daftar jenis transaksi & simpan pemetaan (superuser-only)

Spec §6. **Superuser saja** — bukan `has_ni_perm`.

**Files:**
- Create: `apps/posting/forms.py`
- Create: `apps/posting/views.py`
- Modify: `apps/posting/urls.py`
- Create: `apps/posting/tests/test_views.py`

**Interfaces:**
- Produces: `_require_superuser(request) -> HttpResponse | None`; view `daftar_jenis_transaksi` (GET, `posting:daftar`); view `detail_jenis_transaksi` (GET, `posting:detail`, arg `pk`); view `simpan_pemetaan` (POST AJAX, `posting:simpan_pemetaan`); form `PemetaanAkunForm`.
- Konteks template `detail_jenis_transaksi`: `jenis_transaksi`, `baris_list` (tiap item: `baris`, `pemetaan_per_sisi`, `akun_choices`), `scope_tipe`, `scope_id`.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/test_views.py`:
```python
"""Unit tests untuk view Posting Engine (superuser-only)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.master_data.models import Akun
from apps.posting.constants import ARAH_KREDIT, SISI_NORMAL, SUMBER_MAPPING
from apps.posting.models import BarisJurnal, JenisTransaksi, PemetaanAkun

User = get_user_model()


def _akun(kode, kategori='pendapatan'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


def _jt():
    return JenisTransaksi.objects.create(
        kode='penjualan', label='Penjualan Kasir', grup='Penjualan', module='sales',
    )


def _baris(jt):
    return BarisJurnal.objects.create(
        jenis_transaksi=jt, urutan=1, kode='pendapatan',
        label='Pendapatan Barang Dagang', angka='subtotal', arah=ARAH_KREDIT,
        sumber_akun=SUMBER_MAPPING, kategori_akun=['pendapatan'],
    )


class AksesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.jt = _jt()

    def test_anonim_dialihkan_ke_login(self):
        self.assertEqual(self.client.get(reverse('posting:daftar')).status_code, 302)

    def test_user_biasa_ditolak(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('posting:daftar')).status_code, 403)

    def test_superuser_boleh(self):
        su = User.objects.create_superuser(email='su@test.com', password='pass', name='SU')
        self.client.force_login(su)
        self.assertEqual(self.client.get(reverse('posting:daftar')).status_code, 200)

    def test_detail_ditolak_untuk_user_biasa(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        self.client.force_login(user)
        url = reverse('posting:detail', args=[self.jt.pk])
        self.assertEqual(self.client.get(url).status_code, 403)


class DaftarTests(TestCase):
    def setUp(self):
        self.client = Client()
        su = User.objects.create_superuser(email='su@test.com', password='pass', name='SU')
        self.client.force_login(su)

    def test_menampilkan_jenis_transaksi(self):
        _jt()
        response = self.client.get(reverse('posting:daftar'))
        self.assertContains(response, 'Penjualan Kasir')


class DetailTests(TestCase):
    def setUp(self):
        self.client = Client()
        su = User.objects.create_superuser(email='su@test.com', password='pass', name='SU')
        self.client.force_login(su)
        self.jt = _jt()
        self.baris = _baris(self.jt)

    def test_menampilkan_label_baris(self):
        response = self.client.get(reverse('posting:detail', args=[self.jt.pk]))
        self.assertContains(response, 'Pendapatan Barang Dagang')

    def test_dropdown_akun_difilter_kategori_baris(self):
        _akun('4.1.1', 'pendapatan')
        _akun('1.1.1', 'aset')
        response = self.client.get(reverse('posting:detail', args=[self.jt.pk]))
        content = response.content.decode()
        self.assertIn('4.1.1', content)
        self.assertNotIn('1.1.1', content)


class SimpanPemetaanTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.su = User.objects.create_superuser(email='su@test.com', password='pass', name='SU')
        self.jt = _jt()
        self.baris = _baris(self.jt)
        self.akun = _akun('4.1.1')

    def _post(self, **overrides):
        data = {
            'baris_jurnal': self.baris.pk,
            'sisi': SISI_NORMAL,
            'scope_tipe': 'global',
            'akun': self.akun.pk,
            'berlaku_mulai': '2026-01-01',
        }
        data.update(overrides)
        return self.client.post(
            reverse('posting:simpan_pemetaan'), data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_user_biasa_ditolak(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        self.client.force_login(user)
        self.assertEqual(self._post().status_code, 403)

    def test_membuat_pemetaan_global(self):
        self.client.force_login(self.su)
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        p = PemetaanAkun.objects.get(baris_jurnal=self.baris)
        self.assertEqual(p.akun, self.akun)
        self.assertEqual(p.scope_tipe, 'global')
        self.assertIsNone(p.scope_id)
        self.assertEqual(p.spesifisitas, 0)

    def test_upsert_pada_scope_dan_tanggal_yang_sama(self):
        self.client.force_login(self.su)
        self._post()
        akun2 = _akun('4.1.2')
        self._post(akun=akun2.pk)
        qs = PemetaanAkun.objects.filter(baris_jurnal=self.baris)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().akun, akun2)

    def test_tanggal_berlaku_baru_membuat_baris_riwayat_baru(self):
        """Effective-dated: pemetaan lama TIDAK ditimpa (spec §5.4)."""
        self.client.force_login(self.su)
        self._post()
        akun2 = _akun('4.1.2')
        self._post(akun=akun2.pk, berlaku_mulai='2026-06-01')
        self.assertEqual(PemetaanAkun.objects.filter(baris_jurnal=self.baris).count(), 2)

    def test_pemetaan_scope_entitas_bisnis(self):
        self.client.force_login(self.su)
        response = self._post(scope_tipe='entitas_bisnis', scope_id=7)
        self.assertTrue(response.json()['success'])
        p = PemetaanAkun.objects.get(baris_jurnal=self.baris)
        self.assertEqual(p.scope_id, 7)
        self.assertEqual(p.spesifisitas, 10)

    def test_akun_di_luar_kategori_baris_ditolak(self):
        self.client.force_login(self.su)
        akun_salah = _akun('1.1.1', 'aset')
        response = self._post(akun=akun_salah.pk)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertIn('akun', body['errors'])
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_views -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.posting.views'`

- [ ] **Step 3: Implementasi form**

`apps/posting/forms.py`:
```python
"""Form untuk halaman Posting Engine."""
from django import forms

from apps.master_data.models import Akun

from .constants import SCOPE_CHOICES, SISI_CHOICES, SISI_NORMAL
from .models import BarisJurnal


class PemetaanAkunForm(forms.Form):
    baris_jurnal = forms.ModelChoiceField(queryset=BarisJurnal.objects.all())
    sisi = forms.ChoiceField(choices=SISI_CHOICES, required=False, initial=SISI_NORMAL)
    scope_tipe = forms.ChoiceField(choices=SCOPE_CHOICES)
    scope_id = forms.IntegerField(required=False)
    scope_kode = forms.CharField(max_length=60, required=False)
    akun = forms.ModelChoiceField(queryset=Akun.objects.all())
    berlaku_mulai = forms.DateField()

    def clean_sisi(self):
        return self.cleaned_data.get('sisi') or SISI_NORMAL

    def clean(self):
        cleaned = super().clean()
        baris = cleaned.get('baris_jurnal')
        akun = cleaned.get('akun')
        if baris and akun:
            diizinkan = baris.kategori_akun or []
            if diizinkan and akun.kategori_id not in diizinkan:
                self.add_error(
                    'akun',
                    f"Akun '{akun}' berkategori '{akun.kategori_id}', "
                    f"sedangkan baris '{baris.label}' hanya menerima: "
                    f"{', '.join(diizinkan)}.",
                )
        return cleaned
```

- [ ] **Step 4: Implementasi view**

`apps/posting/views.py`:
```python
"""View Posting Engine — SUPERUSER ONLY.

Halaman ini milik vendor (pemilik aplikasi), bukan klien. Sengaja TIDAK memakai
has_ni_perm('settings_view') — permission itu bisa diberikan ke user biasa,
terlalu longgar untuk halaman ini (spec §8.2c).
"""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.master_data.models import Akun

from .forms import PemetaanAkunForm
from .models import JenisTransaksi, PemetaanAkun


def _require_superuser(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Halaman ini hanya untuk superuser.')
    return None


@login_required
def daftar_jenis_transaksi(request):
    denied = _require_superuser(request)
    if denied:
        return denied
    return render(request, 'posting/daftar.html', {
        'jenis_transaksi_list': JenisTransaksi.objects.all().select_related('entitas_bisnis'),
    })


def _akun_choices(kategori_list):
    if not kategori_list:
        return list(Akun.objects.all().order_by('kode_akun'))
    return list(Akun.objects.filter(kategori_id__in=kategori_list).order_by('kode_akun'))


@login_required
def detail_jenis_transaksi(request, pk):
    denied = _require_superuser(request)
    if denied:
        return denied

    jt = get_object_or_404(JenisTransaksi, pk=pk)
    scope_tipe = request.GET.get('scope_tipe') or 'global'
    scope_id = request.GET.get('scope_id') or None

    pemetaan_map = {}
    for p in PemetaanAkun.objects.filter(
        baris_jurnal__jenis_transaksi=jt, scope_tipe=scope_tipe,
    ).select_related('akun').order_by('-berlaku_mulai'):
        pemetaan_map.setdefault((p.baris_jurnal_id, p.sisi), p)

    baris_list = []
    for baris in jt.baris.all():
        baris_list.append({
            'baris': baris,
            'pemetaan_normal': pemetaan_map.get((baris.pk, '')),
            'pemetaan_kredit': pemetaan_map.get((baris.pk, 'kredit')),
            'pemetaan_debit': pemetaan_map.get((baris.pk, 'debit')),
            'akun_choices': _akun_choices(baris.kategori_akun),
        })

    return render(request, 'posting/detail.html', {
        'jenis_transaksi': jt,
        'baris_list': baris_list,
        'scope_tipe': scope_tipe,
        'scope_id': scope_id,
        'hari_ini': date.today(),
    })


@login_required
def simpan_pemetaan(request):
    denied = _require_superuser(request)
    if denied:
        return denied
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    form = PemetaanAkunForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'errors': {k: [str(e) for e in v] for k, v in form.errors.items()},
        })

    data = form.cleaned_data
    PemetaanAkun.objects.update_or_create(
        baris_jurnal=data['baris_jurnal'],
        sisi=data['sisi'],
        scope_tipe=data['scope_tipe'],
        scope_id=data['scope_id'],
        scope_kode=data['scope_kode'],
        berlaku_mulai=data['berlaku_mulai'],
        defaults={'akun': data['akun']},
    )
    return JsonResponse({'success': True})
```

> **Catatan:** `update_or_create` di sini **tidak** melanggar effective-dating. `berlaku_mulai` ikut jadi kunci pencarian — mengganti akun untuk **tanggal berlaku yang sama** = koreksi (upsert), sedangkan menyimpan dengan **tanggal berlaku baru** = baris riwayat baru. Persis yang dites di `test_tanggal_berlaku_baru_membuat_baris_riwayat_baru`.

- [ ] **Step 5: Template sementara (template lengkap di Task 7) & URL**

`templates/posting/daftar.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Jenis Transaksi</h1>
<ul>
  {% for jt in jenis_transaksi_list %}
  <li><a href="{% url 'posting:detail' jt.pk %}">{{ jt.grup }} — {{ jt.label }}</a></li>
  {% empty %}
  <li>Belum ada jenis transaksi.</li>
  {% endfor %}
</ul>
{% endblock %}
```

`templates/posting/detail.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>{{ jenis_transaksi.label }}</h1>
{% for entry in baris_list %}
<p>{{ entry.baris.label }}</p>
{% for akun in entry.akun_choices %}<span>{{ akun.kode_akun }}</span>{% endfor %}
{% endfor %}
{% endblock %}
```

`apps/posting/urls.py` — ganti isinya:
```python
"""Posting Engine URLs."""
from django.urls import path

from . import views

app_name = 'posting'

urlpatterns = [
    path('', views.daftar_jenis_transaksi, name='daftar'),
    path('<int:pk>/', views.detail_jenis_transaksi, name='detail'),
    path('pemetaan/simpan/', views.simpan_pemetaan, name='simpan_pemetaan'),
]
```

- [ ] **Step 6: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_views -v 2`
Expected: `OK` (12 tes)

- [ ] **Step 7: Commit**

```bash
git add apps/posting/forms.py apps/posting/views.py apps/posting/urls.py templates/posting/daftar.html templates/posting/detail.html apps/posting/tests/test_views.py
git commit -m "feat(posting): add superuser-only jenis transaksi views and mapping save"
```

---

### Task 7: Preview jurnal + template lengkap + nav

Spec §6 & §8.2b. **Preview adalah pengaman wajib**, bukan hiasan: begitu superuser bisa menyusun baris jurnal, ia juga bisa salah menyusunnya — preview adalah satu-satunya cara memverifikasi tanpa menjalankan transaksi sungguhan.

**Files:**
- Modify: `apps/posting/views.py` (tambah view `preview_jurnal`)
- Modify: `apps/posting/urls.py`
- Modify: `templates/posting/detail.html` (template lengkap + panel preview)
- Modify: `templates/base.html` (nav link)
- Create: `apps/posting/tests/test_preview.py`

**Interfaces:**
- Produces: view `preview_jurnal` (POST AJAX, `posting:preview`). Body: `jenis_transaksi` (pk) + `angka__<kode>` per angka. Response: `{'success': True, 'baris': [{'label','akun','debit','kredit'}], 'total_debit','total_kredit','balance': bool}` atau `{'success': False, 'error': '...'}`.

- [ ] **Step 1: Tulis tes yang gagal**

`apps/posting/tests/test_preview.py`:
```python
"""Unit tests untuk preview jurnal."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.master_data.models import Akun
from apps.posting.constants import ARAH_DEBIT, ARAH_KREDIT, SUMBER_MAPPING
from apps.posting.models import BarisJurnal, JenisTransaksi, PemetaanAkun

User = get_user_model()


def _akun(kode, kategori):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


class PreviewTests(TestCase):
    def setUp(self):
        self.client = Client()
        su = User.objects.create_superuser(email='su@test.com', password='pass', name='SU')
        self.client.force_login(su)

        self.jt = JenisTransaksi.objects.create(
            kode='penjualan', label='Penjualan Kasir', grup='Penjualan', module='sales',
        )
        kas = _akun('1.1.1', 'aset')
        pendapatan = _akun('4.1.1', 'pendapatan')

        baris_kas = BarisJurnal.objects.create(
            jenis_transaksi=self.jt, urutan=1, kode='kas', label='Kas',
            angka='nilai_bayar', arah=ARAH_DEBIT, sumber_akun=SUMBER_MAPPING,
            kategori_akun=['aset'],
        )
        baris_pend = BarisJurnal.objects.create(
            jenis_transaksi=self.jt, urutan=2, kode='pendapatan', label='Pendapatan',
            angka='subtotal', arah=ARAH_KREDIT, sumber_akun=SUMBER_MAPPING,
            kategori_akun=['pendapatan'],
        )
        for baris, akun in ((baris_kas, kas), (baris_pend, pendapatan)):
            PemetaanAkun.objects.create(
                baris_jurnal=baris, akun=akun, scope_tipe='global',
                berlaku_mulai=date(2026, 1, 1),
            )

    def _preview(self, **angka):
        data = {'jenis_transaksi': self.jt.pk, 'tanggal': '2026-07-15'}
        data.update({f'angka__{k}': v for k, v in angka.items()})
        return self.client.post(
            reverse('posting:preview'), data, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_user_biasa_ditolak(self):
        user = User.objects.create_user(email='u@test.com', password='pass', name='U')
        self.client.force_login(user)
        self.assertEqual(self._preview(nilai_bayar='100000').status_code, 403)

    def test_preview_menampilkan_baris_balance(self):
        body = self._preview(nilai_bayar='100000', subtotal='100000').json()
        self.assertTrue(body['success'])
        self.assertEqual(len(body['baris']), 2)
        self.assertTrue(body['balance'])
        self.assertEqual(body['total_debit'], '100000.00')
        self.assertEqual(body['total_kredit'], '100000.00')

    def test_preview_menandai_tidak_balance(self):
        body = self._preview(nilai_bayar='105000', subtotal='100000').json()
        self.assertTrue(body['success'])
        self.assertFalse(body['balance'])

    def test_preview_melewati_baris_bernilai_nol(self):
        body = self._preview(nilai_bayar='100000', subtotal='0').json()
        self.assertEqual(len(body['baris']), 1)
        self.assertEqual(body['baris'][0]['label'], 'Kas')

    def test_preview_melaporkan_pemetaan_yang_belum_di_set(self):
        BarisJurnal.objects.create(
            jenis_transaksi=self.jt, urutan=3, kode='ppn', label='Hutang PPN',
            angka='pajak', arah=ARAH_KREDIT, sumber_akun=SUMBER_MAPPING,
            kategori_akun=['kewajiban'],
        )
        body = self._preview(nilai_bayar='111000', subtotal='100000', pajak='11000').json()
        self.assertFalse(body['success'])
        self.assertIn('Hutang PPN', body['error'])
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `python manage.py test apps.posting.tests.test_preview -v 2`
Expected: `NoReverseMatch: Reverse for 'preview' not found`

- [ ] **Step 3: Tambahkan view preview**

Di `apps/posting/views.py`, tambahkan import berikut (`from datetime import date` sudah ada sejak Task 6):
```python
from decimal import Decimal, InvalidOperation
```
dan
```python
from .poster import AkunEksternalHilangError, bangun_baris_jurnal, cek_balance
from .resolver import PemetaanTidakAdaError
```

Lalu tambahkan view berikut di akhir file:
```python
def _angka_dari_post(post) -> dict:
    """Ambil field 'angka__<kode>' dari POST menjadi {kode: Decimal}."""
    angka = {}
    for key, value in post.items():
        if not key.startswith('angka__'):
            continue
        kode = key[len('angka__'):]
        try:
            angka[kode] = Decimal(value or '0')
        except InvalidOperation:
            angka[kode] = Decimal('0')
    return angka


@login_required
def preview_jurnal(request):
    """Tunjukkan jurnal yang AKAN dihasilkan konfigurasi ini — spec §8.2b.

    Satu-satunya cara superuser memverifikasi konfigurasinya benar tanpa
    menjalankan transaksi sungguhan.
    """
    denied = _require_superuser(request)
    if denied:
        return denied
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    jt = get_object_or_404(JenisTransaksi, pk=request.POST.get('jenis_transaksi'))
    tanggal = request.POST.get('tanggal') or date.today().isoformat()
    angka = _angka_dari_post(request.POST)

    konteks = {}
    if request.POST.get('scope_tipe') and request.POST.get('scope_id'):
        konteks[request.POST['scope_tipe']] = int(request.POST['scope_id'])

    try:
        baris = bangun_baris_jurnal(jt, angka=angka, konteks=konteks, tanggal=tanggal)
    except (PemetaanTidakAdaError, AkunEksternalHilangError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)})

    total_debit = sum((b.debit for b in baris), Decimal('0'))
    total_kredit = sum((b.kredit for b in baris), Decimal('0'))
    try:
        cek_balance(baris)
        balance = True
    except Exception:
        balance = False

    return JsonResponse({
        'success': True,
        'baris': [
            {
                'label': b.label,
                'akun': f'{b.akun.kode_akun} {b.akun.nama}',
                'debit': f'{b.debit:.2f}',
                'kredit': f'{b.kredit:.2f}',
            }
            for b in baris
        ],
        'total_debit': f'{total_debit:.2f}',
        'total_kredit': f'{total_kredit:.2f}',
        'balance': balance,
    })
```

> **Catatan:** `bangun_baris_jurnal` menerima `tanggal` berupa string ISO di sini; Django meneruskannya ke `berlaku_mulai__lte` yang menerima string ISO tanpa masalah di Postgres. Tidak perlu konversi.

- [ ] **Step 4: Daftarkan URL**

`apps/posting/urls.py` — tambahkan satu baris pada `urlpatterns`:
```python
urlpatterns = [
    path('', views.daftar_jenis_transaksi, name='daftar'),
    path('<int:pk>/', views.detail_jenis_transaksi, name='detail'),
    path('pemetaan/simpan/', views.simpan_pemetaan, name='simpan_pemetaan'),
    path('preview/', views.preview_jurnal, name='preview'),
]
```

- [ ] **Step 5: Template lengkap dengan panel preview**

`templates/posting/detail.html` — ganti seluruh isinya:
```html
{% extends "base.html" %}

{% block title %}{{ jenis_transaksi.label }} — Posting Engine{% endblock %}

{% block content %}
<div class="ni-card">
  <div class="ni-card__header">
    <h1>{{ jenis_transaksi.label }}</h1>
    <p>{{ jenis_transaksi.grup }} · modul: {{ jenis_transaksi.module }}</p>
  </div>

  <div class="ni-card__body">
    <table class="ni-table">
      <thead>
        <tr><th>Baris</th><th>Angka</th><th>Arah</th><th>Akun</th></tr>
      </thead>
      <tbody>
        {% for entry in baris_list %}
        <tr>
          <td>
            {{ entry.baris.label }}
            {% if entry.baris.wajib and not entry.pemetaan_normal %}
            <span style="color:#c0392b;">(! wajib)</span>
            {% endif %}
          </td>
          <td><code>{{ entry.baris.angka }}</code></td>
          <td>{{ entry.baris.get_arah_display }}</td>
          <td>
            {% if entry.baris.sumber_akun == 'mapping' %}
            <form method="post" action="{% url 'posting:simpan_pemetaan' %}" class="posting-save-form">
              {% csrf_token %}
              <input type="hidden" name="baris_jurnal" value="{{ entry.baris.pk }}">
              <input type="hidden" name="sisi" value="">
              <input type="hidden" name="scope_tipe" value="{{ scope_tipe }}">
              {% if scope_id %}<input type="hidden" name="scope_id" value="{{ scope_id }}">{% endif %}
              <input type="date" name="berlaku_mulai" value="{{ hari_ini|date:'Y-m-d' }}"
                     class="ni-input" title="Tanggal mulai berlaku pemetaan ini">
              <select name="akun" class="ni-input" onchange="this.form.requestSubmit()">
                <option value="">-- belum di-set --</option>
                {% for akun in entry.akun_choices %}
                <option value="{{ akun.pk }}" {% if entry.pemetaan_normal.akun_id == akun.pk %}selected{% endif %}>
                  {{ akun.kode_akun }} {{ akun.nama }}
                </option>
                {% endfor %}
              </select>
            </form>
            {% else %}
            <em>{{ entry.baris.get_sumber_akun_display }}</em>
            {% endif %}
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="4">Belum ada baris jurnal.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="ni-card" style="margin-top:16px;">
  <div class="ni-card__header"><h2>Preview Jurnal</h2></div>
  <div class="ni-card__body">
    <p>Isi contoh nilai untuk melihat jurnal yang akan dihasilkan konfigurasi ini.</p>
    <form id="preview-form">
      {% csrf_token %}
      <input type="hidden" name="jenis_transaksi" value="{{ jenis_transaksi.pk }}">
      <input type="hidden" name="scope_tipe" value="{{ scope_tipe }}">
      {% if scope_id %}<input type="hidden" name="scope_id" value="{{ scope_id }}">{% endif %}
      <label>Tanggal <input type="date" name="tanggal" value="2026-07-15" class="ni-input"></label>
      {% for entry in baris_list %}
      <label>
        {{ entry.baris.angka }}
        <input type="number" step="0.01" name="angka__{{ entry.baris.angka }}" value="0" class="ni-input">
      </label>
      {% endfor %}
      <button type="submit" class="ni-btn">Lihat Preview</button>
    </form>
    <div id="preview-hasil" style="margin-top:12px;"></div>
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
document.addEventListener('submit', function (e) {
  if (e.target.classList.contains('posting-save-form')) {
    e.preventDefault();
    var form = e.target;
    fetch(form.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: new FormData(form),
    })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (json.success) { window.location.reload(); }
        else { alert('Gagal menyimpan: ' + JSON.stringify(json.errors)); }
      })
      .catch(function () { alert('Terjadi kesalahan. Silakan coba lagi.'); });
    return;
  }

  if (e.target.id === 'preview-form') {
    e.preventDefault();
    var pform = e.target;
    fetch("{% url 'posting:preview' %}", {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: new FormData(pform),
    })
      .then(function (r) { return r.json(); })
      .then(function (json) {
        var box = document.getElementById('preview-hasil');
        if (!json.success) {
          box.innerHTML = '<p style="color:#c0392b;">' + json.error + '</p>';
          return;
        }
        var html = '<table class="ni-table"><thead><tr><th>Baris</th><th>Akun</th>'
                 + '<th>Debit</th><th>Kredit</th></tr></thead><tbody>';
        json.baris.forEach(function (b) {
          html += '<tr><td>' + b.label + '</td><td>' + b.akun + '</td><td>'
               + b.debit + '</td><td>' + b.kredit + '</td></tr>';
        });
        html += '</tbody><tfoot><tr><th colspan="2">Total</th><th>'
             + json.total_debit + '</th><th>' + json.total_kredit + '</th></tr></tfoot></table>';
        html += json.balance
          ? '<p style="color:#27ae60;">Balance ✔</p>'
          : '<p style="color:#c0392b;">TIDAK BALANCE — ada angka yang belum dipasangkan ke baris jurnal manapun.</p>';
        box.innerHTML = html;
      })
      .catch(function () { alert('Terjadi kesalahan. Silakan coba lagi.'); });
  }
});
</script>
{% endblock %}
```

- [ ] **Step 6: Nav link (superuser saja)**

Di `templates/base.html`, cari:
```
      {% if user.is_superuser or user.is_admin %}
      <div class="ni-nav-item">
        <a href="{% url 'accounts:user_list' %}" class="ni-nav-link {% if 'accounts/users' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="users" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">User</span>
        </a>
      </div>
      {% endif %}
```
Ganti jadi:
```
      {% if user.is_superuser or user.is_admin %}
      <div class="ni-nav-item">
        <a href="{% url 'accounts:user_list' %}" class="ni-nav-link {% if 'accounts/users' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="users" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">User</span>
        </a>
      </div>
      {% endif %}

      {% if user.is_superuser %}
      <div class="ni-nav-item">
        <a href="{% url 'posting:daftar' %}" class="ni-nav-link {% if '/posting/' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="settings" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">Jenis Transaksi</span>
        </a>
      </div>
      {% endif %}
```

- [ ] **Step 7: Jalankan tes, pastikan lulus**

Run: `python manage.py test apps.posting.tests.test_preview -v 2`
Expected: `OK` (5 tes)

- [ ] **Step 8: Commit**

```bash
git add apps/posting/views.py apps/posting/urls.py templates/posting/detail.html templates/base.html apps/posting/tests/test_preview.py
git commit -m "feat(posting): add journal preview and full settings UI"
```

---

### Task 8: Verifikasi menyeluruh

**Files:** tidak ada (verifikasi saja)

- [ ] **Step 1: Seluruh suite posting**

Run: `python manage.py test apps.posting -v 2`
Expected: `OK` (semua tes Task 2–7 lulus bersamaan; tidak ada kebocoran katalog antar-tes — memastikan tiap `tearDown` benar memanggil `clear_catalog()`)

- [ ] **Step 2: Seluruh suite project (regresi)**

Run: `python manage.py test`
Expected: `OK` — khususnya tidak ada kegagalan di `apps.purchase`, `apps.sales`, `apps.pendapatan` (memastikan **STT tidak tersentuh**), `apps.jurnal`, `apps.master_data`, `apps.entitas_bisnis`, `apps.accounts` (memastikan perubahan `INSTALLED_APPS`/`urls.py`/`base.html` tidak merusak apapun).

- [ ] **Step 3: Pastikan nol pemanggil produksi**

Run: `grep -rn "apps.posting" apps/ --include=*.py | grep -v "^apps/posting/"`
Expected: **tidak ada output.** Bila ada, sebuah modul sudah meng-import posting engine — itu melanggar Global Constraint "nol pemanggil produksi" dan harus dicabut (pemakaian nyata dimulai di Tahap 1).

- [ ] **Step 4: Check & state migrasi bersih**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `python manage.py makemigrations --check --dry-run`
Expected: tidak ada output / exit code 0.

- [ ] **Step 5: Verifikasi manual di browser**

Run: `python manage.py runserver`

1. Login sebagai **user biasa** → link "Jenis Transaksi" **tidak muncul** di nav; buka `/posting/` langsung → **403**.
2. Login sebagai **superuser** → link muncul; `/posting/` merender daftar kosong (wajar — belum ada jenis transaksi).
3. Buat data contoh lewat Django admin (`/admin/posting/jenistransaksi/`): satu `JenisTransaksi` ("Penjualan Kasir", grup "Penjualan", module "sales"), dua `BarisJurnal` — `kas` (angka `nilai_bayar`, arah Debit, kategori `["aset"]`) dan `pendapatan` (angka `subtotal`, arah Kredit, kategori `["pendapatan"]`).
4. Buka `/posting/<pk>/` → pilih akun untuk kedua baris (dropdown harus **hanya** menampilkan akun berkategori yang sesuai).
5. Di panel **Preview Jurnal**, isi `nilai_bayar=100000`, `subtotal=100000` → harus tampil dua baris dan **Balance ✔**.
6. Ubah `nilai_bayar=105000` → harus tampil **TIDAK BALANCE**. **Inilah pengaman utamanya**: ia menangkap angka yang belum dipasangkan ke baris jurnal manapun.

- [ ] **Step 6: Commit akhir (bila ada perbaikan)**

Bila Step 1–5 tidak butuh perubahan kode, tidak ada yang perlu di-commit — Tahap 0 selesai. Bila ada perbaikan, commit dengan pesan yang menjelaskan regresi apa yang diperbaiki.

---

## Selesai — apa yang sudah ada setelah Tahap 0

- Katalog angka (kode) + `JenisTransaksi`/`BarisJurnal`/`PemetaanAkun` (tabel).
- Resolver: rantai scope (`global` → `entitas_bisnis` → `lv2` → `lv3` → `metode_bayar` → `alasan`) + effective-dated.
- Poster: bentuk baris jurnal, lewati baris nol (mekanisme **varian**), baris **bertanda** dengan dua akun (laba vs rugi), cek balance.
- UI superuser-only + **preview jurnal**.
- **Nol pemanggil produksi** → nol risiko bagi modul yang berjalan.

**Belum ada, dan memang belum boleh ada:** modul manapun yang memanggil engine ini. Itu Tahap 1 (pilot **Penyusutan Aset Tetap** — spec §8), yang butuh plan tersendiri.
