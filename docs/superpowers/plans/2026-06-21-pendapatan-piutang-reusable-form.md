# Reusable Piutang Form + Pendapatan→Piutang (Kredit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the "tambah piutang" form a single reusable source of truth and wire pendapatan credit transactions to capture full piutang data via an inline modal, building a complete `PiutangHeader` at confirm.

**Architecture:** Pendekatan A — a new staging model `PendapatanPiutangProfil` (one-to-one with `PendapatanHeader`) stores modal input at create time; at confirm, an adapter converts header+profil+KP-items into a payload consumed by one canonical `build_piutang()` service. The piutang wizard form body and JS are extracted into a shared partial + static JS so the same form renders in the piutang page and the pendapatan modal.

**Tech Stack:** Django 6.x, Python 3.12, Django forms/formsets, vanilla JS + TomSelect, `manage.py test` runner.

**Spec:** `docs/superpowers/specs/2026-06-21-pendapatan-piutang-reusable-form-design.md`

**Conventions in this codebase:**
- Run tests with `python manage.py test <dotted.path>` (no pytest).
- Decimals everywhere for money (`from decimal import Decimal`).
- Indonesian field/verbose names.
- Commit messages: Conventional Commits, end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Work on `main` (no feature branches — per project working style).

---

## File Structure

**Create:**
- `apps/pendapatan/migrations/0017_pendapatanpiutangprofil.py` — migration (number may differ; use `makemigrations`).
- `templates/piutang/_form_body.html` — extracted wizard body (cards + detail table), included by both piutang page and pendapatan modal.
- `static/js/piutang_form.js` — `initPiutangForm(rootEl, options)`, extracted wizard JS.
- `apps/pendapatan/tests_piutang_integration.py` — new test module for this feature (keeps `tests.py` focused).

**Modify:**
- `apps/pendapatan/models.py` — add `PendapatanPiutangProfil` + `PIUTANG_PROFIL_FIELDS`.
- `apps/piutang/services.py` — add `build_piutang()`; refactor `create_manual_piutang` + `create_piutang_from_pendapatan` to wrap it.
- `apps/pendapatan/services.py` — add `pendapatan_to_piutang_payload()`; rewrite the credit branch of `confirm_pendapatan` (accounting fix + link journal).
- `apps/pendapatan/views.py` — `pendapatan_create` + `pendapatan_edit`: parse/validate `piutang-*`, save `PendapatanPiutangProfil`, block credit-without-profil.
- `templates/piutang/form.html` — replace inline body+JS with `{% include '_form_body.html' %}` + `<script src=...>` + `initPiutangForm(document, {...})`.
- `templates/pendapatan/form.html` — add "Atur Detail Piutang" button + modal including the partial + glue JS.

---

## Task 1: `PendapatanPiutangProfil` staging model

**Files:**
- Modify: `apps/pendapatan/models.py` (append at end of file)
- Create: `apps/pendapatan/migrations/0017_pendapatanpiutangprofil.py` (via makemigrations)
- Test: `apps/pendapatan/tests_piutang_integration.py`

- [ ] **Step 1: Write the failing test**

Create `apps/pendapatan/tests_piutang_integration.py`:

```python
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.master_data.models import Akun, KategoriAkun
from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import SubTransactionType
from apps.pendapatan.models import (
    PendapatanHeader, PendapatanEntitasBisnis, KewajibabPelaksanaan,
    PendapatanPiutangProfil, PIUTANG_PROFIL_FIELDS,
)


def _akun(kode, nama, kategori_id='aset'):
    kat, _ = KategoriAkun.objects.get_or_create(
        id=kategori_id, defaults={'nama': kategori_id.title()})
    return Akun.objects.create(kode_akun=kode, nama_akun=nama, kategori=kat)


class PendapatanPiutangProfilModelTest(TestCase):
    def test_profil_one_to_one_with_header(self):
        akun_piutang = _akun('1.1.4', 'Piutang Usaha')
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft',
        )
        profil = PendapatanPiutangProfil.objects.create(
            pendapatan_header=header,
            debitur='PT Maju',
            coa_piutang_account=akun_piutang,
        )
        self.assertEqual(header.piutang_profil, profil)
        self.assertEqual(profil.debitur, 'PT Maju')
        # Constant lists the fields the modal mirrors from PiutangHeader.
        self.assertIn('coa_piutang_account', PIUTANG_PROFIL_FIELDS)
        self.assertIn('jatuh_tempo', PIUTANG_PROFIL_FIELDS)
```

> NOTE: If `KategoriAkun`/`Akun` constructor args differ in this codebase, adjust `_akun` to match `apps/master_data/models.py`. Verify field names (`kode_akun`, `nama_akun`, `kategori`) before running — fix the helper, not the test intent.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.PendapatanPiutangProfilModelTest -v 2`
Expected: FAIL with `ImportError: cannot import name 'PendapatanPiutangProfil'`.

- [ ] **Step 3: Add the model + constant**

Append to `apps/pendapatan/models.py`:

```python
# ── Staging profil piutang untuk transaksi kredit ────────────────────────────

# Field yang di-mirror dari PiutangHeader ke modal pendapatan. Tambah di sini
# bila form piutang menambah field credit-terms baru yang ingin di-stage.
PIUTANG_PROFIL_FIELDS = [
    'debitur', 'coa_piutang_account', 'jatuh_tempo',
    'jenis_jangka_waktu', 'jenis_bunga', 'suku_bunga', 'periode_angsuran',
    'pv_discount_rate', 'interest_income_account', 'coa_piutang_lancar_account',
    'standar_akuntansi', 'kategori_pengukuran', 'business_model', 'sppi_test_passed',
    'biaya_transaksi', 'biaya_transaksi_account',
    'agunan_jenis', 'agunan_nilai', 'is_approval_required',
]


class PendapatanPiutangProfil(models.Model):
    """Staging untuk field piutang yang diisi di modal pendapatan (transaksi kredit).

    Disimpan saat create/edit pendapatan; dikonsumsi saat confirm untuk membangun
    PiutangHeader lengkap lewat apps.piutang.services.build_piutang().
    """
    pendapatan_header = models.OneToOneField(
        PendapatanHeader, on_delete=models.CASCADE,
        related_name='piutang_profil', verbose_name='Pendapatan Header',
    )
    debitur = models.CharField(max_length=255, blank=True, default='', verbose_name='Debitur')
    coa_piutang_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pendapatan_profil_piutang', verbose_name='Akun Piutang',
    )
    jatuh_tempo = models.DateField(null=True, blank=True, verbose_name='Jatuh Tempo')
    jenis_jangka_waktu = models.CharField(max_length=20, default='short_term', verbose_name='Jenis Jangka Waktu')
    jenis_bunga = models.CharField(max_length=20, default='tanpa_bunga', verbose_name='Jenis Bunga')
    suku_bunga = models.DecimalField(max_digits=8, decimal_places=4, default=0, verbose_name='Suku Bunga')
    periode_angsuran = models.CharField(max_length=20, default='bulanan', verbose_name='Periode Angsuran')
    pv_discount_rate = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name='Market Rate PV')
    interest_income_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pendapatan_profil_interest', verbose_name='Akun Pendapatan Bunga Efektif',
    )
    coa_piutang_lancar_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pendapatan_profil_lancar', verbose_name='Akun Piutang Bagian Lancar',
    )
    standar_akuntansi = models.CharField(max_length=10, blank=True, default='', verbose_name='Standar Akuntansi')
    kategori_pengukuran = models.CharField(max_length=20, default='amortised_cost', verbose_name='Kategori Pengukuran')
    business_model = models.CharField(max_length=30, blank=True, default='', verbose_name='Business Model')
    sppi_test_passed = models.BooleanField(null=True, blank=True, verbose_name='SPPI Test Lulus')
    biaya_transaksi = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal('0'), verbose_name='Biaya Transaksi')
    biaya_transaksi_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pendapatan_profil_biaya', verbose_name='Akun Biaya Transaksi',
    )
    agunan_jenis = models.CharField(max_length=255, blank=True, default='', verbose_name='Jenis Agunan')
    agunan_nilai = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True, verbose_name='Nilai Agunan')
    is_approval_required = models.BooleanField(default=False, verbose_name='Perlu Approval')

    class Meta:
        verbose_name = 'Profil Piutang Pendapatan'
        verbose_name_plural = 'Profil Piutang Pendapatan'

    def __str__(self) -> str:
        return f'Profil Piutang {self.pendapatan_header.transaction_id}'
```

Add `from decimal import Decimal` to the top of `apps/pendapatan/models.py` if not already imported (the file currently does not import it).

- [ ] **Step 4: Create the migration**

Run: `python manage.py makemigrations pendapatan`
Expected: creates `apps/pendapatan/migrations/0017_pendapatanpiutangprofil.py` (or next free number).

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.PendapatanPiutangProfilModelTest -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/models.py apps/pendapatan/migrations/ apps/pendapatan/tests_piutang_integration.py
git commit -m "feat(pendapatan): add PendapatanPiutangProfil staging model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Canonical `build_piutang()` service

**Files:**
- Modify: `apps/piutang/services.py:194-377` (refactor `create_manual_piutang` + `create_piutang_from_pendapatan`)
- Test: `apps/piutang/tests.py` (append a new TestCase)

The current `create_manual_piutang` (lines 194-269) and `create_piutang_from_pendapatan` (lines 325-377) duplicate header+detail creation. Introduce one `build_piutang()` they both delegate to.

- [ ] **Step 1: Write the failing test**

Append to `apps/piutang/tests.py` (reuse existing test fixtures/helpers in that file for `Akun`; if none, mirror the `_akun` helper from Task 1):

```python
class BuildPiutangServiceTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        from apps.master_data.models import Akun, KategoriAkun
        kat, _ = KategoriAkun.objects.get_or_create(
            id=kategori_id, defaults={'nama': kategori_id.title()})
        return Akun.objects.create(kode_akun=kode, nama_akun=nama, kategori=kat)

    def test_build_piutang_creates_full_header_and_details(self):
        from decimal import Decimal
        from datetime import date
        from apps.piutang.services import build_piutang
        from apps.piutang.models import PiutangHeader

        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        payload = {
            'tanggal': date(2026, 1, 10),
            'debitur': 'PT Maju',
            'deskripsi': 'Piutang uji',
            'coa_piutang_account': akun_piutang,
            'jatuh_tempo': date(2026, 3, 10),
            'jenis_bunga': 'flat',
            'suku_bunga': Decimal('12'),
            'kategori_pengukuran': 'amortised_cost',
        }
        details = [{'deskripsi': 'Baris 1', 'jumlah': Decimal('1000'), 'revenue_account': akun_pend}]
        piutang = build_piutang(payload, source='manual', source_obj=None, details=details, user=None)

        self.assertIsInstance(piutang, PiutangHeader)
        self.assertEqual(piutang.jumlah_pokok, Decimal('1000'))
        self.assertEqual(piutang.debitur, 'PT Maju')
        self.assertEqual(piutang.jenis_bunga, 'flat')
        self.assertEqual(piutang.suku_bunga, Decimal('12'))
        self.assertEqual(piutang.details.count(), 1)
        self.assertEqual(piutang.status, 'draft')  # manual default

    def test_build_piutang_pendapatan_source_status_open(self):
        from decimal import Decimal
        from datetime import date
        from apps.piutang.services import build_piutang
        akun_piutang = self._akun('1.1.5', 'Piutang B')
        payload = {'tanggal': date(2026, 1, 10), 'coa_piutang_account': akun_piutang}
        details = [{'deskripsi': 'x', 'jumlah': Decimal('500'), 'revenue_account': None}]
        piutang = build_piutang(payload, source='pendapatan', source_obj=None, details=details, user=None)
        self.assertEqual(piutang.status, 'open')
        self.assertEqual(piutang.source_type, 'from_pendapatan')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.piutang.tests.BuildPiutangServiceTest -v 2`
Expected: FAIL with `ImportError: cannot import name 'build_piutang'`.

- [ ] **Step 3: Implement `build_piutang` and refactor the two wrappers**

In `apps/piutang/services.py`, add `build_piutang` directly above `create_manual_piutang` (before line 194):

```python
# Mapping source → (source_type value on PiutangHeader, default status)
_PIUTANG_SOURCE_MAP = {
    'manual': ('manual', 'draft'),
    'pendapatan': ('from_pendapatan', 'open'),
    'sales': ('from_sales', 'open'),
}


def build_piutang(payload: dict, *, source: str, source_obj, details: list, user=None) -> PiutangHeader:
    """Canonical piutang factory used by every module.

    payload: dict of PiutangHeader header fields (debitur, coa_piutang_account, credit terms…).
    details: list of {'deskripsi', 'jumlah', 'revenue_account'(, 'sub_transaction_type')}.
    source: 'manual' | 'pendapatan' | 'sales'.
    source_obj: the originating header (PendapatanHeader / SalesHeader) or None.

    Does NOT post an AR journal — posting is a separate step (manual) or already
    booked by the originating module's confirm (pendapatan).
    """
    if not details:
        raise ValueError('Minimal satu detail piutang diperlukan.')
    total = sum(Decimal(str(d['jumlah'])) for d in details)
    if total <= 0:
        raise ValueError('Total piutang harus lebih besar dari 0.')

    source_type, default_status = _PIUTANG_SOURCE_MAP[source]
    header_kwargs = dict(payload)
    header_kwargs.setdefault('status', default_status)
    header_kwargs['source_type'] = source_type
    if source == 'pendapatan':
        header_kwargs['source_pendapatan'] = source_obj
    elif source == 'sales':
        header_kwargs['source_sales'] = source_obj
    header_kwargs['jumlah_pokok'] = total
    header_kwargs['created_by'] = user

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(**header_kwargs)
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d.get('deskripsi', ''),
                jumlah=Decimal(str(d['jumlah'])),
                revenue_account=d.get('revenue_account'),
                sub_transaction_type=d.get('sub_transaction_type'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang
```

Then replace the body of `create_manual_piutang` (keep its signature for backward compatibility) so it builds a payload dict and delegates:

```python
def create_manual_piutang(
    tanggal, entitas_bisnis, debitur, deskripsi, coa_piutang_account, jatuh_tempo,
    details, jenis_jangka_waktu='short_term', jenis_bunga='tanpa_bunga',
    suku_bunga=Decimal('0'), periode_angsuran='bulanan', is_approval_required=False,
    pv_discount_rate=None, deferred_income_account=None, interest_income_account=None,
    coa_piutang_lancar_account=None, deferred_income_lancar_account=None,
    standar_akuntansi='', kategori_pengukuran='amortised_cost', business_model='',
    sppi_test_passed=None, biaya_transaksi=None, biaya_transaksi_account=None,
    agunan_jenis='', agunan_nilai=None, user=None,
) -> PiutangHeader:
    payload = {
        'tanggal': tanggal, 'entitas_bisnis': entitas_bisnis, 'debitur': debitur,
        'deskripsi': deskripsi, 'coa_piutang_account': coa_piutang_account,
        'jatuh_tempo': jatuh_tempo, 'jenis_jangka_waktu': jenis_jangka_waktu,
        'jenis_bunga': jenis_bunga, 'suku_bunga': suku_bunga,
        'periode_angsuran': periode_angsuran, 'is_approval_required': is_approval_required,
        'pv_discount_rate': pv_discount_rate, 'deferred_income_account': deferred_income_account,
        'interest_income_account': interest_income_account,
        'coa_piutang_lancar_account': coa_piutang_lancar_account,
        'deferred_income_lancar_account': deferred_income_lancar_account,
        'standar_akuntansi': standar_akuntansi or '',
        'kategori_pengukuran': kategori_pengukuran or 'amortised_cost',
        'business_model': business_model or '', 'sppi_test_passed': sppi_test_passed,
        'biaya_transaksi': biaya_transaksi or Decimal('0'),
        'biaya_transaksi_account': biaya_transaksi_account,
        'agunan_jenis': agunan_jenis or '', 'agunan_nilai': agunan_nilai,
    }
    return build_piutang(payload, source='manual', source_obj=None, details=details, user=user)
```

Replace the body of `create_piutang_from_pendapatan` (lines 325-377) to delegate via the new adapter (defined in Task 3). For now leave it importing the adapter lazily:

```python
def create_piutang_from_pendapatan(pendapatan_header, user=None) -> PiutangHeader:
    from apps.pendapatan.services import pendapatan_to_piutang_payload
    payload, details = pendapatan_to_piutang_payload(pendapatan_header)
    return build_piutang(payload, source='pendapatan', source_obj=pendapatan_header,
                         details=details, user=user)
```

> NOTE: `build_piutang` passes `payload` straight into `PiutangHeader.objects.create(**payload)`, so every key in `payload` MUST be a real `PiutangHeader` field. The adapter in Task 3 is responsible for only emitting valid field names.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.piutang.tests.BuildPiutangServiceTest -v 2`
Expected: PASS.

- [ ] **Step 5: Run the existing piutang suite (regression)**

Run: `python manage.py test apps.piutang -v 1`
Expected: PASS (no regression in `create_manual_piutang` callers).

> If `create_piutang_from_pendapatan` tests run here and fail because Task 3 isn't done yet, that's expected — they pass after Task 3. Note which tests, continue.

- [ ] **Step 6: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add canonical build_piutang() and refactor factories to use it

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `pendapatan_to_piutang_payload()` adapter

**Files:**
- Modify: `apps/pendapatan/services.py` (add function; import `PendapatanPiutangProfil` + `PIUTANG_PROFIL_FIELDS`)
- Test: `apps/pendapatan/tests_piutang_integration.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/pendapatan/tests_piutang_integration.py`:

```python
class AdapterTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        kat, _ = KategoriAkun.objects.get_or_create(
            id=kategori_id, defaults={'nama': kategori_id.title()})
        return Akun.objects.create(kode_akun=kode, nama_akun=nama, kategori=kat)

    def _stt(self):
        akun = self._akun('2.1.1', 'Offset')
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=akun)

    def test_adapter_maps_profil_and_kp_items(self):
        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        eb = EntitasBisnis.objects.create(nama='PT Alpha', standar_akuntansi='psak')
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb)
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group, deskripsi_item='Jasa konsultasi', kategori='jasa',
            sub_transaction_type=self._stt(), nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend)
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header, debitur='PT Alpha',
            coa_piutang_account=akun_piutang, jenis_bunga='flat',
            suku_bunga=Decimal('10'))

        from apps.pendapatan.services import pendapatan_to_piutang_payload
        payload, details = pendapatan_to_piutang_payload(header)

        self.assertEqual(payload['debitur'], 'PT Alpha')
        self.assertEqual(payload['coa_piutang_account'], akun_piutang)
        self.assertEqual(payload['jenis_bunga'], 'flat')
        self.assertEqual(payload['tanggal'], header.tanggal)
        self.assertEqual(payload['entitas_bisnis'], eb)
        self.assertNotIn('debitur', [])  # sanity
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['deskripsi'], 'Jasa konsultasi')
        self.assertEqual(details[0]['jumlah'], Decimal('2000'))
        self.assertEqual(details[0]['revenue_account'], akun_pend)

    def test_adapter_raises_without_profil(self):
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        from apps.pendapatan.services import pendapatan_to_piutang_payload
        with self.assertRaises(ValueError):
            pendapatan_to_piutang_payload(header)
```

> NOTE: Adjust `EntitasBisnis.objects.create(...)` kwargs to match the real model (verify `nama`, `standar_akuntansi`, `status_aktif` fields in `apps/entitas_bisnis/models.py`). Fix the helper, not the assertion intent.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.AdapterTest -v 2`
Expected: FAIL with `ImportError: cannot import name 'pendapatan_to_piutang_payload'`.

- [ ] **Step 3: Implement the adapter**

In `apps/pendapatan/services.py`, update the model import (line 16-19) to also import the new names, then add the function near the other piutang-related helpers (e.g. just below `_log_event`):

```python
def pendapatan_to_piutang_payload(header: PendapatanHeader):
    """Convert a credit PendapatanHeader (+ its PendapatanPiutangProfil + KP items)
    into (payload, details) for apps.piutang.services.build_piutang().

    This is THE single mapping point. If a new auto-prefilled piutang field is added,
    extend PIUTANG_PROFIL_FIELDS and (if not a direct copy) this function only.
    """
    from .models import PendapatanPiutangProfil, PIUTANG_PROFIL_FIELDS

    try:
        profil = header.piutang_profil
    except PendapatanPiutangProfil.DoesNotExist:
        raise ValueError(
            f'Pendapatan {header.transaction_id} bertipe kredit tetapi belum memiliki '
            f'profil piutang. Atur Detail Piutang sebelum konfirmasi.'
        )

    eb_group = header.entitas_groups.select_related('entitas_bisnis').first()
    payload = {
        'tanggal': header.tanggal,
        'deskripsi': f'Piutang dari Pendapatan {header.transaction_id}',
        'entitas_bisnis': eb_group.entitas_bisnis if eb_group else None,
    }
    for f in PIUTANG_PROFIL_FIELDS:
        payload[f] = getattr(profil, f)

    details = []
    for eg in header.entitas_groups.prefetch_related('items__revenue_account').all():
        for kp in eg.items.all():
            details.append({
                'deskripsi': kp.deskripsi_item[:255],
                'jumlah': kp.nilai_kontrak,
                'revenue_account': kp.revenue_account,
            })
    return payload, details
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.AdapterTest -v 2`
Expected: PASS.

- [ ] **Step 5: Re-run piutang suite (confirms Task 2 Step 5 deferred failures now pass)**

Run: `python manage.py test apps.piutang apps.pendapatan -v 1`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/services.py apps/pendapatan/tests_piutang_integration.py
git commit -m "feat(pendapatan): add pendapatan_to_piutang_payload adapter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Confirm flow — build full piutang + accounting fix

**Files:**
- Modify: `apps/pendapatan/services.py:281-394` (`confirm_pendapatan`)
- Test: `apps/pendapatan/tests_piutang_integration.py`

Two changes inside `confirm_pendapatan`:
1. For credit point-in-time KP, debit the **piutang account from the profil** (`profil.coa_piutang_account`), not `payment_account`.
2. After booking, build the full piutang from the profil (replaces the thin `create_piutang_from_pendapatan` call at lines 386-390) and link the AR journal(s) for traceability.

- [ ] **Step 1: Write the failing test**

Append to `apps/pendapatan/tests_piutang_integration.py`:

```python
class ConfirmCreditTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        kat, _ = KategoriAkun.objects.get_or_create(
            id=kategori_id, defaults={'nama': kategori_id.title()})
        return Akun.objects.create(kode_akun=kode, nama_akun=nama, kategori=kat)

    def _stt(self):
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=self._akun('2.1.9', 'Offset'))

    def test_confirm_credit_builds_full_piutang_and_books_ar(self):
        from apps.jurnal.models import JurnalDetail
        from apps.piutang.models import PiutangHeader
        from apps.pendapatan.services import confirm_pendapatan

        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        eb = EntitasBisnis.objects.create(nama='PT Alpha', standar_akuntansi='psak')
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb)
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group, deskripsi_item='Jasa', kategori='jasa',
            sub_transaction_type=self._stt(), nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend, recognition_type='point_in_time')
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header, debitur='PT Alpha',
            coa_piutang_account=akun_piutang, jenis_bunga='flat', suku_bunga=Decimal('10'))

        confirm_pendapatan(header, user=None)
        header.refresh_from_db()
        self.assertEqual(header.status, 'confirmed')

        piutang = PiutangHeader.objects.get(source_pendapatan=header)
        self.assertEqual(piutang.jumlah_pokok, Decimal('2000'))
        self.assertEqual(piutang.jenis_bunga, 'flat')  # credit term carried over
        self.assertEqual(piutang.coa_piutang_account, akun_piutang)

        # AR journal debits the piutang account (not a cash account).
        debit_lines = JurnalDetail.objects.filter(akun=akun_piutang, debit=Decimal('2000'))
        self.assertTrue(debit_lines.exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.ConfirmCreditTest -v 2`
Expected: FAIL — either piutang lacks `jenis_bunga='flat'` (thin path) or AR debit hits payment_account instead of piutang account.

- [ ] **Step 3: Patch `confirm_pendapatan`**

In `apps/pendapatan/services.py`, inside `confirm_pendapatan`, locate the credit-resolution. Just before the per-group loop (around line 309 where `has_credit_pit = False`), load the profil once:

```python
        has_credit_pit = False
        is_credit = header.payment_type == 'credit'
        piutang_acct = None
        if is_credit:
            from .models import PendapatanPiutangProfil
            try:
                piutang_acct = header.piutang_profil.coa_piutang_account
            except PendapatanPiutangProfil.DoesNotExist:
                raise ValueError(
                    f'Pendapatan {header.transaction_id} bertipe kredit tetapi belum '
                    f'memiliki profil piutang. Atur Detail Piutang sebelum konfirmasi.'
                )
```

In the POINT_IN_TIME branch (currently lines 319-331), change the debit account for credit to the piutang account, and capture the journal to link later:

```python
                if kp.recognition_type == KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME:
                    debit_acct = piutang_acct if is_credit else pay_acct
                    jh = _create_kp_journal(
                        header, eb_group, kp,
                        debit_acct=debit_acct,
                        credit_acct=kp.revenue_account,
                        amount=harga_j,
                        user=user,
                    )
                    for tax_line in kp.tax_lines.all():
                        _sync_confirm_tax_line(kp, header, tax_line, harga_j, entitas_bisnis=eb_group.entitas_bisnis, user=user)
                    if is_credit:
                        has_credit_pit = True
                        credit_ar_journals.append(jh)
```

Initialize `credit_ar_journals = []` next to `has_credit_pit = False`.

Replace the thin creation block (currently lines 386-390) with the full build + journal link:

```python
        # Case 2: build ONE full piutang for all point_in_time credit KPs, from the modal profil.
        if has_credit_pit:
            from apps.piutang.services import build_piutang
            from .services import pendapatan_to_piutang_payload  # same module; explicit for clarity
            payload, details = pendapatan_to_piutang_payload(header)
            piutang = build_piutang(payload, source='pendapatan', source_obj=header,
                                   details=details, user=user)
            # Link AR journals to the piutang for traceability (best-effort uraian tag).
            for jh in credit_ar_journals:
                jh.uraian_transaksi = f'{jh.uraian_transaksi} — {piutang.nomor_piutang}'
                jh.save(update_fields=['uraian_transaksi'])
            _log_event(header, 'PIUTANG_CREATED', description=piutang.nomor_piutang, actor=user)
```

> NOTE: `from .services import pendapatan_to_piutang_payload` inside the same module is redundant — call it directly as `pendapatan_to_piutang_payload(header)` since it's defined in this file. Use the direct call; the import line above is illustrative only and should be omitted.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.ConfirmCreditTest -v 2`
Expected: PASS.

- [ ] **Step 5: Run full pendapatan + piutang suites (regression — cash path & existing confirm tests)**

Run: `python manage.py test apps.pendapatan apps.piutang -v 1`
Expected: PASS. If pre-existing confirm tests created credit pendapatan without a profil, they now correctly raise — update those tests to add a profil (that is the new contract), or mark them as cash. Document any test you change.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/services.py apps/pendapatan/tests_piutang_integration.py
git commit -m "feat(pendapatan): build full piutang from profil at confirm; debit piutang account for credit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Extract reusable piutang form partial + JS

**Files:**
- Create: `templates/piutang/_form_body.html`
- Create: `static/js/piutang_form.js`
- Modify: `templates/piutang/form.html`
- Test: manual via Django test client (append to `apps/piutang/tests.py`)

This is a refactor: move existing markup/JS without behavior change, parameterised by an `embedded` flag.

- [ ] **Step 1: Write the regression test FIRST (guards the refactor)**

Append to `apps/piutang/tests.py`:

```python
class PiutangFormRendersTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username='u', password='p')
        self.client.force_login(self.user)

    def test_create_page_renders_wizard(self):
        resp = self.client.get('/piutang/create/')  # adjust to real URL name if different
        self.assertEqual(resp.status_code, 200)
        # Wizard markers from the partial must be present.
        self.assertContains(resp, 'Langkah 1')
        self.assertContains(resp, 'id_coa_piutang_account')
        self.assertContains(resp, 'piutang_form.js')
```

> NOTE: Resolve the real create URL with `python manage.py show_urls` (or read `apps/piutang/urls.py`) and use `reverse('piutang:create')` instead of a hardcoded path.

- [ ] **Step 2: Run test to verify current state**

Run: `python manage.py test apps.piutang.tests.PiutangFormRendersTest -v 2`
Expected: FAIL on `assertContains(resp, 'piutang_form.js')` (JS still inline). The `Langkah 1` assertion should pass already — confirming the page renders today.

- [ ] **Step 3: Create the partial**

Create `templates/piutang/_form_body.html` by moving the markup currently inside `templates/piutang/form.html` between the `<form …>` open (after line 12 `{% csrf_token %}`) and the closing button row — i.e. KARTU 1 through KARTU 7 (current lines 14-319). Wrap with an `embedded` guard around the two cards the modal hides:

- Wrap **KARTU 1's** Entitas Bisnis select block in `{% if not embedded %} … {% endif %}` (modal hides EB select; pendapatan already chose EB).
- Wrap **KARTU 7 (Detail Baris Piutang, current lines 277-319)** in `{% if not embedded %} … {% endif %}` (modal derives detail rows from KP).

Top of `_form_body.html` (no `{% extends %}` — it's an include):

```django
{# Reusable piutang wizard body. Context: form, formset, embedded (bool). #}
{# Included by templates/piutang/form.html and the pendapatan modal. #}
```

Paste the moved cards below that comment, applying the two `{% if not embedded %}` guards.

- [ ] **Step 4: Create the JS module**

Create `static/js/piutang_form.js`. Move the entire `<script>` IIFE body from `templates/piutang/form.html` (current lines 327-622) into a named function. Replace `document.getElementById(...)` / `document.querySelectorAll(...)` with lookups scoped to a `root` parameter, and accept server data via an `options` argument instead of inline template vars:

```javascript
/* Reusable piutang wizard. Call initPiutangForm(rootEl, options). */
function initPiutangForm(root, options) {
  options = options || {};
  var CALLOUTS = options.callouts || {};            // injected from template
  var EB_STANDAR_MAP = options.ebStandarMap || {};
  var EB_LABEL_MAP = { 'psak': 'SAK (Full IFRS)', 'sak_ep': 'SAK EP', 'sak_emkm': 'SAK EMKM' };
  var $ = function (sel) { return root.querySelector(sel); };
  var $$ = function (sel) { return root.querySelectorAll(sel); };

  // … paste the existing logic here, replacing:
  //   document.getElementById('id_x')      -> root.querySelector('#id_x')
  //   document.querySelectorAll('.x')      -> root.querySelectorAll('.x')
  //   {{ eb_options_json }} / {{ eb_selected }} -> options.ebOptions / options.ebSelected
  //   {{ eb_standar_map_json }}            -> options.ebStandarMap
  // Detail-row logic (current lines 569-616) must no-op when its elements are absent
  //   (modal has no detail table): guard `if (!tbody) return;` early in that block.
}
```

Keep the `CALLOUTS` and `RESULT_CONFIGS` objects (current lines 330-403) inside the function unchanged — they are static. Only `EB_STANDAR_MAP`, `eb_options`, and `eb_selected` come from `options`.

- [ ] **Step 5: Rewire `templates/piutang/form.html`**

Replace the moved markup with an include, and replace the inline script with a `<script src>` + an init call that passes the existing template JSON vars:

```django
<form method="post" id="piutang-form">
  {% csrf_token %}
  {% include 'piutang/_form_body.html' with embedded=False %}
  <div class="ni-btn-row">
    <button type="submit" class="ni-btn ni-btn--primary">Simpan Piutang</button>
    <a href="{% url 'piutang:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
  </div>
</form>

{% load static %}
<script src="{% static 'js/piutang_form.js' %}"></script>
<script>
  initPiutangForm(document, {
    ebStandarMap: {{ eb_standar_map_json|default:"{}"|safe }},
    ebOptions: {{ eb_options_json|default:"[]"|safe }},
    ebSelected: '{{ eb_selected|default:""|escapejs }}'
  });
</script>
```

- [ ] **Step 6: Run the regression test**

Run: `python manage.py test apps.piutang.tests.PiutangFormRendersTest -v 2`
Expected: PASS (all three asserts).

- [ ] **Step 7: Manual smoke test**

Run: `python manage.py runserver` and open the piutang create page. Verify: standar callout updates, business-model/SPPI cards select, long-term toggles cards, detail rows add/remove, TomSelect on accounts works. (See `superpowers:verification-before-completion`.)

- [ ] **Step 8: Commit**

```bash
git add templates/piutang/_form_body.html templates/piutang/form.html static/js/piutang_form.js apps/piutang/tests.py
git commit -m "refactor(piutang): extract reusable form partial and piutang_form.js

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Pendapatan modal + glue JS

**Files:**
- Modify: `templates/pendapatan/form.html` (add button near payment_type ~line 99; add modal before `</form>` at line 314; add glue JS in the script block)
- Test: manual via Django test client (covered by Task 7 view test for POST; this task is UI wiring)

- [ ] **Step 1: Add the "Atur Detail Piutang" trigger + status badge**

In `templates/pendapatan/form.html`, immediately after the payment_type form-group (after current line 102), add:

```django
        <div class="ni-form-group" id="piutang-trigger-group" style="display:none">
          <label class="ni-form-label">Detail Piutang (Kredit)</label>
          <div style="display:flex;gap:10px;align-items:center">
            <button type="button" class="ni-btn ni-btn--secondary" id="open-piutang-modal">Atur Detail Piutang</button>
            <span id="piutang-status-badge" class="ni-badge ni-badge--warning">Belum diatur</span>
          </div>
        </div>
```

- [ ] **Step 2: Add the modal + embedded form body before `</form>`**

The pendapatan view must pass a `piutang_form` (a `PiutangHeaderForm(prefix='piutang')`) and the EB standar map into the context (wired in Task 7). Insert before line 314 `</form>`:

```django
  <div id="piutang-modal" class="ni-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;overflow:auto">
    <div class="ni-modal__dialog" style="background:var(--ni-surface,#fff);max-width:900px;margin:32px auto;border-radius:10px;padding:20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 class="ni-card__title">Detail Piutang</h2>
        <button type="button" class="ni-btn ni-btn--xs" id="close-piutang-modal">&#10005;</button>
      </div>
      <div id="piutang-modal-body">
        {% with form=piutang_form formset=None %}
          {% include 'piutang/_form_body.html' with embedded=True %}
        {% endwith %}
      </div>
      <div class="ni-btn-row" style="margin-top:14px">
        <button type="button" class="ni-btn ni-btn--primary" id="save-piutang-modal">Simpan Detail Piutang</button>
        <button type="button" class="ni-btn ni-btn--secondary" id="cancel-piutang-modal">Batal</button>
      </div>
    </div>
  </div>
  <div id="piutang-hidden-fields"></div>
```

> NOTE: The `_form_body.html` partial references `form.<field>` for the piutang form. Because it's rendered inside the pendapatan `<form>`, its inputs carry the `piutang-` prefix automatically (the prefix comes from `PiutangHeaderForm(prefix='piutang')` instantiated in the view). On submit they post alongside pendapatan fields — no separate copy needed for the wizard's own inputs. The hidden-fields div is only for the JS-derived debitur/detail mirror values described below.

- [ ] **Step 3: Add glue JS**

Inside the existing `<script>` block of `templates/pendapatan/form.html` (after the `payTypeSel` lookup at ~line 841), add:

```javascript
  /* ── Piutang modal wiring ───────────────────────────────────────── */
  var piutangTriggerGroup = document.getElementById('piutang-trigger-group');
  var piutangModal   = document.getElementById('piutang-modal');
  var openPiutangBtn = document.getElementById('open-piutang-modal');
  var closePiutangBtn= document.getElementById('close-piutang-modal');
  var cancelPiutangBtn = document.getElementById('cancel-piutang-modal');
  var savePiutangBtn = document.getElementById('save-piutang-modal');
  var piutangBadge   = document.getElementById('piutang-status-badge');
  var pendapatanForm = document.getElementById('pendapatan-form');
  var piutangConfigured = {{ piutang_profil_exists|yesno:"true,false" }};

  function isCredit() { return payTypeSel && payTypeSel.value === 'credit'; }

  function syncPiutangTriggerVisibility() {
    if (piutangTriggerGroup) piutangTriggerGroup.style.display = isCredit() ? '' : 'none';
  }
  function setBadge(ok) {
    if (!piutangBadge) return;
    piutangBadge.textContent = ok ? 'Sudah diatur' : 'Belum diatur';
    piutangBadge.className = 'ni-badge ' + (ok ? 'ni-badge--success' : 'ni-badge--warning');
  }

  if (payTypeSel) payTypeSel.addEventListener('change', syncPiutangTriggerVisibility);
  syncPiutangTriggerVisibility();
  setBadge(piutangConfigured);

  // Init the wizard inside the modal once, scoped to the modal element.
  if (piutangModal && typeof initPiutangForm === 'function') {
    initPiutangForm(piutangModal, {
      ebStandarMap: {{ eb_standar_map_json|default:"{}"|safe }},
      ebOptions: [], ebSelected: ''
    });
  }

  function prefillPiutangFromKP() {
    // Debitur ← entitas bisnis label (from the EB TomSelect already on the page).
    var ebSel = document.getElementById('id_eb_selection');
    var debiturInput = piutangModal.querySelector('#id_piutang-debitur');
    if (debiturInput && ebSel && ebSel.selectedOptions.length) {
      if (!debiturInput.value) debiturInput.value = ebSel.selectedOptions[0].textContent.trim();
    }
    // Detail rows are derived server-side from KP at confirm; show a read-only summary.
    var summary = piutangModal.querySelector('#piutang-detail-summary');
    if (summary) {
      var rows = [];
      document.querySelectorAll('.item-card').forEach(function (card) {  // adjust selector to KP item container
        var desc = card.querySelector('input[name$="-deskripsi_item"]');
        var amt  = card.querySelector('input[name$="-nilai_kontrak"]');
        if (desc && amt && amt.value) rows.push((desc.value || '(item)') + ' — ' + amt.value);
      });
      summary.innerHTML = rows.length ? rows.map(function (r){return '<li>'+r+'</li>';}).join('') : '<li>(belum ada item)</li>';
    }
  }

  if (openPiutangBtn) openPiutangBtn.addEventListener('click', function () {
    prefillPiutangFromKP();
    piutangModal.style.display = '';
  });
  function closeModal() { piutangModal.style.display = 'none'; }
  if (closePiutangBtn) closePiutangBtn.addEventListener('click', closeModal);
  if (cancelPiutangBtn) cancelPiutangBtn.addEventListener('click', closeModal);

  if (savePiutangBtn) savePiutangBtn.addEventListener('click', function () {
    // Minimal client check: piutang account chosen.
    var acct = piutangModal.querySelector('#id_piutang-coa_piutang_account');
    if (acct && !acct.value) { acct.focus(); alert('Pilih Akun Piutang terlebih dahulu.'); return; }
    setBadge(true);
    piutangConfigured = true;
    closeModal();
  });

  // Block submit if credit but not configured.
  if (pendapatanForm) pendapatanForm.addEventListener('submit', function (e) {
    if (isCredit() && !piutangConfigured) {
      e.preventDefault();
      alert('Transaksi kredit memerlukan Detail Piutang. Klik "Atur Detail Piutang".');
      if (piutangTriggerGroup) piutangTriggerGroup.scrollIntoView({behavior:'smooth'});
    }
  });
```

> NOTE: Adjust the KP item container selector (`.item-card`, `input[name$="-deskripsi_item"]`, `input[name$="-nilai_kontrak"]`) to the real markup in `templates/pendapatan/form.html` (inspect the item card structure around the `item_forms` loop). Add an empty `<ul id="piutang-detail-summary">` inside `_form_body.html` under an `{% if embedded %}` block where the detail card used to be, so the modal shows the derived rows.

- [ ] **Step 4: Add the embedded detail summary to the partial**

In `templates/piutang/_form_body.html`, where KARTU 7 is wrapped `{% if not embedded %}`, add an `{% else %}` branch:

```django
  {% if not embedded %}
    {# … existing KARTU 7 detail table … #}
  {% else %}
  <div class="ni-card ni-animate-fade-in">
    <div class="ni-card__header"><h2 class="ni-card__title">Baris Piutang (otomatis dari item pendapatan)</h2></div>
    <div class="ni-card__body">
      <ul id="piutang-detail-summary" style="margin:0;padding-left:18px"></ul>
      <p class="ni-text-muted" style="font-size:.82em;margin-top:8px">Baris ini mengikuti item pendapatan dan tidak diubah di sini.</p>
    </div>
  </div>
  {% endif %}
```

- [ ] **Step 5: Manual smoke test**

Run `python manage.py runserver`, open pendapatan create, switch payment type to Kredit → trigger appears; open modal → wizard renders, debitur prefilled, summary lists items; choose piutang account → Simpan → badge "Sudah diatur"; try submit without configuring → blocked.

- [ ] **Step 6: Commit**

```bash
git add templates/pendapatan/form.html templates/piutang/_form_body.html
git commit -m "feat(pendapatan): add inline piutang modal to credit transaction form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Wire pendapatan views to validate + persist the profil

**Files:**
- Modify: `apps/pendapatan/views.py` (`pendapatan_create` lines 123-170, `pendapatan_edit` lines 173-299)
- Test: `apps/pendapatan/tests_piutang_integration.py`

- [ ] **Step 1: Write the failing view tests**

Append to `apps/pendapatan/tests_piutang_integration.py`:

```python
class PendapatanCreateViewProfilTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username='u', password='p')
        self.client.force_login(self.user)

    def _akun(self, kode, nama, kategori_id='aset'):
        kat, _ = KategoriAkun.objects.get_or_create(
            id=kategori_id, defaults={'nama': kategori_id.title()})
        return Akun.objects.create(kode_akun=kode, nama_akun=nama, kategori=kat)

    def _base_post(self, eb, stt, akun_pend, akun_pay):
        return {
            'tanggal': '2026-01-10', 'deskripsi': 'Uji', 'payment_type': 'credit',
            'standar_akuntansi': 'PSAK_71_72', 'eb_selection': f'lv1:{eb.pk}',
            'item_count': '1',
            'item_0-deskripsi_item': 'Jasa', 'item_0-kategori': 'jasa',
            'item_0-sub_transaction_type': str(stt.pk),
            'item_0-nilai_kontrak': '2000',
            'item_0-revenue_account': str(akun_pend.pk),
            'item_0-payment_account': str(akun_pay.pk),
            'item_0-recognition_type': 'point_in_time',
        }

    def test_credit_post_with_piutang_fields_saves_profil(self):
        from apps.entitas_bisnis.models import EntitasBisnis
        from apps.pendapatan.models import PendapatanHeader, PendapatanPiutangProfil
        eb = EntitasBisnis.objects.create(nama='PT Alpha', standar_akuntansi='psak')
        stt = SubTransactionType.objects.create(
            nama='Jasa', module='pendapatan', direction='inflow',
            default_offset_account=self._akun('2.1.9', 'Off'))
        akun_pend = self._akun('4.1.1', 'Pend', kategori_id='pendapatan')
        akun_pay = self._akun('1.1.1', 'Kas')
        akun_piutang = self._akun('1.1.4', 'Piutang')
        data = self._base_post(eb, stt, akun_pend, akun_pay)
        data.update({
            'piutang-tanggal': '2026-01-10',
            'piutang-coa_piutang_account': str(akun_piutang.pk),
            'piutang-jenis_jangka_waktu': 'short_term',
            'piutang-jenis_bunga': 'tanpa_bunga',
            'piutang-periode_angsuran': 'bulanan',
            'piutang-kategori_pengukuran': 'amortised_cost',
            'piutang-debitur': 'PT Alpha',
        })
        resp = self.client.post('/pendapatan/create/', data)  # use reverse('pendapatan:create')
        self.assertEqual(resp.status_code, 302)
        header = PendapatanHeader.objects.latest('id')
        self.assertTrue(PendapatanPiutangProfil.objects.filter(pendapatan_header=header).exists())
        self.assertEqual(header.piutang_profil.coa_piutang_account, akun_piutang)

    def test_credit_post_without_piutang_account_rejected(self):
        from apps.entitas_bisnis.models import EntitasBisnis
        from apps.pendapatan.models import PendapatanHeader
        eb = EntitasBisnis.objects.create(nama='PT Beta', standar_akuntansi='psak')
        stt = SubTransactionType.objects.create(
            nama='Jasa', module='pendapatan', direction='inflow',
            default_offset_account=self._akun('2.1.9', 'Off'))
        akun_pend = self._akun('4.1.1', 'Pend', kategori_id='pendapatan')
        akun_pay = self._akun('1.1.1', 'Kas')
        data = self._base_post(eb, stt, akun_pend, akun_pay)  # no piutang-* fields
        resp = self.client.post('/pendapatan/create/', data)
        self.assertEqual(resp.status_code, 200)  # re-render with error
        self.assertEqual(PendapatanHeader.objects.count(), 0)
```

> NOTE: Use `reverse('pendapatan:create')` (read `apps/pendapatan/urls.py` for the name). Confirm `payment_type` POST value is `'credit'` and `standar_akuntansi` choice value matches `StandarAkuntansi` (`PSAK_71_72`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.PendapatanCreateViewProfilTest -v 2`
Expected: FAIL — no profil saved (view ignores `piutang-*`), and credit-without-account is accepted.

- [ ] **Step 3: Add a profil helper + wire `pendapatan_create`**

In `apps/pendapatan/views.py`, add a helper near the top (after `_parse_tax_lines_from_post`):

```python
def _save_piutang_profil(request, header):
    """Validate piutang-* POST via PiutangHeaderForm(prefix='piutang') and upsert
    PendapatanPiutangProfil on the header. Returns (ok, piutang_form)."""
    from apps.piutang.forms import PiutangHeaderForm
    from .models import PendapatanPiutangProfil, PIUTANG_PROFIL_FIELDS

    pf = PiutangHeaderForm(request.POST, prefix='piutang')
    if not pf.is_valid():
        return False, pf
    cd = pf.cleaned_data
    defaults = {f: cd.get(f) for f in PIUTANG_PROFIL_FIELDS if f in cd}
    # Non-nullable defaults safety:
    defaults.setdefault('suku_bunga', 0)
    defaults.setdefault('biaya_transaksi', 0)
    PendapatanPiutangProfil.objects.update_or_create(
        pendapatan_header=header, defaults=defaults)
    return True, pf
```

In `pendapatan_create`, after `header = create_pendapatan_header(...)` succeeds (after line 153) but still inside the `try`, when `payment_type == 'credit'`:

```python
                if cd['payment_type'] == 'credit':
                    ok, piutang_form = _save_piutang_profil(request, header)
                    if not ok:
                        header.delete()  # roll back the just-created header
                        form.add_error(None, 'Detail piutang belum lengkap atau tidak valid.')
                        raise ValueError('__piutang_invalid__')  # jump to except, re-render
```

Wrap the existing `except ValueError as exc:` (line 156) to skip re-adding the sentinel:

```python
            except ValueError as exc:
                if str(exc) != '__piutang_invalid__':
                    form.add_error(None, str(exc))
```

Add `piutang_form` + context flags to BOTH render calls in `pendapatan_create`. At the GET branch (line 159-160) and the final `render` (line 163), include:

```python
    from apps.piutang.forms import PiutangHeaderForm
    piutang_form = PiutangHeaderForm(prefix='piutang')  # GET; for POST-invalid reuse the validated one
    # … add to context dict:
        'piutang_form': piutang_form,
        'piutang_profil_exists': False,
        'eb_standar_map_json': _pendapatan_eb_standar_map_json(),
```

Add the standar-map helper (mirrors piutang view) near the top of `views.py`:

```python
def _pendapatan_eb_standar_map_json():
    from apps.entitas_bisnis.models import EntitasBisnis
    rows = EntitasBisnis.objects.filter(status_aktif=True).values('pk', 'standar_akuntansi')
    return json.dumps({f'lv1:{r["pk"]}': r['standar_akuntansi'] for r in rows})
```

> NOTE: On a POST that fails piutang validation, pass the *validated* `piutang_form` (with errors) into the context instead of a fresh one so the modal shows field errors. Restructure the create view so the context is built once at the end with whatever `piutang_form` is in scope.

- [ ] **Step 4: Wire `pendapatan_edit` the same way**

In `pendapatan_edit`, after the KP rebuild succeeds (inside the `transaction.atomic()` block, after the items loop ~line 247) when `header.payment_type == 'credit'`, call `_save_piutang_profil(request, header)`; if not ok, raise to trigger the `except` and re-render. For the GET branch (line 254), pre-fill the modal from the existing profil:

```python
        from apps.piutang.forms import PiutangHeaderForm
        from .models import PendapatanPiutangProfil
        profil = PendapatanPiutangProfil.objects.filter(pendapatan_header=header).first()
        piutang_form = PiutangHeaderForm(
            prefix='piutang',
            initial={f: getattr(profil, f) for f in __import__('apps.pendapatan.models', fromlist=['PIUTANG_PROFIL_FIELDS']).PIUTANG_PROFIL_FIELDS} if profil else None,
        )
```

Prefer a clean import at the top of the function:

```python
        from .models import PIUTANG_PROFIL_FIELDS, PendapatanPiutangProfil
        profil = PendapatanPiutangProfil.objects.filter(pendapatan_header=header).first()
        initial = {f: getattr(profil, f) for f in PIUTANG_PROFIL_FIELDS} if profil else None
        piutang_form = PiutangHeaderForm(prefix='piutang', initial=initial)
```

Add to the edit-view context (line 290 render):

```python
        'piutang_form': piutang_form,
        'piutang_profil_exists': bool(profil),
        'eb_standar_map_json': _pendapatan_eb_standar_map_json(),
```

Also: when payment_type is changed away from credit on edit, delete any existing profil:

```python
                    if header.payment_type != 'credit':
                        PendapatanPiutangProfil.objects.filter(pendapatan_header=header).delete()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test apps.pendapatan.tests_piutang_integration.PendapatanCreateViewProfilTest -v 2`
Expected: PASS.

- [ ] **Step 6: Run the whole feature + regression suite**

Run: `python manage.py test apps.pendapatan apps.piutang -v 1`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/pendapatan/views.py apps/pendapatan/tests_piutang_integration.py
git commit -m "feat(pendapatan): validate and persist piutang profil on create/edit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: End-to-end verification + cleanup

**Files:**
- Modify: none expected (verification); fix anything surfaced.

- [ ] **Step 1: Full E2E manual run**

`python manage.py runserver`. Create a **credit** pendapatan with 2 KP items → open modal → set piutang account + jatuh tempo + bunga → save → submit → confirm. Verify in piutang list a new `TRX-PIU-xxxx` exists with the credit terms and 2 detail rows; verify the journal debits the chosen piutang account. Then create a **cash** pendapatan and confirm the modal/trigger never appears and behavior is unchanged.

- [ ] **Step 2: Confirm the deprecated thin path is gone**

Run: `grep -rn "create_piutang_from_pendapatan" apps/`
Expected: only the thin wrapper (now delegating to `build_piutang` via the adapter) and its callers remain; no code path builds a piutang missing the credit terms. If a caller other than `confirm_pendapatan` exists, verify it still works.

- [ ] **Step 3: Run the entire test suite**

Run: `python manage.py test -v 1`
Expected: PASS (or only pre-existing unrelated failures; document them).

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "test(pendapatan): end-to-end verification of pendapatan-piutang credit flow

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes (verification against spec)

- Spec §3.1 Form layer → Task 7 instantiates `PiutangHeaderForm(prefix='piutang')`; Task 5/6 reuse the same form. ✓
- Spec §3.2 Template partial → Task 5 (`_form_body.html`), Task 6 includes it embedded. ✓
- Spec §3.3 JS init → Task 5 (`piutang_form.js` / `initPiutangForm`). ✓
- Spec §4.1 Model → Task 1. ✓
- Spec §4.2 `build_piutang` → Task 2. ✓
- Spec §4.3 Adapter → Task 3. ✓
- Spec §5.1 UX flow (trigger, modal, prefill, block submit) → Task 6 + Task 7. ✓
- Spec §5.2 Accounting fix (debit piutang account for credit; link journal; no double AR) → Task 4. ✓
- Spec §6 Edge cases (no profil blocked server-side, cash↔credit, edit prefill, KP-derived details) → Task 3 (raise), Task 4 (raise), Task 7 (delete on cash, prefill on edit). ✓
- Spec §7 Back-compat (additive migration, wrapper kept) → Task 1, Task 2. ✓
- Spec §8 Testing → unit (Tasks 2,3), integration (Tasks 4,7), regression (Task 5). ✓
- Spec §9 YAGNI (no sales wiring, no per-EB split, no ECL in modal) → respected; `build_piutang` supports `source='sales'` but not wired. ✓
```
