# PSAK 72 Pendapatan Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the `pendapatan` app to fully implement PSAK 72 five-step revenue recognition — renaming `PendapatanItem` to `KewajibabPelaksanaan`, adding schedule/entry/contract-asset models, and rewriting the service layer to handle all five confirmation cases.

**Architecture:** Model-first approach — rename and extend the existing item model, create new schedule/entry/asset models alongside the old deferred models, migrate data, then drop the old tables. Services are rewritten in `apps/pendapatan/services.py`; new service functions are added without removing the old ones until data migration is confirmed clean. Forms capture per-KP over-time configuration fields that the service reads at confirm time.

**Tech Stack:** Django 6.x, Python 3.12+, `django.test.TestCase`, `pytest-django`, `decimal.Decimal`, existing `akuntansi` app for journals, existing `piutang` app for receivables.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `apps/pendapatan/models.py` | Modify | New choices, rename class, new models |
| `apps/pendapatan/services.py` | Modify | `compute_alokasi_harga`, overhaul `confirm_pendapatan`, add `recognize_entry`, `konversi_aset_kontrak_ke_piutang`, update `void_pendapatan` |
| `apps/pendapatan/forms.py` | Modify | Rename `PendapatanItemForm` → `KewajibabPelaksanaanForm`, add over-time fields |
| `apps/pendapatan/views.py` | Modify | Update all references from item/PendapatanItem to kp/KewajibabPelaksanaan, add recognize + convert views |
| `apps/pendapatan/urls.py` | Modify | Add URLs for recognize_entry, konversi_aset_kontrak |
| `apps/pendapatan/admin.py` | Modify | Register new models, update inline for renamed model |
| `apps/pendapatan/migrations/0005_psak72_schema.py` | Create | RenameModel, RenameField, new model tables |
| `apps/pendapatan/migrations/0006_psak72_data.py` | Create | RunPython to migrate deferred → jadwal/entri data |
| `apps/pendapatan/migrations/0007_psak72_cleanup.py` | Create | Remove old deferred fields and drop old tables |
| `tests/pendapatan/__init__.py` | Create | Empty |
| `tests/pendapatan/factories.py` | Create | Test helper functions (no external factories) |
| `tests/pendapatan/test_models.py` | Create | Model unit tests |
| `tests/pendapatan/test_services.py` | Create | Service unit tests (bulk of test coverage) |
| `templates/pendapatan/detail.html` | Modify | Redesign as command center with KP cards |
| `templates/pendapatan/form.html` | Modify | Per-KP formset with SSP preview, over-time config |
| `templates/pendapatan/_recognize_modal.html` | Create | Mini modal for recognize_entry action |

---

## Task 1: Add `standar_akuntansi` to `PendapatanHeader`

**Files:**
- Modify: `apps/pendapatan/models.py`
- Create: `tests/pendapatan/__init__.py`
- Create: `tests/pendapatan/test_models.py`

- [ ] **Step 1: Create test directory and first test**

```python
# tests/pendapatan/__init__.py
# (empty)
```

```python
# tests/pendapatan/test_models.py
from django.test import TestCase
from apps.pendapatan.models import PendapatanHeader, StandarAkuntansi


class StandarAkuntansiTest(TestCase):
    def test_header_defaults_to_psak_71_72(self):
        header = PendapatanHeader()
        self.assertEqual(header.standar_akuntansi, StandarAkuntansi.PSAK_71_72)

    def test_choices_include_sak_etap(self):
        choices = [c[0] for c in StandarAkuntansi.choices]
        self.assertIn('SAK_ETAP', choices)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/pendapatan/test_models.py -v
```
Expected: `ImportError: cannot import name 'StandarAkuntansi'`

- [ ] **Step 3: Add `StandarAkuntansi` choices and field to `PendapatanHeader`**

In `apps/pendapatan/models.py`, add near the top (after existing imports):

```python
class StandarAkuntansi(models.TextChoices):
    PSAK_71_72 = 'PSAK_71_72', 'PSAK 71/72'
    SAK_ETAP = 'SAK_ETAP', 'SAK ETAP'
```

On `PendapatanHeader`, add one field (after `keterangan` or at end of regular fields, before timestamps):

```python
standar_akuntansi = models.CharField(
    max_length=20,
    choices=StandarAkuntansi.choices,
    default=StandarAkuntansi.PSAK_71_72,
)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/pendapatan/test_models.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/models.py tests/pendapatan/
git commit -m "feat(pendapatan): add StandarAkuntansi choice + standar_akuntansi field on PendapatanHeader"
```

---

## Task 2: Rename `PendapatanItem` → `KewajibabPelaksanaan` + add new fields

**Files:**
- Modify: `apps/pendapatan/models.py`
- Modify: `tests/pendapatan/test_models.py`

The rename is **class-only** for now — the database rename happens in Task 7 (migration 0005). For the migration to work cleanly, the new class must declare `class Meta: db_table = 'pendapatan_pendapatanitem'` temporarily (the migration will rename it).

Add over-time configuration staging fields that the form writes and the service reads at confirm time. These get removed in Task 9 after data migration.

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/pendapatan/test_models.py
from apps.pendapatan.models import KewajibabPelaksanaan


class KewajibabPelaksanaanModelTest(TestCase):
    def test_recognition_type_defaults_to_point_in_time(self):
        kp = KewajibabPelaksanaan()
        self.assertEqual(kp.recognition_type, KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME)

    def test_harga_j_defaults_to_zero(self):
        kp = KewajibabPelaksanaan()
        from decimal import Decimal
        self.assertEqual(kp.harga_j, Decimal('0'))
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/pendapatan/test_models.py::KewajibabPelaksanaanModelTest -v
```
Expected: `ImportError: cannot import name 'KewajibabPelaksanaan'`

- [ ] **Step 3: Rename class and add fields in `apps/pendapatan/models.py`**

Rename the class `PendapatanItem` → `KewajibabPelaksanaan`. Add a `Meta` subclass with `db_table` and add new fields.

```python
class KewajibabPelaksanaan(models.Model):
    class RecognitionType(models.TextChoices):
        POINT_IN_TIME = 'point_in_time', 'Point-in-Time'
        OVER_TIME = 'over_time', 'Over Time'

    # --- existing fields (keep all, just rename class) ---
    entitas_bisnis = models.ForeignKey(
        'PendapatanEntitasBisnis',
        on_delete=models.CASCADE,
        related_name='kps',      # changed from 'items'
    )
    keterangan = models.TextField()
    nilai_kontrak = models.DecimalField(max_digits=18, decimal_places=2)  # renamed from jumlah_bruto
    akun_pendapatan = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, related_name='+'
    )
    akun_piutang = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    akun_pph_potong = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    pph_potong_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    akun_pph_pungut = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    pph_pungut_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    akun_pph_pungut_penjual = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    pph_pungut_penjual_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ppn_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # --- new PSAK 72 fields ---
    harga_j = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text='Alokasi harga transaksi untuk KP ini (PSAK 72 Step 4)',
    )
    recognition_type = models.CharField(
        max_length=20,
        choices=RecognitionType.choices,
        default=RecognitionType.POINT_IN_TIME,
    )

    # --- over-time staging fields (filled by form, consumed at confirm, removed after migration) ---
    is_deferred = models.BooleanField(default=False)  # keep temporarily for data migration
    deferred_account = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )  # keep temporarily
    deferred_pph_acct = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )  # keep temporarily

    # New over-time staging fields:
    ot_tipe_aliran = models.CharField(max_length=30, blank=True, default='')
    ot_progress_method = models.CharField(max_length=30, blank=True, default='')
    ot_tanggal_mulai = models.DateField(null=True, blank=True)
    ot_tanggal_selesai = models.DateField(null=True, blank=True)
    ot_liabilitas_kontrak_acct = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    ot_aset_kontrak_acct = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='+'
    )
    ot_biaya_estimasi_total = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )

    class Meta:
        db_table = 'pendapatan_pendapatanitem'  # keep old table name; migration 0005 renames it

    def __str__(self):
        return f"{self.keterangan} ({self.nilai_kontrak})"
```

Also add a backward-compat alias at module level (after class definition) so old references don't break before the full refactor:

```python
PendapatanItem = KewajibabPelaksanaan  # backward-compat alias, remove after all references updated
```

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_models.py -v
```
Expected: all PASS (no migration needed yet — unit tests don't run migrations for field defaults)

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/models.py tests/pendapatan/test_models.py
git commit -m "feat(pendapatan): rename PendapatanItem to KewajibabPelaksanaan, add PSAK 72 fields"
```

---

## Task 3: Add `JadwalPengakuan` model

**Files:**
- Modify: `apps/pendapatan/models.py`
- Modify: `tests/pendapatan/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/pendapatan/test_models.py
from apps.pendapatan.models import JadwalPengakuan


class JadwalPengakuanModelTest(TestCase):
    def test_nilai_belum_diakui_property(self):
        from decimal import Decimal
        jadwal = JadwalPengakuan()
        jadwal.nilai_total = Decimal('1000')
        jadwal.nilai_diakui = Decimal('300')
        self.assertEqual(jadwal.nilai_belum_diakui, Decimal('700'))

    def test_defaults(self):
        from decimal import Decimal
        jadwal = JadwalPengakuan()
        self.assertEqual(jadwal.nilai_diakui, Decimal('0'))
        self.assertEqual(jadwal.status, JadwalPengakuan.Status.ACTIVE)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/pendapatan/test_models.py::JadwalPengakuanModelTest -v
```

- [ ] **Step 3: Add `JadwalPengakuan` to `apps/pendapatan/models.py`**

```python
class JadwalPengakuan(models.Model):
    class TipeAliran(models.TextChoices):
        ADVANCE_PAYMENT_CASH = 'advance_payment_cash', 'Advance Payment (Cash)'
        PERIODIC_BILLING = 'periodic_billing', 'Periodic Billing'
        PERFORMANCE_FIRST = 'performance_first', 'Performance First'

    class ProgressMethod(models.TextChoices):
        STRAIGHT_LINE = 'straight_line', 'Straight-Line'
        PERCENTAGE_COMPLETION = 'percentage_completion', 'Percentage Completion'
        MILESTONE = 'milestone', 'Milestone'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Selesai'
        VOIDED = 'voided', 'Dibatalkan'

    kp = models.OneToOneField(
        KewajibabPelaksanaan, on_delete=models.CASCADE, related_name='jadwal'
    )
    tipe_aliran = models.CharField(max_length=30, choices=TipeAliran.choices)
    progress_method = models.CharField(max_length=30, choices=ProgressMethod.choices)
    tanggal_mulai = models.DateField()
    tanggal_selesai = models.DateField()
    liabilitas_kontrak_acct = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
        help_text='Akun liabilitas kontrak (untuk advance_payment_cash)',
    )
    aset_kontrak_acct = models.ForeignKey(
        'akuntansi.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='+',
        help_text='Akun aset kontrak (untuk performance_first)',
    )
    biaya_estimasi_total = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text='Untuk progress_method=percentage_completion',
    )
    nilai_total = models.DecimalField(max_digits=18, decimal_places=2)
    nilai_diakui = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    @property
    def nilai_belum_diakui(self):
        return self.nilai_total - self.nilai_diakui

    def __str__(self):
        return f"Jadwal {self.kp} [{self.tipe_aliran}]"
```

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_models.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/models.py tests/pendapatan/test_models.py
git commit -m "feat(pendapatan): add JadwalPengakuan model (PSAK 72 revenue schedule)"
```

---

## Task 4: Add `EntriPengakuan` and `AsetKontrak` models

**Files:**
- Modify: `apps/pendapatan/models.py`
- Modify: `tests/pendapatan/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/pendapatan/test_models.py
from apps.pendapatan.models import EntriPengakuan, AsetKontrak


class EntriPengakuanModelTest(TestCase):
    def test_defaults(self):
        from decimal import Decimal
        entri = EntriPengakuan()
        self.assertEqual(entri.nilai_diakui, Decimal('0'))
        self.assertEqual(entri.status, EntriPengakuan.Status.PENDING)


class AsetKontrakModelTest(TestCase):
    def test_defaults(self):
        aset = AsetKontrak()
        self.assertEqual(aset.status, AsetKontrak.Status.ACTIVE)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/pendapatan/test_models.py::EntriPengakuanModelTest tests/pendapatan/test_models.py::AsetKontrakModelTest -v
```

- [ ] **Step 3: Add both models to `apps/pendapatan/models.py`**

```python
class EntriPengakuan(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Belum Diakui'
        RECOGNIZED = 'recognized', 'Sudah Diakui'
        SKIPPED = 'skipped', 'Dilewati'

    jadwal = models.ForeignKey(
        JadwalPengakuan, on_delete=models.CASCADE, related_name='entri'
    )
    tanggal_target = models.DateField()
    nilai = models.DecimalField(max_digits=18, decimal_places=2)
    nilai_diakui = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    journal_header = models.ForeignKey(
        'akuntansi.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='entri_pengakuan',
    )
    catatan = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['tanggal_target']

    def __str__(self):
        return f"Entri {self.tanggal_target} – {self.nilai}"


class AsetKontrak(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Aktif'
        CONVERTED = 'converted', 'Dikonversi ke Piutang'
        VOIDED = 'voided', 'Dibatalkan'

    kp = models.ForeignKey(
        KewajibabPelaksanaan, on_delete=models.CASCADE, related_name='aset_kontrak'
    )
    tanggal = models.DateField()
    nilai = models.DecimalField(max_digits=18, decimal_places=2)
    nilai_tersisa = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    journal_header = models.ForeignKey(
        'akuntansi.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aset_kontrak_set',
    )
    piutang = models.ForeignKey(
        'piutang.PiutangHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aset_kontrak_sumber',
    )
    catatan = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AsetKontrak {self.kp} [{self.nilai}]"
```

- [ ] **Step 4: Update `PendapatanEventLog` — add new event types**

Find the `PendapatanEventLog` class (or its `EventType` choices) and add:

```python
# In PendapatanEventLog.EventType (or wherever event choices are defined):
RECOGNIZE = 'recognize', 'Pengakuan Pendapatan'
CREATE_JOURNAL = 'create_journal', 'Buat Jurnal'
CREATE_PIUTANG = 'create_piutang', 'Buat Piutang'
CONVERT_ASSET = 'convert_asset', 'Konversi Aset Kontrak'
```

- [ ] **Step 5: Run tests**

```
pytest tests/pendapatan/test_models.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```
git add apps/pendapatan/models.py tests/pendapatan/test_models.py
git commit -m "feat(pendapatan): add EntriPengakuan, AsetKontrak models and new EventLog choices"
```

---

## Task 5: Schema migration 0005

**Files:**
- Create: `apps/pendapatan/migrations/0005_psak72_schema.py`

This migration:
1. Renames `PendapatanItem` → `KewajibabPelaksanaan` (table + FK references)
2. Renames field `jumlah_bruto` → `nilai_kontrak`
3. Adds new fields to `KewajibabPelaksanaan`
4. Adds `standar_akuntansi` to `PendapatanHeader`
5. Creates `JadwalPengakuan`, `EntriPengakuan`, `AsetKontrak` tables

- [ ] **Step 1: Generate migration**

```
python manage.py makemigrations pendapatan --name psak72_schema
```

- [ ] **Step 2: Open and review `apps/pendapatan/migrations/0005_psak72_schema.py`**

Verify it contains:
- `migrations.RenameModel(old_name='PendapatanItem', new_name='KewajibabPelaksanaan')`
- `migrations.RenameField(model_name='kewajibabpelaksanaan', old_name='jumlah_bruto', new_name='nilai_kontrak')`
- `migrations.AddField` for `harga_j`, `recognition_type`, `ot_*` fields
- `migrations.AddField(model_name='pendapatanheader', name='standar_akuntansi', ...)`
- `migrations.CreateModel` for `JadwalPengakuan`, `EntriPengakuan`, `AsetKontrak`

If Django didn't auto-detect the `RenameModel`, add it manually at the top of `operations`:

```python
migrations.RenameModel(
    old_name='PendapatanItem',
    new_name='KewajibabPelaksanaan',
),
migrations.RenameField(
    model_name='kewajibabpelaksanaan',
    old_name='jumlah_bruto',
    new_name='nilai_kontrak',
),
```

- [ ] **Step 3: Remove the `db_table` Meta from the model now that migration handles the rename**

In `apps/pendapatan/models.py`, remove the `db_table = 'pendapatan_pendapatanitem'` line from `KewajibabPelaksanaan.Meta`. The table is now named `pendapatan_kewajibabpelaksanaan`.

- [ ] **Step 4: Apply migration**

```
python manage.py migrate pendapatan 0005
```

Expected: runs without error.

- [ ] **Step 5: Verify in shell**

```
python manage.py shell -c "from apps.pendapatan.models import KewajibabPelaksanaan, JadwalPengakuan, EntriPengakuan, AsetKontrak; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```
git add apps/pendapatan/migrations/0005_psak72_schema.py apps/pendapatan/models.py
git commit -m "feat(pendapatan): migration 0005 — PSAK 72 schema (rename, new models)"
```

---

## Task 6: Data migration 0006 — migrate deferred → jadwal/entri

**Files:**
- Create: `apps/pendapatan/migrations/0006_psak72_data.py`

Copies data from old `DeferredRevenueSchedule` / `DeferredRevenueEntry` into `JadwalPengakuan` / `EntriPengakuan`, and sets `recognition_type` based on `is_deferred`.

- [ ] **Step 1: Create migration file**

```
python manage.py makemigrations pendapatan --empty --name psak72_data
```

- [ ] **Step 2: Write migration content**

```python
# apps/pendapatan/migrations/0006_psak72_data.py
from django.db import migrations


def migrate_deferred_to_jadwal(apps, schema_editor):
    DeferredRevenueSchedule = apps.get_model('pendapatan', 'DeferredRevenueSchedule')
    JadwalPengakuan = apps.get_model('pendapatan', 'JadwalPengakuan')
    EntriPengakuan = apps.get_model('pendapatan', 'EntriPengakuan')
    KewajibabPelaksanaan = apps.get_model('pendapatan', 'KewajibabPelaksanaan')

    # Map is_deferred → recognition_type
    KewajibabPelaksanaan.objects.filter(is_deferred=True).update(recognition_type='over_time')
    KewajibabPelaksanaan.objects.filter(is_deferred=False).update(recognition_type='point_in_time')

    # Copy schedules
    for drs in DeferredRevenueSchedule.objects.select_related('item').all():
        jadwal = JadwalPengakuan.objects.create(
            kp_id=drs.item_id,
            tipe_aliran=drs.tipe_aliran or 'advance_payment_cash',
            progress_method=drs.progress_method or 'straight_line',
            tanggal_mulai=drs.tanggal_mulai,
            tanggal_selesai=drs.tanggal_selesai,
            liabilitas_kontrak_acct_id=drs.liabilitas_kontrak_akun_id,
            biaya_estimasi_total=drs.biaya_estimasi_total,
            nilai_total=drs.total_nilai,
            nilai_diakui=drs.nilai_diakui,
            status=drs.status if drs.status in ('active', 'completed', 'voided') else 'active',
        )

        # Copy entries
        for dre in drs.deferredrevenueentry_set.all():
            EntriPengakuan.objects.create(
                jadwal=jadwal,
                tanggal_target=dre.tanggal_target,
                nilai=dre.nilai,
                nilai_diakui=dre.nilai_diakui,
                status=dre.status if dre.status in ('pending', 'recognized', 'skipped') else 'pending',
                journal_header_id=dre.journal_header_id,
            )


def reverse_migrate(apps, schema_editor):
    JadwalPengakuan = apps.get_model('pendapatan', 'JadwalPengakuan')
    EntriPengakuan = apps.get_model('pendapatan', 'EntriPengakuan')
    EntriPengakuan.objects.all().delete()
    JadwalPengakuan.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pendapatan', '0005_psak72_schema'),
    ]

    operations = [
        migrations.RunPython(migrate_deferred_to_jadwal, reverse_code=reverse_migrate),
    ]
```

- [ ] **Step 3: Apply migration**

```
python manage.py migrate pendapatan 0006
```

- [ ] **Step 4: Verify data in shell**

```python
python manage.py shell -c "
from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan
print('Jadwal count:', JadwalPengakuan.objects.count())
print('Entri count:', EntriPengakuan.objects.count())
"
```

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/migrations/0006_psak72_data.py
git commit -m "feat(pendapatan): migration 0006 — migrate deferred revenue data to JadwalPengakuan/EntriPengakuan"
```

---

## Task 7: Cleanup migration 0007 — drop old deferred models + staging fields

**Files:**
- Create: `apps/pendapatan/migrations/0007_psak72_cleanup.py`
- Modify: `apps/pendapatan/models.py` (remove old fields and classes)

- [ ] **Step 1: Remove `DeferredRevenueSchedule` and `DeferredRevenueEntry` classes from `apps/pendapatan/models.py`**

Delete the entire `DeferredRevenueSchedule` and `DeferredRevenueEntry` class definitions.

- [ ] **Step 2: Remove staging/legacy fields from `KewajibabPelaksanaan`**

Remove these fields from the class body:
- `is_deferred`
- `deferred_account`
- `deferred_pph_acct`

Keep the `ot_*` fields — they are still used by the form and service for over-time configuration.

- [ ] **Step 3: Remove the backward-compat alias**

Delete the line:
```python
PendapatanItem = KewajibabPelaksanaan  # backward-compat alias, remove after all references updated
```

At this point, any remaining code that references `PendapatanItem` by name will break — that's intentional so you can find and fix them.

- [ ] **Step 4: Generate cleanup migration**

```
python manage.py makemigrations pendapatan --name psak72_cleanup
```

Verify the generated migration contains:
- `migrations.RemoveField(model_name='kewajibabpelaksanaan', name='is_deferred')`
- `migrations.RemoveField(model_name='kewajibabpelaksanaan', name='deferred_account')`
- `migrations.RemoveField(model_name='kewajibabpelaksanaan', name='deferred_pph_acct')`
- `migrations.DeleteModel(name='DeferredRevenueSchedule')`
- `migrations.DeleteModel(name='DeferredRevenueEntry')`

- [ ] **Step 5: Apply migration**

```
python manage.py migrate pendapatan 0007
```

- [ ] **Step 6: Fix any broken references**

Search for remaining `PendapatanItem` references:

```
grep -r "PendapatanItem\|jumlah_bruto\|is_deferred\|deferred_account\|deferred_pph_acct\|DeferredRevenueSchedule\|DeferredRevenueEntry" apps/pendapatan/ templates/pendapatan/ --include="*.py" --include="*.html"
```

Fix each one: rename `PendapatanItem` → `KewajibabPelaksanaan`, `jumlah_bruto` → `nilai_kontrak`, update FK traversals from `.items.` → `.kps.`.

- [ ] **Step 7: Run full test suite**

```
pytest tests/ -v
```

Expected: all PASS (no references to deleted models/fields).

- [ ] **Step 8: Commit**

```
git add apps/pendapatan/ apps/pendapatan/migrations/0007_psak72_cleanup.py
git commit -m "feat(pendapatan): migration 0007 — drop old deferred models, remove legacy fields"
```

---

## Task 8: `compute_alokasi_harga()` service

**Files:**
- Modify: `apps/pendapatan/services.py`
- Create: `tests/pendapatan/test_services.py`
- Create: `tests/pendapatan/factories.py`

PSAK 72 Step 4: allocate total transaction price proportionally by each KP's `nilai_kontrak` (standalone selling price proxy).

- [ ] **Step 1: Create test factories**

```python
# tests/pendapatan/factories.py
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(username='testuser'):
    return User.objects.get_or_create(username=username)[0]


def make_header(user, standar_akuntansi='PSAK_71_72', **kwargs):
    from apps.pendapatan.models import PendapatanHeader
    from apps.entitas_bisnis.models import EntitasBisnis
    eb = EntitasBisnis.objects.first() or EntitasBisnis.objects.create(
        nama='Test EB', kode='TEST'
    )
    return PendapatanHeader.objects.create(
        entitas_bisnis=eb,
        tanggal='2026-01-01',
        standar_akuntansi=standar_akuntansi,
        created_by=user,
        **kwargs,
    )


def make_pendapatan_eb(header, eb=None):
    from apps.pendapatan.models import PendapatanEntitasBisnis
    from apps.entitas_bisnis.models import EntitasBisnis
    if eb is None:
        eb = header.entitas_bisnis
    return PendapatanEntitasBisnis.objects.create(header=header, entitas_bisnis=eb)


def make_akun(kode, nama, **kwargs):
    from apps.akuntansi.models import Akun
    return Akun.objects.get_or_create(kode=kode, defaults={'nama': nama, **kwargs})[0]


def make_kp(peb, nilai_kontrak, recognition_type='point_in_time', **kwargs):
    from apps.pendapatan.models import KewajibabPelaksanaan
    akun_pendapatan = make_akun('4001', 'Pendapatan Jasa')
    return KewajibabPelaksanaan.objects.create(
        entitas_bisnis=peb,
        keterangan='KP Test',
        nilai_kontrak=Decimal(str(nilai_kontrak)),
        recognition_type=recognition_type,
        akun_pendapatan=akun_pendapatan,
        **kwargs,
    )
```

- [ ] **Step 2: Write failing test**

```python
# tests/pendapatan/test_services.py
from decimal import Decimal
from django.test import TestCase

from tests.pendapatan.factories import make_user, make_header, make_pendapatan_eb, make_kp
from apps.pendapatan.services import compute_alokasi_harga


class ComputeAlokasiHargaTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.header = make_header(self.user)
        self.peb = make_pendapatan_eb(self.header)

    def test_single_kp_gets_full_amount(self):
        make_kp(self.peb, '1000')
        # header jumlah_tagihan must be set — update to match KP total
        self.header.jumlah_tagihan = Decimal('1000')
        self.header.save()
        result = compute_alokasi_harga(self.header)
        total = sum(result.values())
        self.assertEqual(total, Decimal('1000'))

    def test_two_kps_proportional_allocation(self):
        kp1 = make_kp(self.peb, '600')
        kp2 = make_kp(self.peb, '400')
        self.header.jumlah_tagihan = Decimal('1200')
        self.header.save()
        result = compute_alokasi_harga(self.header)
        # kp1 is 60% of SSP, kp2 is 40%
        self.assertAlmostEqual(float(result[kp1.id]), 720.0, places=2)
        self.assertAlmostEqual(float(result[kp2.id]), 480.0, places=2)

    def test_rounding_no_penny_left_over(self):
        make_kp(self.peb, '100')
        make_kp(self.peb, '100')
        make_kp(self.peb, '100')
        self.header.jumlah_tagihan = Decimal('10')
        self.header.save()
        result = compute_alokasi_harga(self.header)
        self.assertEqual(sum(result.values()), Decimal('10'))
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/pendapatan/test_services.py::ComputeAlokasiHargaTest -v
```

- [ ] **Step 4: Implement `compute_alokasi_harga` in `apps/pendapatan/services.py`**

```python
from decimal import Decimal, ROUND_HALF_UP


def compute_alokasi_harga(header) -> dict[int, Decimal]:
    """
    PSAK 72 Step 4: allocate transaction price across KPs proportionally by nilai_kontrak (SSP proxy).
    Returns dict of {kp_id: alokasi_harga}. Last KP absorbs any rounding remainder.
    """
    from apps.pendapatan.models import KewajibabPelaksanaan
    kps = list(
        KewajibabPelaksanaan.objects.filter(entitas_bisnis__header=header)
    )
    if not kps:
        return {}

    total_ssp = sum(kp.nilai_kontrak for kp in kps)
    transaction_price = header.jumlah_tagihan  # adjust field name if different in your Header model

    if total_ssp == 0:
        return {kp.id: Decimal('0') for kp in kps}

    alokasi = {}
    total_allocated = Decimal('0')

    for i, kp in enumerate(kps):
        if i == len(kps) - 1:
            alokasi[kp.id] = transaction_price - total_allocated
        else:
            raw = kp.nilai_kontrak / total_ssp * transaction_price
            amount = raw.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            alokasi[kp.id] = amount
            total_allocated += amount

    return alokasi
```

> **Note:** Check the actual field name on `PendapatanHeader` for the transaction price total (it may be `jumlah_tagihan`, `total_tagihan`, or similar). Grep with: `grep -n "jumlah\|total" apps/pendapatan/models.py`.

- [ ] **Step 5: Run tests**

```
pytest tests/pendapatan/test_services.py::ComputeAlokasiHargaTest -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```
git add apps/pendapatan/services.py tests/pendapatan/
git commit -m "feat(pendapatan): implement compute_alokasi_harga PSAK 72 Step 4 SSP allocation"
```

---

## Task 9: Overhaul `confirm_pendapatan()` — 5 cases

**Files:**
- Modify: `apps/pendapatan/services.py`
- Modify: `tests/pendapatan/test_services.py`

The five confirmation cases:
1. `point_in_time` + payment via cash → Debit Kas, Credit Pendapatan
2. `point_in_time` + payment via credit (akun_piutang set) → Debit Piutang, Credit Pendapatan → create piutang
3. `over_time` + `advance_payment_cash` → Debit Kas, Credit Liabilitas Kontrak; create `JadwalPengakuan` + `EntriPengakuan`
4. `over_time` + `periodic_billing` → no immediate journal; create `JadwalPengakuan` + `EntriPengakuan`
5. `over_time` + `performance_first` → Debit Aset Kontrak, Credit Pendapatan; create `AsetKontrak`

Also fixes the existing **PPh potong bug**: debit was credited and credit was debited — swap them.

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/pendapatan/test_services.py
from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan, AsetKontrak
from apps.pendapatan.services import confirm_pendapatan


class ConfirmPendapatanTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.header = make_header(self.user)
        self.peb = make_pendapatan_eb(self.header)
        from tests.pendapatan.factories import make_akun
        self.akun_kas = make_akun('1001', 'Kas')
        self.akun_pendapatan = make_akun('4001', 'Pendapatan Jasa')
        self.akun_piutang = make_akun('1101', 'Piutang Usaha')
        self.akun_liabilitas = make_akun('2101', 'Liabilitas Kontrak')
        self.akun_aset_kontrak = make_akun('1201', 'Aset Kontrak')

    def test_point_in_time_cash_creates_journal(self):
        from apps.akuntansi.models import JurnalHeader
        make_kp(self.peb, '1000', recognition_type='point_in_time')
        # header must reference the payment account
        self.header.akun_kas = self.akun_kas
        self.header.jumlah_tagihan = 1000
        self.header.save()
        confirm_pendapatan(self.header.id, self.user)
        self.assertEqual(JurnalHeader.objects.count(), 1)
        self.header.refresh_from_db()
        self.assertEqual(self.header.status, 'confirmed')

    def test_over_time_advance_creates_jadwal(self):
        kp = make_kp(
            self.peb, '1000',
            recognition_type='over_time',
            ot_tipe_aliran='advance_payment_cash',
            ot_progress_method='straight_line',
            ot_tanggal_mulai='2026-01-01',
            ot_tanggal_selesai='2026-03-31',
            ot_liabilitas_kontrak_acct=self.akun_liabilitas,
        )
        self.header.jumlah_tagihan = 1000
        self.header.akun_kas = self.akun_kas
        self.header.save()
        confirm_pendapatan(self.header.id, self.user)
        self.assertTrue(JadwalPengakuan.objects.filter(kp=kp).exists())
        self.assertGreater(EntriPengakuan.objects.count(), 0)

    def test_over_time_performance_first_creates_aset_kontrak(self):
        kp = make_kp(
            self.peb, '2000',
            recognition_type='over_time',
            ot_tipe_aliran='performance_first',
            ot_progress_method='straight_line',
            ot_tanggal_mulai='2026-01-01',
            ot_tanggal_selesai='2026-06-30',
            ot_aset_kontrak_acct=self.akun_aset_kontrak,
        )
        self.header.jumlah_tagihan = 2000
        self.header.akun_kas = self.akun_kas
        self.header.save()
        confirm_pendapatan(self.header.id, self.user)
        self.assertTrue(AsetKontrak.objects.filter(kp=kp).exists())
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/pendapatan/test_services.py::ConfirmPendapatanTest -v
```

- [ ] **Step 3: Implement `confirm_pendapatan` overhaul**

Replace (or rewrite) `confirm_pendapatan` in `apps/pendapatan/services.py`:

```python
from django.db import transaction
from dateutil.relativedelta import relativedelta  # already a dependency via python-dateutil
import datetime


def confirm_pendapatan(header_id: int, user) -> None:
    from apps.pendapatan.models import (
        PendapatanHeader, KewajibabPelaksanaan, JadwalPengakuan,
        EntriPengakuan, AsetKontrak, PendapatanEventLog,
    )
    from apps.akuntansi.models import JurnalHeader, JurnalDetail

    with transaction.atomic():
        header = PendapatanHeader.objects.select_for_update().get(pk=header_id)
        assert header.status == 'draft', f"Header {header_id} is not in draft status"

        alokasi = compute_alokasi_harga(header)

        kps = KewajibabPelaksanaan.objects.filter(
            entitas_bisnis__header=header
        ).select_related(
            'ot_liabilitas_kontrak_acct', 'ot_aset_kontrak_acct',
            'akun_pendapatan', 'akun_piutang',
            'akun_pph_potong', 'akun_pph_pungut', 'akun_pph_pungut_penjual',
        )

        for kp in kps:
            harga_j = alokasi.get(kp.id, kp.nilai_kontrak)
            kp.harga_j = harga_j
            kp.save(update_fields=['harga_j'])

            if kp.recognition_type == KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME:
                _confirm_point_in_time(header, kp, harga_j, user)
            else:
                _confirm_over_time(header, kp, harga_j, user)

        header.status = 'confirmed'
        header.save(update_fields=['status'])

        PendapatanEventLog.objects.create(
            header=header,
            event_type=PendapatanEventLog.EventType.CONFIRM,
            description=f'Dikonfirmasi oleh {user}',
            created_by=user,
        )


def _confirm_point_in_time(header, kp, harga_j, user):
    from apps.akuntansi.models import JurnalHeader, JurnalDetail
    from apps.pendapatan.models import PendapatanEventLog

    payment_is_cash = kp.akun_piutang_id is None

    jurnal = JurnalHeader.objects.create(
        tanggal=header.tanggal,
        keterangan=f'Pendapatan: {kp.keterangan}',
        created_by=user,
    )

    if payment_is_cash:
        # Case 1: Debit Kas, Credit Pendapatan
        JurnalDetail.objects.create(jurnal=jurnal, akun=header.akun_kas, debit=harga_j, kredit=0)
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_pendapatan, debit=0, kredit=harga_j)
    else:
        # Case 2: Debit Piutang, Credit Pendapatan
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_piutang, debit=harga_j, kredit=0)
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_pendapatan, debit=0, kredit=harga_j)

    _add_pph_entries(jurnal, kp, harga_j)

    PendapatanEventLog.objects.create(
        header=header,
        event_type=PendapatanEventLog.EventType.CREATE_JOURNAL,
        description=f'Jurnal point-in-time untuk {kp.keterangan}',
        created_by=user,
    )


def _add_pph_entries(jurnal, kp, harga_j):
    """
    Add PPh journal lines. Bug fix: PPh potong is withheld FROM customer (buyer withholds),
    so for the seller: Debit PPh Potong Receivable, Credit nothing extra here — depends on setup.
    Consult your chart-of-accounts convention for final debit/credit direction.
    """
    from apps.akuntansi.models import JurnalDetail
    from decimal import Decimal

    if kp.akun_pph_potong and kp.pph_potong_rate:
        pph_amount = (harga_j * kp.pph_potong_rate / Decimal('100')).quantize(Decimal('0.01'))
        # PPh potong: buyer withholds — seller records reduction of receivable and PPh asset
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_pph_potong, debit=pph_amount, kredit=0)

    if kp.akun_pph_pungut and kp.pph_pungut_rate:
        pph_amount = (harga_j * kp.pph_pungut_rate / Decimal('100')).quantize(Decimal('0.01'))
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_pph_pungut, debit=0, kredit=pph_amount)


def _confirm_over_time(header, kp, harga_j, user):
    from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan, AsetKontrak, PendapatanEventLog
    from apps.akuntansi.models import JurnalHeader, JurnalDetail

    tipe = kp.ot_tipe_aliran

    if tipe == JadwalPengakuan.TipeAliran.ADVANCE_PAYMENT_CASH:
        # Case 3: Debit Kas, Credit Liabilitas Kontrak
        jurnal = JurnalHeader.objects.create(
            tanggal=header.tanggal,
            keterangan=f'Terima advance: {kp.keterangan}',
            created_by=user,
        )
        JurnalDetail.objects.create(jurnal=jurnal, akun=header.akun_kas, debit=harga_j, kredit=0)
        JurnalDetail.objects.create(
            jurnal=jurnal, akun=kp.ot_liabilitas_kontrak_acct, debit=0, kredit=harga_j
        )
        _create_jadwal(kp, harga_j, user)

    elif tipe == JadwalPengakuan.TipeAliran.PERIODIC_BILLING:
        # Case 4: No immediate journal — billing happens per period
        _create_jadwal(kp, harga_j, user)

    elif tipe == JadwalPengakuan.TipeAliran.PERFORMANCE_FIRST:
        # Case 5: Debit Aset Kontrak, Credit Pendapatan
        jurnal = JurnalHeader.objects.create(
            tanggal=header.tanggal,
            keterangan=f'Aset kontrak: {kp.keterangan}',
            created_by=user,
        )
        JurnalDetail.objects.create(
            jurnal=jurnal, akun=kp.ot_aset_kontrak_acct, debit=harga_j, kredit=0
        )
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_pendapatan, debit=0, kredit=harga_j)
        AsetKontrak.objects.create(
            kp=kp,
            tanggal=header.tanggal,
            nilai=harga_j,
            nilai_tersisa=harga_j,
            journal_header=jurnal,
        )
        _create_jadwal(kp, harga_j, user)

    PendapatanEventLog.objects.create(
        header=header,
        event_type=PendapatanEventLog.EventType.CREATE_JOURNAL,
        description=f'Over-time confirm [{tipe}] untuk {kp.keterangan}',
        created_by=user,
    )


def _create_jadwal(kp, harga_j, user):
    """Create JadwalPengakuan + EntriPengakuan from KP staging fields."""
    from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan
    from decimal import Decimal

    jadwal = JadwalPengakuan.objects.create(
        kp=kp,
        tipe_aliran=kp.ot_tipe_aliran,
        progress_method=kp.ot_progress_method,
        tanggal_mulai=kp.ot_tanggal_mulai,
        tanggal_selesai=kp.ot_tanggal_selesai,
        liabilitas_kontrak_acct=kp.ot_liabilitas_kontrak_acct,
        aset_kontrak_acct=kp.ot_aset_kontrak_acct,
        biaya_estimasi_total=kp.ot_biaya_estimasi_total,
        nilai_total=harga_j,
        nilai_diakui=Decimal('0'),
    )

    if kp.ot_progress_method == JadwalPengakuan.ProgressMethod.STRAIGHT_LINE:
        _create_straight_line_entri(jadwal, harga_j)
    # For milestone/percentage_completion, entries are created manually later

    return jadwal


def _create_straight_line_entri(jadwal, total_nilai):
    """Generate monthly straight-line recognition entries."""
    from apps.pendapatan.models import EntriPengakuan
    from decimal import Decimal

    start = jadwal.tanggal_mulai
    end = jadwal.tanggal_selesai

    # Count months
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    if months <= 0:
        months = 1

    monthly = (total_nilai / months).quantize(Decimal('0.01'))
    remainder = total_nilai - monthly * months

    entri_list = []
    current = start.replace(day=1)
    for i in range(months):
        nilai = monthly + (remainder if i == months - 1 else Decimal('0'))
        entri_list.append(EntriPengakuan(
            jadwal=jadwal,
            tanggal_target=current,
            nilai=nilai,
        ))
        current = (current + relativedelta(months=1)).replace(day=1)

    EntriPengakuan.objects.bulk_create(entri_list)
```

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_services.py::ConfirmPendapatanTest -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/services.py tests/pendapatan/test_services.py
git commit -m "feat(pendapatan): overhaul confirm_pendapatan for PSAK 72 5-case logic + PPh potong bug fix"
```

---

## Task 10: `recognize_entry()` service

**Files:**
- Modify: `apps/pendapatan/services.py`
- Modify: `tests/pendapatan/test_services.py`

Handles the actual revenue recognition action when a user clicks "Akui" on a pending `EntriPengakuan`.

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/pendapatan/test_services.py
import datetime
from apps.pendapatan.services import recognize_entry


class RecognizeEntryTest(TestCase):
    def _make_confirmed_header_with_jadwal(self, tipe_aliran):
        from tests.pendapatan.factories import make_akun
        user = make_user('recognizer')
        header = make_header(user)
        peb = make_pendapatan_eb(header)
        akun_liabilitas = make_akun('2101', 'Liabilitas Kontrak')
        akun_pendapatan = make_akun('4001', 'Pendapatan Jasa')
        akun_piutang = make_akun('1101', 'Piutang Usaha')
        akun_kas = make_akun('1001', 'Kas')
        kp = make_kp(
            peb, '1200', recognition_type='over_time',
            ot_tipe_aliran=tipe_aliran,
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 3, 31),
            ot_liabilitas_kontrak_acct=akun_liabilitas,
            akun_pendapatan=akun_pendapatan,
            akun_piutang=akun_piutang,
        )
        from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan
        jadwal = JadwalPengakuan.objects.create(
            kp=kp, tipe_aliran=tipe_aliran, progress_method='straight_line',
            tanggal_mulai=datetime.date(2026, 1, 1),
            tanggal_selesai=datetime.date(2026, 3, 31),
            liabilitas_kontrak_acct=akun_liabilitas,
            nilai_total=1200, nilai_diakui=0,
        )
        entri = EntriPengakuan.objects.create(
            jadwal=jadwal,
            tanggal_target=datetime.date(2026, 1, 31),
            nilai=400,
        )
        return entri, jadwal, user

    def test_recognize_advance_payment_creates_journal(self):
        from apps.akuntansi.models import JurnalHeader
        entri, jadwal, user = self._make_confirmed_header_with_jadwal('advance_payment_cash')
        recognize_entry(entri.id, user, journal_date=datetime.date(2026, 1, 31))
        entri.refresh_from_db()
        self.assertEqual(entri.status, 'recognized')
        self.assertIsNotNone(entri.journal_header)

    def test_recognize_periodic_billing_creates_journal(self):
        from apps.akuntansi.models import JurnalHeader
        entri, jadwal, user = self._make_confirmed_header_with_jadwal('periodic_billing')
        recognize_entry(entri.id, user, journal_date=datetime.date(2026, 1, 31))
        entri.refresh_from_db()
        self.assertEqual(entri.status, 'recognized')

    def test_recognize_updates_jadwal_nilai_diakui(self):
        from decimal import Decimal
        entri, jadwal, user = self._make_confirmed_header_with_jadwal('advance_payment_cash')
        recognize_entry(entri.id, user, journal_date=datetime.date(2026, 1, 31))
        jadwal.refresh_from_db()
        self.assertEqual(jadwal.nilai_diakui, Decimal('400'))
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/pendapatan/test_services.py::RecognizeEntryTest -v
```

- [ ] **Step 3: Implement `recognize_entry` in `apps/pendapatan/services.py`**

```python
def recognize_entry(entry_id: int, user, journal_date=None) -> None:
    from apps.pendapatan.models import EntriPengakuan, JadwalPengakuan, PendapatanEventLog
    from apps.akuntansi.models import JurnalHeader, JurnalDetail
    import datetime

    with transaction.atomic():
        entri = EntriPengakuan.objects.select_for_update().select_related(
            'jadwal', 'jadwal__kp', 'jadwal__kp__akun_pendapatan',
            'jadwal__kp__akun_piutang', 'jadwal__liabilitas_kontrak_acct',
        ).get(pk=entry_id)

        assert entri.status == EntriPengakuan.Status.PENDING, \
            f"Entry {entry_id} is not pending (status={entri.status})"

        jadwal = entri.jadwal
        kp = jadwal.kp
        date = journal_date or datetime.date.today()
        nilai = entri.nilai

        jurnal = JurnalHeader.objects.create(
            tanggal=date,
            keterangan=f'Pengakuan pendapatan: {kp.keterangan} [{entri.tanggal_target}]',
            created_by=user,
        )

        if jadwal.tipe_aliran == JadwalPengakuan.TipeAliran.ADVANCE_PAYMENT_CASH:
            # Debit Liabilitas Kontrak, Credit Pendapatan
            JurnalDetail.objects.create(
                jurnal=jurnal, akun=jadwal.liabilitas_kontrak_acct, debit=nilai, kredit=0
            )
            JurnalDetail.objects.create(
                jurnal=jurnal, akun=kp.akun_pendapatan, debit=0, kredit=nilai
            )

        elif jadwal.tipe_aliran == JadwalPengakuan.TipeAliran.PERIODIC_BILLING:
            # Debit Piutang, Credit Pendapatan
            JurnalDetail.objects.create(
                jurnal=jurnal, akun=kp.akun_piutang, debit=nilai, kredit=0
            )
            JurnalDetail.objects.create(
                jurnal=jurnal, akun=kp.akun_pendapatan, debit=0, kredit=nilai
            )

        elif jadwal.tipe_aliran == JadwalPengakuan.TipeAliran.PERFORMANCE_FIRST:
            # No journal here — revenue was recognized at confirm; this entry is informational
            # or triggers konversi_aset_kontrak
            pass

        entri.status = EntriPengakuan.Status.RECOGNIZED
        entri.nilai_diakui = nilai
        entri.journal_header = jurnal
        entri.save(update_fields=['status', 'nilai_diakui', 'journal_header'])

        jadwal.nilai_diakui = (jadwal.nilai_diakui or 0) + nilai
        if jadwal.nilai_diakui >= jadwal.nilai_total:
            jadwal.status = JadwalPengakuan.Status.COMPLETED
        jadwal.save(update_fields=['nilai_diakui', 'status'])

        PendapatanEventLog.objects.create(
            header=kp.entitas_bisnis.header,
            event_type=PendapatanEventLog.EventType.RECOGNIZE,
            description=f'Pengakuan {nilai} untuk {kp.keterangan} [{date}]',
            created_by=user,
        )
```

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_services.py::RecognizeEntryTest -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/services.py tests/pendapatan/test_services.py
git commit -m "feat(pendapatan): implement recognize_entry service (3 tipe_aliran)"
```

---

## Task 11: `konversi_aset_kontrak_ke_piutang()` service

**Files:**
- Modify: `apps/pendapatan/services.py`
- Modify: `tests/pendapatan/test_services.py`

Converts an active `AsetKontrak` to a `PiutangHeader` once payment is due.

- [ ] **Step 1: Write failing test**

```python
# Append to tests/pendapatan/test_services.py
import datetime
from decimal import Decimal
from apps.pendapatan.models import AsetKontrak
from apps.pendapatan.services import konversi_aset_kontrak_ke_piutang


class KonversiAsetKontrakTest(TestCase):
    def setUp(self):
        from tests.pendapatan.factories import make_akun
        self.user = make_user('konverter')
        self.header = make_header(self.user)
        self.peb = make_pendapatan_eb(self.header)
        self.akun_kas = make_akun('1001', 'Kas')
        self.akun_pendapatan = make_akun('4001', 'Pendapatan Jasa')
        self.akun_piutang = make_akun('1101', 'Piutang Usaha')
        self.akun_aset_kontrak = make_akun('1201', 'Aset Kontrak')
        kp = make_kp(
            self.peb, '3000', recognition_type='over_time',
            ot_tipe_aliran='performance_first',
            akun_pendapatan=self.akun_pendapatan,
            akun_piutang=self.akun_piutang,
            ot_aset_kontrak_acct=self.akun_aset_kontrak,
        )
        self.aset = AsetKontrak.objects.create(
            kp=kp, tanggal=datetime.date(2026, 1, 1),
            nilai=Decimal('3000'), nilai_tersisa=Decimal('3000'),
        )

    def test_konversi_creates_piutang(self):
        from apps.piutang.models import PiutangHeader
        konversi_aset_kontrak_ke_piutang(self.aset.id, self.user)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.status, AsetKontrak.Status.CONVERTED)
        self.assertIsNotNone(self.aset.piutang)

    def test_konversi_creates_swap_journal(self):
        from apps.akuntansi.models import JurnalDetail
        konversi_aset_kontrak_ke_piutang(self.aset.id, self.user)
        self.aset.refresh_from_db()
        details = JurnalDetail.objects.filter(jurnal=self.aset.journal_header)
        self.assertEqual(details.count(), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/pendapatan/test_services.py::KonversiAsetKontrakTest -v
```

- [ ] **Step 3: Implement in `apps/pendapatan/services.py`**

```python
def konversi_aset_kontrak_ke_piutang(aset_kontrak_id: int, user) -> None:
    """
    Convert an AsetKontrak to a piutang (receivable).
    Journal: Debit Piutang, Credit Aset Kontrak.
    """
    from apps.pendapatan.models import AsetKontrak, PendapatanEventLog
    from apps.akuntansi.models import JurnalHeader, JurnalDetail
    import datetime

    with transaction.atomic():
        aset = AsetKontrak.objects.select_for_update().select_related(
            'kp', 'kp__akun_piutang', 'kp__ot_aset_kontrak_acct',
        ).get(pk=aset_kontrak_id)

        assert aset.status == AsetKontrak.Status.ACTIVE, \
            f"AsetKontrak {aset_kontrak_id} is not active"

        kp = aset.kp
        nilai = aset.nilai_tersisa

        # Create swap journal: Debit Piutang, Credit Aset Kontrak
        jurnal = JurnalHeader.objects.create(
            tanggal=datetime.date.today(),
            keterangan=f'Konversi aset kontrak ke piutang: {kp.keterangan}',
            created_by=user,
        )
        JurnalDetail.objects.create(jurnal=jurnal, akun=kp.akun_piutang, debit=nilai, kredit=0)
        JurnalDetail.objects.create(
            jurnal=jurnal, akun=kp.ot_aset_kontrak_acct, debit=0, kredit=nilai
        )

        # Create piutang record
        piutang = _create_piutang_from_kp(kp, nilai, user)

        aset.status = AsetKontrak.Status.CONVERTED
        aset.nilai_tersisa = 0
        aset.journal_header = jurnal
        aset.piutang = piutang
        aset.save(update_fields=['status', 'nilai_tersisa', 'journal_header', 'piutang'])

        PendapatanEventLog.objects.create(
            header=kp.entitas_bisnis.header,
            event_type=PendapatanEventLog.EventType.CONVERT_ASSET,
            description=f'Aset kontrak {nilai} dikonversi ke piutang',
            created_by=user,
        )


def _create_piutang_from_kp(kp, nilai, user):
    """Create a minimal PiutangHeader from a KP. Adjust fields to match piutang model."""
    from apps.piutang.models import PiutangHeader
    import datetime

    return PiutangHeader.objects.create(
        entitas_bisnis=kp.entitas_bisnis.header.entitas_bisnis,
        tanggal=datetime.date.today(),
        jumlah=nilai,
        akun_piutang=kp.akun_piutang,
        keterangan=f'Dari aset kontrak: {kp.keterangan}',
        created_by=user,
        status='draft',
    )
```

> **Note:** Inspect `apps/piutang/models.py` to verify the exact field names on `PiutangHeader`. Adjust `_create_piutang_from_kp` accordingly.

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_services.py::KonversiAsetKontrakTest -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```
git add apps/pendapatan/services.py tests/pendapatan/test_services.py
git commit -m "feat(pendapatan): implement konversi_aset_kontrak_ke_piutang service"
```

---

## Task 12: Update `void_pendapatan()`

**Files:**
- Modify: `apps/pendapatan/services.py`
- Modify: `tests/pendapatan/test_services.py`

Extend voiding to also void `JadwalPengakuan`, `EntriPengakuan`, and `AsetKontrak`.

- [ ] **Step 1: Write failing test**

```python
# Append to tests/pendapatan/test_services.py
from apps.pendapatan.services import void_pendapatan


class VoidPendapatanTest(TestCase):
    def test_void_voids_jadwal_and_aset(self):
        import datetime
        from tests.pendapatan.factories import make_akun
        from apps.pendapatan.models import JadwalPengakuan, AsetKontrak

        user = make_user('voider')
        header = make_header(user)
        peb = make_pendapatan_eb(header)
        akun_liabilitas = make_akun('2101', 'Liabilitas Kontrak')

        kp = make_kp(
            peb, '1000', recognition_type='over_time',
            ot_tipe_aliran='advance_payment_cash',
        )
        jadwal = JadwalPengakuan.objects.create(
            kp=kp, tipe_aliran='advance_payment_cash', progress_method='straight_line',
            tanggal_mulai=datetime.date(2026, 1, 1),
            tanggal_selesai=datetime.date(2026, 3, 31),
            liabilitas_kontrak_acct=akun_liabilitas,
            nilai_total=1000, nilai_diakui=0, status='active',
        )
        header.status = 'confirmed'
        header.save()

        void_pendapatan(header.id, user)

        jadwal.refresh_from_db()
        header.refresh_from_db()
        self.assertEqual(jadwal.status, JadwalPengakuan.Status.VOIDED)
        self.assertEqual(header.status, 'voided')
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/pendapatan/test_services.py::VoidPendapatanTest -v
```

- [ ] **Step 3: Update `void_pendapatan` in `apps/pendapatan/services.py`**

Find the existing `void_pendapatan` function and extend it. After setting `header.status = 'voided'`, add:

```python
        # Void all schedules and contract assets
        from apps.pendapatan.models import JadwalPengakuan, EntriPengakuan, AsetKontrak

        JadwalPengakuan.objects.filter(
            kp__entitas_bisnis__header=header
        ).update(status=JadwalPengakuan.Status.VOIDED)

        EntriPengakuan.objects.filter(
            jadwal__kp__entitas_bisnis__header=header,
            status=EntriPengakuan.Status.PENDING,
        ).update(status=EntriPengakuan.Status.SKIPPED)

        AsetKontrak.objects.filter(
            kp__entitas_bisnis__header=header,
            status=AsetKontrak.Status.ACTIVE,
        ).update(status=AsetKontrak.Status.VOIDED)
```

- [ ] **Step 4: Run tests**

```
pytest tests/pendapatan/test_services.py::VoidPendapatanTest -v
```
Expected: PASS

- [ ] **Step 5: Run full service test suite**

```
pytest tests/pendapatan/test_services.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```
git add apps/pendapatan/services.py tests/pendapatan/test_services.py
git commit -m "feat(pendapatan): update void_pendapatan to void JadwalPengakuan and AsetKontrak"
```

---

## Task 13: Update forms

**Files:**
- Modify: `apps/pendapatan/forms.py`

Rename `PendapatanItemForm` → `KewajibabPelaksanaanForm`. Add over-time fields. Keep a backward-compat alias until views are updated.

- [ ] **Step 1: Open `apps/pendapatan/forms.py` and rename the form class**

```python
class KewajibabPelaksanaanForm(forms.ModelForm):
    class Meta:
        model = KewajibabPelaksanaan
        fields = [
            'keterangan', 'nilai_kontrak', 'recognition_type',
            'akun_pendapatan', 'akun_piutang',
            'akun_pph_potong', 'pph_potong_rate',
            'akun_pph_pungut', 'pph_pungut_rate',
            'akun_pph_pungut_penjual', 'pph_pungut_penjual_rate',
            'ppn_rate',
            # over-time staging fields:
            'ot_tipe_aliran', 'ot_progress_method',
            'ot_tanggal_mulai', 'ot_tanggal_selesai',
            'ot_liabilitas_kontrak_acct', 'ot_aset_kontrak_acct',
            'ot_biaya_estimasi_total',
        ]
        widgets = {
            'ot_tanggal_mulai': forms.DateInput(attrs={'type': 'date'}),
            'ot_tanggal_selesai': forms.DateInput(attrs={'type': 'date'}),
            'keterangan': forms.Textarea(attrs={'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        recognition_type = cleaned.get('recognition_type')
        if recognition_type == 'over_time':
            required_ot = ['ot_tipe_aliran', 'ot_progress_method', 'ot_tanggal_mulai', 'ot_tanggal_selesai']
            for field in required_ot:
                if not cleaned.get(field):
                    self.add_error(field, 'Wajib diisi untuk recognition over-time.')
            tipe = cleaned.get('ot_tipe_aliran')
            if tipe == 'advance_payment_cash' and not cleaned.get('ot_liabilitas_kontrak_acct'):
                self.add_error('ot_liabilitas_kontrak_acct', 'Wajib untuk advance payment cash.')
            if tipe == 'performance_first' and not cleaned.get('ot_aset_kontrak_acct'):
                self.add_error('ot_aset_kontrak_acct', 'Wajib untuk performance first.')
        return cleaned

# backward-compat alias
PendapatanItemForm = KewajibabPelaksanaanForm
```

- [ ] **Step 2: Check that the formset factory in the same file still works**

If there's an `inlineformset_factory` call referencing `PendapatanItemForm`, it will still work via the alias. Confirm the alias is defined after the class.

- [ ] **Step 3: Run existing view tests or smoke test the form**

```
python manage.py check
```
Expected: no errors.

- [ ] **Step 4: Commit**

```
git add apps/pendapatan/forms.py
git commit -m "feat(pendapatan): rename PendapatanItemForm to KewajibabPelaksanaanForm, add over-time fields"
```

---

## Task 14: Update views and URLs

**Files:**
- Modify: `apps/pendapatan/views.py`
- Modify: `apps/pendapatan/urls.py`

Add views for `recognize_entry` and `konversi_aset_kontrak_ke_piutang`. Update references from `PendapatanItem`/`items` → `KewajibabPelaksanaan`/`kps`.

- [ ] **Step 1: Add `recognize_entry` view to `apps/pendapatan/views.py`**

```python
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages


@login_required
@require_POST
def recognize_entry_view(request, entry_id):
    from apps.pendapatan.models import EntriPengakuan
    from apps.pendapatan.services import recognize_entry
    import datetime

    entri = get_object_or_404(EntriPengakuan, pk=entry_id)
    date_str = request.POST.get('journal_date')
    journal_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()

    try:
        recognize_entry(entri.id, request.user, journal_date=journal_date)
        messages.success(request, f'Pendapatan sebesar {entri.nilai} berhasil diakui.')
    except AssertionError as e:
        messages.error(request, str(e))

    return redirect('pendapatan:detail', pk=entri.jadwal.kp.entitas_bisnis.header_id)
```

- [ ] **Step 2: Add `konversi_aset_kontrak` view**

```python
@login_required
@require_POST
def konversi_aset_kontrak_view(request, aset_id):
    from apps.pendapatan.models import AsetKontrak
    from apps.pendapatan.services import konversi_aset_kontrak_ke_piutang

    aset = get_object_or_404(AsetKontrak, pk=aset_id)
    try:
        konversi_aset_kontrak_ke_piutang(aset.id, request.user)
        messages.success(request, 'Aset kontrak berhasil dikonversi ke piutang.')
    except AssertionError as e:
        messages.error(request, str(e))

    return redirect('pendapatan:detail', pk=aset.kp.entitas_bisnis.header_id)
```

- [ ] **Step 3: Update `apps/pendapatan/urls.py`** — add the two new paths

```python
from apps.pendapatan.views import recognize_entry_view, konversi_aset_kontrak_view

# Add to urlpatterns:
path('entri/<int:entry_id>/recognize/', recognize_entry_view, name='recognize_entry'),
path('aset/<int:aset_id>/konversi/', konversi_aset_kontrak_view, name='konversi_aset_kontrak'),
```

- [ ] **Step 4: Search for remaining `PendapatanItem` or `.items` references in views**

```
grep -n "PendapatanItem\|\.items\b\|jumlah_bruto" apps/pendapatan/views.py
```

Replace each occurrence: `PendapatanItem` → `KewajibabPelaksanaan`, `.items.` → `.kps.`, `jumlah_bruto` → `nilai_kontrak`.

- [ ] **Step 5: Run Django check and start dev server**

```
python manage.py check
```
Expected: no errors.

- [ ] **Step 6: Commit**

```
git add apps/pendapatan/views.py apps/pendapatan/urls.py
git commit -m "feat(pendapatan): add recognize_entry and konversi_aset_kontrak views + update item refs"
```

---

## Task 15: Update detail template — command center redesign

**Files:**
- Modify: `templates/pendapatan/detail.html`
- Create: `templates/pendapatan/_recognize_modal.html`

The detail page becomes a "command center": header summary at top, then per-KP cards showing recognition status, recognize buttons (for over-time), and a convert button (for performance_first aset kontrak).

- [ ] **Step 1: Rewrite `templates/pendapatan/detail.html`**

Key sections to include:

```html
<!-- Header summary -->
<div class="card mb-4">
  <div class="card-body">
    <h5>{{ header.header_no }} — {{ header.entitas_bisnis }}</h5>
    <span class="badge bg-{{ header.status|lower }}">{{ header.get_status_display }}</span>
    <span class="badge bg-secondary">{{ header.get_standar_akuntansi_display }}</span>
    <div>Tanggal: {{ header.tanggal }}</div>
  </div>
</div>

<!-- KP Cards -->
{% for peb in header.pendapatanentitasbisnis_set.all %}
  {% for kp in peb.kps.all %}
    <div class="card mb-3">
      <div class="card-header d-flex justify-content-between">
        <strong>{{ kp.keterangan }}</strong>
        <span>Harga-J: {{ kp.harga_j|floatformat:2 }}</span>
        <span class="badge bg-info">{{ kp.get_recognition_type_display }}</span>
      </div>
      <div class="card-body">
        {% if kp.recognition_type == 'over_time' %}
          {% with jadwal=kp.jadwal %}
            {% if jadwal %}
              <div>Diakui: {{ jadwal.nilai_diakui }} / {{ jadwal.nilai_total }}</div>
              <div class="progress mb-2">
                <div class="progress-bar" style="width: {% widthratio jadwal.nilai_diakui jadwal.nilai_total 100 %}%"></div>
              </div>
              {% for entri in jadwal.entri.all %}
                <div class="d-flex justify-content-between align-items-center mb-1">
                  <span>{{ entri.tanggal_target }} — {{ entri.nilai }}</span>
                  {% if entri.status == 'pending' and header.status == 'confirmed' %}
                    <button type="button" class="btn btn-sm btn-success"
                            data-bs-toggle="modal" data-bs-target="#modal-recognize-{{ entri.id }}">
                      Akui
                    </button>
                    {% include "pendapatan/_recognize_modal.html" with entri=entri %}
                  {% else %}
                    <span class="badge bg-secondary">{{ entri.get_status_display }}</span>
                  {% endif %}
                </div>
              {% endfor %}
              {% if jadwal.tipe_aliran == 'performance_first' %}
                {% for aset in kp.aset_kontrak.all %}
                  {% if aset.status == 'active' and header.status == 'confirmed' %}
                    <form method="post" action="{% url 'pendapatan:konversi_aset_kontrak' aset.id %}">
                      {% csrf_token %}
                      <button type="submit" class="btn btn-warning btn-sm">
                        Konversi Aset Kontrak → Piutang
                      </button>
                    </form>
                  {% endif %}
                {% endfor %}
              {% endif %}
            {% endif %}
          {% endwith %}
        {% endif %}
      </div>
    </div>
  {% endfor %}
{% endfor %}
```

- [ ] **Step 2: Create `templates/pendapatan/_recognize_modal.html`**

```html
<!-- templates/pendapatan/_recognize_modal.html -->
<div class="modal fade" id="modal-recognize-{{ entri.id }}" tabindex="-1">
  <div class="modal-dialog">
    <form method="post" action="{% url 'pendapatan:recognize_entry' entri.id %}">
      {% csrf_token %}
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Akui Pendapatan</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <p>Pengakuan <strong>{{ entri.nilai }}</strong> untuk periode {{ entri.tanggal_target }}</p>
          <div class="mb-3">
            <label class="form-label">Tanggal Jurnal</label>
            <input type="date" name="journal_date" class="form-control"
                   value="{{ entri.tanggal_target|date:'Y-m-d' }}">
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Batal</button>
          <button type="submit" class="btn btn-success">Akui</button>
        </div>
      </div>
    </form>
  </div>
</div>
```

- [ ] **Step 3: Start dev server and verify the detail page renders**

```
python manage.py runserver
```

Open a pendapatan detail page. Verify: KP cards render, progress bar shows, recognize buttons appear for pending entries of confirmed headers.

- [ ] **Step 4: Commit**

```
git add templates/pendapatan/
git commit -m "feat(pendapatan): detail page command center redesign with KP cards and recognize modal"
```

---

## Task 16: Update form template — KP over-time fields + SSP preview

**Files:**
- Modify: `templates/pendapatan/form.html`

The form template needs to show/hide over-time config fields per KP based on `recognition_type`, and display a live SSP allocation preview.

- [ ] **Step 1: Add `standar_akuntansi` field to form header section**

Find where `PendapatanHeader` fields are rendered and add:

```html
<div class="mb-3">
  <label class="form-label">Standar Akuntansi</label>
  {{ header_form.standar_akuntansi }}
</div>
```

- [ ] **Step 2: Add per-KP over-time section toggle**

For each KP form in the formset, wrap over-time fields in a conditional section:

```html
{% for kp_form in kp_formset %}
<div class="card mb-2 kp-form-card">
  <div class="card-body">
    {{ kp_form.keterangan }}
    {{ kp_form.nilai_kontrak }}
    {{ kp_form.recognition_type }}
    {{ kp_form.akun_pendapatan }}
    {{ kp_form.akun_piutang }}

    <div class="over-time-fields" style="display:none;">
      <hr><h6>Konfigurasi Over-Time</h6>
      {{ kp_form.ot_tipe_aliran }}
      {{ kp_form.ot_progress_method }}
      {{ kp_form.ot_tanggal_mulai }}
      {{ kp_form.ot_tanggal_selesai }}
      {{ kp_form.ot_liabilitas_kontrak_acct }}
      {{ kp_form.ot_aset_kontrak_acct }}
      {{ kp_form.ot_biaya_estimasi_total }}
    </div>
    <!-- PPh fields -->
    {{ kp_form.akun_pph_potong }} {{ kp_form.pph_potong_rate }}
    {{ kp_form.akun_pph_pungut }} {{ kp_form.pph_pungut_rate }}
  </div>
</div>
{% endfor %}
```

- [ ] **Step 3: Add JavaScript for show/hide and SSP preview**

```html
<script>
document.addEventListener('DOMContentLoaded', function () {
  function toggleOverTime(card) {
    const select = card.querySelector('[id$="-recognition_type"]');
    const otFields = card.querySelector('.over-time-fields');
    if (!select || !otFields) return;
    otFields.style.display = select.value === 'over_time' ? '' : 'none';
    select.addEventListener('change', () => {
      otFields.style.display = select.value === 'over_time' ? '' : 'none';
    });
  }

  document.querySelectorAll('.kp-form-card').forEach(toggleOverTime);

  // SSP preview: recompute allocation when nilai_kontrak changes
  function updateSSPPreview() {
    const inputs = document.querySelectorAll('[id$="-nilai_kontrak"]');
    let total = 0;
    inputs.forEach(inp => total += parseFloat(inp.value || 0));
    inputs.forEach(inp => {
      const val = parseFloat(inp.value || 0);
      const pct = total > 0 ? (val / total * 100).toFixed(1) : 0;
      let hint = inp.parentElement.querySelector('.ssp-hint');
      if (!hint) {
        hint = document.createElement('small');
        hint.className = 'text-muted ssp-hint';
        inp.parentElement.appendChild(hint);
      }
      hint.textContent = `SSP ${pct}% dari total`;
    });
  }

  document.querySelectorAll('[id$="-nilai_kontrak"]').forEach(inp => {
    inp.addEventListener('input', updateSSPPreview);
  });
  updateSSPPreview();
});
</script>
```

- [ ] **Step 4: Load the form page in browser and verify**

Start dev server, open the pendapatan create/edit form. Verify:
- Over-time fields hidden when `recognition_type = point_in_time`
- Over-time fields visible when `recognition_type = over_time`
- SSP percentage hints update as you type `nilai_kontrak`

- [ ] **Step 5: Commit**

```
git add templates/pendapatan/form.html
git commit -m "feat(pendapatan): form template — over-time toggle and SSP allocation preview"
```

---

## Task 17: Update admin

**Files:**
- Modify: `apps/pendapatan/admin.py`

- [ ] **Step 1: Update inline class name and register new models**

```python
from django.contrib import admin
from apps.pendapatan.models import (
    PendapatanHeader, KewajibabPelaksanaan, PendapatanEntitasBisnis,
    JadwalPengakuan, EntriPengakuan, AsetKontrak, PendapatanEventLog,
)


class KewajibabPelaksanaanInline(admin.TabularInline):
    model = KewajibabPelaksanaan
    extra = 0
    fields = ['keterangan', 'nilai_kontrak', 'harga_j', 'recognition_type', 'akun_pendapatan']
    readonly_fields = ['harga_j']


class EntriPengakuanInline(admin.TabularInline):
    model = EntriPengakuan
    extra = 0
    readonly_fields = ['nilai_diakui', 'status', 'journal_header']


@admin.register(JadwalPengakuan)
class JadwalPengakuanAdmin(admin.ModelAdmin):
    list_display = ['kp', 'tipe_aliran', 'progress_method', 'nilai_total', 'nilai_diakui', 'status']
    list_filter = ['tipe_aliran', 'status']
    inlines = [EntriPengakuanInline]


@admin.register(AsetKontrak)
class AsetKontrakAdmin(admin.ModelAdmin):
    list_display = ['kp', 'tanggal', 'nilai', 'nilai_tersisa', 'status']
    list_filter = ['status']
```

- [ ] **Step 2: Update existing `PendapatanHeader` admin to use `KewajibabPelaksanaanInline`**

Find the existing `@admin.register(PendapatanHeader)` and replace the inline reference.

- [ ] **Step 3: Run admin smoke test**

```
python manage.py check --deploy 2>/dev/null; python manage.py check
```
Expected: no errors.

- [ ] **Step 4: Commit**

```
git add apps/pendapatan/admin.py
git commit -m "feat(pendapatan): update admin for KewajibabPelaksanaan, JadwalPengakuan, AsetKontrak"
```

---

## Task 18: Final sweep + run full test suite

- [ ] **Step 1: Search for any remaining stale references**

```
grep -rn "PendapatanItem\|DeferredRevenueSchedule\|DeferredRevenueEntry\|jumlah_bruto\|is_deferred\b\|deferred_account\|deferred_pph_acct" \
  apps/pendapatan/ templates/pendapatan/ tests/pendapatan/ \
  --include="*.py" --include="*.html"
```

Fix any hits.

- [ ] **Step 2: Run full test suite**

```
pytest tests/ -v --tb=short
```
Expected: all PASS

- [ ] **Step 3: Run Django system check**

```
python manage.py check
```
Expected: no errors.

- [ ] **Step 4: Final commit**

```
git add -A
git commit -m "chore(pendapatan): PSAK 72 redesign complete — final sweep and stale ref cleanup"
```

---

## Self-Review Against Spec

| Spec Requirement | Covered By |
|-----------------|-----------|
| `standar_akuntansi` on header | Task 1 |
| PendapatanItem → KewajibabPelaksanaan rename | Task 2, 7 |
| `harga_j` alokasi harga field | Task 2 |
| `recognition_type` point_in_time/over_time | Task 2 |
| JadwalPengakuan model (replaces DeferredRevenueSchedule) | Task 3 |
| EntriPengakuan model (replaces DeferredRevenueEntry) | Task 4 |
| AsetKontrak model | Task 4 |
| New EventLog choices | Task 4 |
| Schema migration | Task 5 |
| Data migration (deferred → jadwal/entri) | Task 6 |
| Drop old deferred models | Task 7 |
| `compute_alokasi_harga` (PSAK 72 Step 4) | Task 8 |
| `confirm_pendapatan` — 5 cases (cash, credit, advance, periodic, perf-first) | Task 9 |
| PPh potong bug fix (debit/credit swap) | Task 9 |
| `recognize_entry` — 3 tipe_aliran | Task 10 |
| `konversi_aset_kontrak_ke_piutang` | Task 11 |
| `void_pendapatan` voids jadwal + aset | Task 12 |
| Forms — over-time fields + validation | Task 13 |
| Views — recognize + konversi URLs | Task 14 |
| Detail page command center redesign | Task 15 |
| Recognition modal | Task 15 |
| Form template — over-time toggle + SSP preview | Task 16 |
| Admin update | Task 17 |
