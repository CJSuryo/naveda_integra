# Recurring Revenue — Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Template-driven recurring pendapatan generation. Operators define a `RecurringTemplate` once; the system generates a `PendapatanHeader` on each scheduled occurrence (manual or via daily cron).

**Architecture:** `RecurringTemplate` model lives in `apps/pendapatan/`. Service `generate_from_recurring` creates header + items + optionally auto-confirms. `compute_next_date` is a pure function (no DB). Management command for daily cron.

**Tech Stack:** Django 4.x, `dateutil.relativedelta` for month/quarter/year arithmetic, existing `confirm_pendapatan` service from Phase 3.

**Spec:** `docs/superpowers/specs/2026-06-07-recurring-revenue-design.md`

**Prerequisite:** Phase 3 (Pendapatan Core) complete. Phase 4 (Deferred Revenue) NOT required — these phases are parallel.

---

## File Map

| Action | File |
|---|---|
| Modify | `apps/pendapatan/models.py` |
| Create | `apps/pendapatan/migrations/000X_recurring_template.py` (via makemigrations) |
| Modify | `apps/pendapatan/services.py` |
| Create | `apps/pendapatan/management/__init__.py` |
| Create | `apps/pendapatan/management/commands/__init__.py` |
| Create | `apps/pendapatan/management/commands/generate_recurring_pendapatan.py` |
| Modify | `apps/pendapatan/views.py` |
| Modify | `apps/pendapatan/urls.py` |
| Create | `templates/pendapatan/recurring_list.html` |
| Create | `templates/pendapatan/recurring_form.html` |
| Create | `templates/pendapatan/recurring_detail.html` |
| Create | `templates/pendapatan/recurring_calendar.html` |
| Modify | `apps/pendapatan/admin.py` |
| Modify | `apps/pendapatan/tests.py` |

---

## Task 1: RecurringTemplate model + migration

**Files:**
- Modify: `apps/pendapatan/models.py`

- [ ] **Step 1: Add `source_recurring` FK to PendapatanHeader**

In `apps/pendapatan/models.py`, inside `PendapatanHeader`, add after `source_type`:

```python
source_recurring = models.ForeignKey(
    'RecurringTemplate',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='generated_headers',
    verbose_name='Template Recurring',
)
```

- [ ] **Step 2: Add RecurringTemplate model**

In `apps/pendapatan/models.py`, add after `PendapatanEventLog`:

```python
class RecurringTemplate(models.Model):
    FREKUENSI_CHOICES = [
        ('harian', 'Harian'),
        ('mingguan', 'Mingguan'),
        ('bulanan', 'Bulanan'),
        ('triwulanan', 'Triwulanan'),
        ('semesteran', 'Semesteran'),
        ('tahunan', 'Tahunan'),
    ]

    nama = models.CharField(max_length=255, verbose_name='Nama Template')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Entitas Bisnis Lv3',
    )
    deskripsi_item = models.TextField(verbose_name='Deskripsi Item')
    kategori = models.CharField(
        max_length=50,
        choices=PendapatanItem.KATEGORI_CHOICES,
        verbose_name='Kategori',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType',
        on_delete=models.PROTECT,
        verbose_name='Sub Transaction Type',
    )
    jumlah = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Jumlah per Periode',
    )
    revenue_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='recurring_revenue_templates',
        verbose_name='Akun Pendapatan',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='recurring_payment_templates',
        verbose_name='Akun Pembayaran',
    )
    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'Cash'), ('credit', 'Kredit')],
        default='cash',
        verbose_name='Tipe Pembayaran',
    )
    frekuensi = models.CharField(
        max_length=20,
        choices=FREKUENSI_CHOICES,
        verbose_name='Frekuensi',
    )
    tanggal_mulai = models.DateField(verbose_name='Tanggal Mulai')
    tanggal_selesai = models.DateField(
        null=True,
        blank=True,
        verbose_name='Tanggal Selesai',
    )
    tanggal_berikutnya = models.DateField(verbose_name='Tanggal Berikutnya')
    auto_confirm = models.BooleanField(
        default=False,
        verbose_name='Auto Konfirmasi',
    )
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['tanggal_berikutnya']
        verbose_name = 'Recurring Template'
        verbose_name_plural = 'Recurring Templates'

    def __str__(self):
        return self.nama

    def save(self, *args, **kwargs):
        if not self.pk and not self.tanggal_berikutnya:
            self.tanggal_berikutnya = self.tanggal_mulai
        super().save(*args, **kwargs)
```

- [ ] **Step 3: Run makemigrations**

```bash
python manage.py makemigrations pendapatan --name recurring_template
```

Expected: new migration file created.

- [ ] **Step 4: Run migrate**

```bash
python manage.py migrate pendapatan
```

Expected: `Applying pendapatan.000X_recurring_template... OK`

- [ ] **Step 5: Verify no regressions**

```bash
python manage.py test apps.pendapatan -v 2
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/models.py apps/pendapatan/migrations/
git commit -m "feat(pendapatan): add RecurringTemplate model and source_recurring FK"
```

---

## Task 2: Services — compute_next_date + generate_from_recurring

**Files:**
- Modify: `apps/pendapatan/services.py`
- Modify: `apps/pendapatan/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `apps/pendapatan/tests.py`:

```python
from datetime import date
from apps.pendapatan.services import compute_next_date, generate_from_recurring


class ComputeNextDateTests(TestCase):
    def test_harian(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'harian'), date(2026, 1, 16))

    def test_mingguan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'mingguan'), date(2026, 1, 22))

    def test_bulanan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 31), 'bulanan'), date(2026, 2, 28))

    def test_triwulanan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'triwulanan'), date(2026, 4, 15))

    def test_semesteran(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'semesteran'), date(2026, 7, 15))

    def test_tahunan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'tahunan'), date(2027, 1, 15))


class GenerateFromRecurringTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
        from apps.master_data.models import Akun
        from apps.purchase.models import SubTransactionType
        from apps.pendapatan.models import RecurringTemplate

        tipe = TipeEntitas.objects.create(nama='Pelanggan')
        self.eb = EntitasBisnis.objects.create(
            nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan'
        )
        self.revenue_akun = Akun.objects.create(
            kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1'
        )
        self.kas_akun = Akun.objects.create(
            kategori_id='aset', nama='Kas', kode_akun='1.1.1'
        )
        self.stt = SubTransactionType.objects.create(
            nama='Pendapatan Sewa', module='pendapatan', direction='inflow',
            default_offset_account=self.revenue_akun,
        )
        self.template = RecurringTemplate.objects.create(
            nama='Sewa Kantor',
            entitas_bisnis=self.eb,
            deskripsi_item='Sewa bulan berikutnya',
            kategori='jasa',
            sub_transaction_type=self.stt,
            jumlah=Decimal('5000000'),
            revenue_account=self.revenue_akun,
            payment_account=self.kas_akun,
            payment_type='cash',
            frekuensi='bulanan',
            tanggal_mulai=date(2026, 1, 1),
            tanggal_berikutnya=date(2026, 1, 1),
        )

    def test_creates_pendapatan_header(self):
        header = generate_from_recurring(self.template, user=None)
        self.assertIsNotNone(header.pk)
        self.assertEqual(header.source_type, 'recurring')
        self.assertEqual(header.source_recurring, self.template)
        self.assertEqual(header.status, 'draft')

    def test_creates_pendapatan_item(self):
        header = generate_from_recurring(self.template, user=None)
        items = header.pendapatan_ebs.first().items.all()
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().jumlah_bruto, Decimal('5000000'))

    def test_advances_tanggal_berikutnya(self):
        generate_from_recurring(self.template, user=None)
        self.template.refresh_from_db()
        self.assertEqual(self.template.tanggal_berikutnya, date(2026, 2, 1))

    def test_deactivates_after_tanggal_selesai(self):
        self.template.tanggal_selesai = date(2026, 1, 31)
        self.template.save()
        generate_from_recurring(self.template, user=None)
        self.template.refresh_from_db()
        self.assertFalse(self.template.is_active)

    def test_auto_confirm_confirms_header(self):
        self.template.auto_confirm = True
        self.template.save()
        header = generate_from_recurring(self.template, user=None)
        self.assertEqual(header.status, 'confirmed')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test apps.pendapatan.tests.ComputeNextDateTests apps.pendapatan.tests.GenerateFromRecurringTests -v 2
```

Expected: `ImportError` or `AttributeError` — functions not yet implemented.

- [ ] **Step 3: Implement compute_next_date**

Add to `apps/pendapatan/services.py`:

```python
from datetime import date, timedelta


def compute_next_date(current_date: date, frekuensi: str) -> date:
    from dateutil.relativedelta import relativedelta

    DELTA_MAP = {
        'harian': timedelta(days=1),
        'mingguan': timedelta(weeks=1),
        'bulanan': relativedelta(months=1),
        'triwulanan': relativedelta(months=3),
        'semesteran': relativedelta(months=6),
        'tahunan': relativedelta(years=1),
    }
    delta = DELTA_MAP.get(frekuensi)
    if delta is None:
        raise ValueError(f'Frekuensi tidak dikenal: {frekuensi}')
    return current_date + delta
```

- [ ] **Step 4: Implement generate_from_recurring**

Add to `apps/pendapatan/services.py`:

```python
def generate_from_recurring(template, user=None):
    from apps.pendapatan.models import (
        PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog,
    )

    with transaction.atomic():
        header = PendapatanHeader.objects.create(
            tanggal=template.tanggal_berikutnya,
            deskripsi=f'{template.nama} — {template.tanggal_berikutnya}',
            payment_type=template.payment_type,
            source_type='recurring',
            source_recurring=template,
            status='draft',
            created_by=user,
        )

        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header,
            entitas_bisnis=template.entitas_bisnis,
            entitas_bisnis_lv2=template.entitas_bisnis_lv2,
            entitas_bisnis_lv3=template.entitas_bisnis_lv3,
        )

        PendapatanItem.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item=template.deskripsi_item,
            kategori=template.kategori,
            sub_transaction_type=template.sub_transaction_type,
            jumlah_bruto=template.jumlah,
            diskon=Decimal('0'),
            pajak=Decimal('0'),
            revenue_account=template.revenue_account,
            payment_account=template.payment_account,
            is_deferred=False,
        )

        new_next = compute_next_date(template.tanggal_berikutnya, template.frekuensi)
        template.tanggal_berikutnya = new_next
        if template.tanggal_selesai and new_next > template.tanggal_selesai:
            template.is_active = False
        template.save(update_fields=['tanggal_berikutnya', 'is_active'])

        PendapatanEventLog.objects.create(
            pendapatan_header=header,
            event_type='RECURRING_GENERATED',
            description=f'Generated from template {template.pk}',
            user=user,
        )

        if template.auto_confirm:
            confirm_pendapatan(header, user=user)

    return header
```

- [ ] **Step 5: Run tests**

```bash
python manage.py test apps.pendapatan.tests.ComputeNextDateTests apps.pendapatan.tests.GenerateFromRecurringTests -v 2
```

Expected: all 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/services.py apps/pendapatan/tests.py
git commit -m "feat(pendapatan): implement compute_next_date and generate_from_recurring"
```

---

## Task 3: Management command

**Files:**
- Create: `apps/pendapatan/management/__init__.py`
- Create: `apps/pendapatan/management/commands/__init__.py`
- Create: `apps/pendapatan/management/commands/generate_recurring_pendapatan.py`

> **Note:** If `apps/pendapatan/management/` already exists from Phase 4 (deferred revenue command), skip `__init__.py` creation and add command file only.

- [ ] **Step 1: Create management command directories if needed**

```bash
python -c "import os; os.makedirs('apps/pendapatan/management/commands', exist_ok=True)"
touch apps/pendapatan/management/__init__.py
touch apps/pendapatan/management/commands/__init__.py
```

- [ ] **Step 2: Write command file**

Create `apps/pendapatan/management/commands/generate_recurring_pendapatan.py`:

```python
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate pendapatan headers from active recurring templates due today.'

    def handle(self, *args, **options):
        from apps.pendapatan.models import RecurringTemplate
        from apps.pendapatan.services import generate_from_recurring
        from django.contrib.auth import get_user_model

        User = get_user_model()
        today = timezone.localdate()

        system_user = User.objects.filter(is_superuser=True).first()

        templates = RecurringTemplate.objects.filter(
            is_active=True,
            tanggal_berikutnya__lte=today,
        ).filter(
            models.Q(tanggal_selesai__isnull=True) |
            models.Q(tanggal_berikutnya__lte=models.F('tanggal_selesai'))
        )

        generated = 0
        confirmed = 0
        errors = 0

        for template in templates:
            try:
                header = generate_from_recurring(template, user=system_user)
                generated += 1
                if header.status == 'confirmed':
                    confirmed += 1
            except Exception as e:
                errors += 1
                self.stderr.write(f'Error template {template.pk} ({template.nama}): {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Generated: {generated}, Confirmed: {confirmed}, Errors: {errors}'
            )
        )
```

> **Fix import:** Add `from django.db import models` at the top of the command file (needed for `models.Q` and `models.F`).

Corrected imports block:

```python
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone
```

- [ ] **Step 3: Test command dry-run**

```bash
python manage.py generate_recurring_pendapatan
```

Expected (empty DB): `Done. Generated: 0, Confirmed: 0, Errors: 0`

- [ ] **Step 4: Commit**

```bash
git add apps/pendapatan/management/
git commit -m "feat(pendapatan): add generate_recurring_pendapatan management command"
```

---

## Task 4: Admin registration

**Files:**
- Modify: `apps/pendapatan/admin.py`

- [ ] **Step 1: Register RecurringTemplate**

In `apps/pendapatan/admin.py`, add:

```python
@admin.register(RecurringTemplate)
class RecurringTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'nama', 'entitas_bisnis', 'frekuensi', 'jumlah',
        'tanggal_berikutnya', 'auto_confirm', 'is_active',
    ]
    list_filter = ['frekuensi', 'is_active', 'auto_confirm', 'payment_type']
    search_fields = ['nama', 'entitas_bisnis__nama']
    readonly_fields = ['tanggal_berikutnya', 'created_at', 'created_by']
```

- [ ] **Step 2: Commit**

```bash
git add apps/pendapatan/admin.py
git commit -m "feat(pendapatan): register RecurringTemplate in admin"
```

---

## Task 5: Views, URLs, templates

**Files:**
- Modify: `apps/pendapatan/views.py`
- Modify: `apps/pendapatan/urls.py`
- Create: `templates/pendapatan/recurring_list.html`
- Create: `templates/pendapatan/recurring_form.html`
- Create: `templates/pendapatan/recurring_detail.html`
- Create: `templates/pendapatan/recurring_calendar.html`

### URL plan

```
/pendapatan/recurring/                  recurring_list
/pendapatan/recurring/create/           recurring_create
/pendapatan/recurring/<pk>/             recurring_detail
/pendapatan/recurring/<pk>/edit/        recurring_edit
/pendapatan/recurring/<pk>/delete/      recurring_delete  (POST → set is_active=False)
/pendapatan/recurring/<pk>/generate/    recurring_generate (POST → generate_from_recurring)
/pendapatan/reports/recurring/          recurring_calendar
```

- [ ] **Step 1: Add RecurringTemplateForm**

In `apps/pendapatan/forms.py`, add:

```python
class RecurringTemplateForm(forms.ModelForm):
    class Meta:
        model = RecurringTemplate
        fields = [
            'nama', 'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
            'deskripsi_item', 'kategori', 'sub_transaction_type', 'jumlah',
            'revenue_account', 'payment_account', 'payment_type',
            'frekuensi', 'tanggal_mulai', 'tanggal_selesai', 'auto_confirm',
        ]
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'deskripsi_item': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input'}),
            'kategori': forms.Select(attrs={'class': 'ni-input'}),
            'payment_type': forms.Select(attrs={'class': 'ni-input'}),
            'frekuensi': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'sub_transaction_type': forms.Select(attrs={'class': 'ni-input'}),
            'revenue_account': forms.Select(attrs={'class': 'ni-input'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal_mulai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'tanggal_selesai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'auto_confirm': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }
```

- [ ] **Step 2: Add views**

In `apps/pendapatan/views.py`, add:

```python
# ── Recurring Template Views ──────────────────────────────────────────────────

@login_required
def recurring_list(request):
    templates = RecurringTemplate.objects.select_related('entitas_bisnis').filter(is_active=True)
    inactive = RecurringTemplate.objects.filter(is_active=False)
    return render(request, 'pendapatan/recurring_list.html', {
        'templates': templates,
        'inactive': inactive,
    })


@login_required
def recurring_create(request):
    form = RecurringTemplateForm(request.POST or None)
    if form.is_valid():
        template = form.save(commit=False)
        template.tanggal_berikutnya = template.tanggal_mulai
        template.created_by = request.user
        template.save()
        messages.success(request, f'Template "{template.nama}" berhasil dibuat.')
        return redirect('pendapatan:recurring_detail', pk=template.pk)
    return render(request, 'pendapatan/recurring_form.html', {'form': form, 'title': 'Buat Template Recurring'})


@login_required
def recurring_detail(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    generated = template.generated_headers.order_by('-tanggal')[:20]
    return render(request, 'pendapatan/recurring_detail.html', {
        'template': template,
        'generated': generated,
    })


@login_required
def recurring_edit(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    form = RecurringTemplateForm(request.POST or None, instance=template)
    if form.is_valid():
        form.save()
        messages.success(request, 'Template berhasil diperbarui.')
        return redirect('pendapatan:recurring_detail', pk=template.pk)
    return render(request, 'pendapatan/recurring_form.html', {'form': form, 'title': 'Edit Template Recurring'})


@login_required
def recurring_delete(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    if request.method == 'POST':
        template.is_active = False
        template.save(update_fields=['is_active'])
        messages.success(request, f'Template "{template.nama}" dinonaktifkan.')
        return redirect('pendapatan:recurring_list')
    return render(request, 'pendapatan/recurring_confirm_delete.html', {'template': template})


@login_required
def recurring_generate(request, pk):
    if request.method != 'POST':
        return redirect('pendapatan:recurring_detail', pk=pk)
    template = get_object_or_404(RecurringTemplate, pk=pk, is_active=True)
    try:
        header = generate_from_recurring(template, user=request.user)
        messages.success(request, f'Pendapatan {header.nomor_pendapatan} berhasil dibuat.')
    except Exception as e:
        messages.error(request, f'Gagal generate: {e}')
    return redirect('pendapatan:recurring_detail', pk=pk)


@login_required
def recurring_calendar(request):
    from datetime import date
    from dateutil.relativedelta import relativedelta

    today = date.today()
    end_date = today + relativedelta(months=3)
    templates = RecurringTemplate.objects.filter(
        is_active=True,
        tanggal_berikutnya__lte=end_date,
    ).order_by('tanggal_berikutnya')
    return render(request, 'pendapatan/recurring_calendar.html', {
        'templates': templates,
        'today': today,
        'end_date': end_date,
    })
```

- [ ] **Step 3: Add URLs**

In `apps/pendapatan/urls.py`, add to `urlpatterns`:

```python
# Recurring Templates
path('recurring/', views.recurring_list, name='recurring_list'),
path('recurring/create/', views.recurring_create, name='recurring_create'),
path('recurring/<int:pk>/', views.recurring_detail, name='recurring_detail'),
path('recurring/<int:pk>/edit/', views.recurring_edit, name='recurring_edit'),
path('recurring/<int:pk>/delete/', views.recurring_delete, name='recurring_delete'),
path('recurring/<int:pk>/generate/', views.recurring_generate, name='recurring_generate'),
path('reports/recurring/', views.recurring_calendar, name='recurring_calendar'),
```

- [ ] **Step 4: Create recurring_list.html**

Create `templates/pendapatan/recurring_list.html`:

```html
{% extends "base.html" %}
{% block title %}Recurring Templates{% endblock %}
{% block content %}
<div class="ni-page-header">
  <h1 class="ni-page-title">Template Recurring Pendapatan</h1>
  <a href="{% url 'pendapatan:recurring_create' %}" class="ni-btn ni-btn-primary">+ Buat Template</a>
</div>

<div class="ni-card">
  <table class="ni-table">
    <thead>
      <tr>
        <th>Nama</th>
        <th>Entitas Bisnis</th>
        <th>Frekuensi</th>
        <th>Jumlah</th>
        <th>Berikutnya</th>
        <th>Auto Konfirmasi</th>
        <th>Aksi</th>
      </tr>
    </thead>
    <tbody>
      {% for t in templates %}
      <tr>
        <td><a href="{% url 'pendapatan:recurring_detail' t.pk %}">{{ t.nama }}</a></td>
        <td>{{ t.entitas_bisnis }}</td>
        <td>{{ t.get_frekuensi_display }}</td>
        <td>{{ t.jumlah|floatformat:0 }}</td>
        <td>{{ t.tanggal_berikutnya }}</td>
        <td>{% if t.auto_confirm %}Ya{% else %}Tidak{% endif %}</td>
        <td>
          <a href="{% url 'pendapatan:recurring_edit' t.pk %}" class="ni-btn ni-btn-sm">Edit</a>
          <form method="post" action="{% url 'pendapatan:recurring_generate' t.pk %}" style="display:inline">
            {% csrf_token %}
            <button type="submit" class="ni-btn ni-btn-sm ni-btn-success">Generate</button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="7">Belum ada template recurring aktif.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% if inactive %}
<div class="ni-card">
  <h3>Template Tidak Aktif</h3>
  <table class="ni-table">
    <thead>
      <tr><th>Nama</th><th>Entitas Bisnis</th><th>Frekuensi</th><th>Jumlah</th></tr>
    </thead>
    <tbody>
      {% for t in inactive %}
      <tr>
        <td><a href="{% url 'pendapatan:recurring_detail' t.pk %}">{{ t.nama }}</a></td>
        <td>{{ t.entitas_bisnis }}</td>
        <td>{{ t.get_frekuensi_display }}</td>
        <td>{{ t.jumlah|floatformat:0 }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create recurring_form.html**

Create `templates/pendapatan/recurring_form.html`:

```html
{% extends "base.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <h1 class="ni-page-title">{{ title }}</h1>
</div>

<div class="ni-card">
  <form method="post">
    {% csrf_token %}
    <div class="ni-form-grid">
      {% for field in form %}
      <div class="ni-form-group {% if field.errors %}ni-form-group--error{% endif %}">
        <label class="ni-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
        {{ field }}
        {% for error in field.errors %}
          <span class="ni-form-error">{{ error }}</span>
        {% endfor %}
      </div>
      {% endfor %}
    </div>
    <div class="ni-form-actions">
      <button type="submit" class="ni-btn ni-btn-primary">Simpan</button>
      <a href="{% url 'pendapatan:recurring_list' %}" class="ni-btn">Batal</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Create recurring_detail.html**

Create `templates/pendapatan/recurring_detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ template.nama }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <h1 class="ni-page-title">{{ template.nama }}</h1>
  <div class="ni-page-actions">
    <a href="{% url 'pendapatan:recurring_edit' template.pk %}" class="ni-btn">Edit</a>
    {% if template.is_active %}
    <form method="post" action="{% url 'pendapatan:recurring_generate' template.pk %}" style="display:inline">
      {% csrf_token %}
      <button type="submit" class="ni-btn ni-btn-primary">Generate Sekarang</button>
    </form>
    <form method="post" action="{% url 'pendapatan:recurring_delete' template.pk %}" style="display:inline">
      {% csrf_token %}
      <button type="submit" class="ni-btn ni-btn-danger" onclick="return confirm('Nonaktifkan template ini?')">Nonaktifkan</button>
    </form>
    {% endif %}
  </div>
</div>

<div class="ni-card">
  <dl class="ni-detail-grid">
    <dt>Entitas Bisnis</dt><dd>{{ template.entitas_bisnis }}</dd>
    <dt>Deskripsi Item</dt><dd>{{ template.deskripsi_item }}</dd>
    <dt>Jumlah</dt><dd>{{ template.jumlah|floatformat:0 }}</dd>
    <dt>Frekuensi</dt><dd>{{ template.get_frekuensi_display }}</dd>
    <dt>Tanggal Mulai</dt><dd>{{ template.tanggal_mulai }}</dd>
    <dt>Tanggal Selesai</dt><dd>{{ template.tanggal_selesai|default:"-" }}</dd>
    <dt>Berikutnya</dt><dd>{{ template.tanggal_berikutnya }}</dd>
    <dt>Auto Konfirmasi</dt><dd>{% if template.auto_confirm %}Ya{% else %}Tidak{% endif %}</dd>
    <dt>Status</dt><dd>{% if template.is_active %}Aktif{% else %}Tidak Aktif{% endif %}</dd>
  </dl>
</div>

<div class="ni-card">
  <h3>Pendapatan Dihasilkan (20 Terakhir)</h3>
  <table class="ni-table">
    <thead>
      <tr><th>Nomor</th><th>Tanggal</th><th>Status</th></tr>
    </thead>
    <tbody>
      {% for h in generated %}
      <tr>
        <td><a href="{% url 'pendapatan:detail' h.pk %}">{{ h.nomor_pendapatan }}</a></td>
        <td>{{ h.tanggal }}</td>
        <td>{{ h.status }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="3">Belum ada pendapatan dihasilkan.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 7: Create recurring_calendar.html**

Create `templates/pendapatan/recurring_calendar.html`:

```html
{% extends "base.html" %}
{% block title %}Kalender Recurring{% endblock %}
{% block content %}
<div class="ni-page-header">
  <h1 class="ni-page-title">Jadwal Recurring — 3 Bulan Ke Depan</h1>
  <span class="ni-text-muted">{{ today }} s/d {{ end_date }}</span>
</div>

<div class="ni-card">
  <table class="ni-table">
    <thead>
      <tr>
        <th>Tanggal</th>
        <th>Template</th>
        <th>Entitas Bisnis</th>
        <th>Jumlah</th>
        <th>Auto Konfirmasi</th>
        <th>Aksi</th>
      </tr>
    </thead>
    <tbody>
      {% for t in templates %}
      <tr>
        <td>{{ t.tanggal_berikutnya }}</td>
        <td><a href="{% url 'pendapatan:recurring_detail' t.pk %}">{{ t.nama }}</a></td>
        <td>{{ t.entitas_bisnis }}</td>
        <td>{{ t.jumlah|floatformat:0 }}</td>
        <td>{% if t.auto_confirm %}Ya{% else %}Tidak{% endif %}</td>
        <td>
          <form method="post" action="{% url 'pendapatan:recurring_generate' t.pk %}" style="display:inline">
            {% csrf_token %}
            <button type="submit" class="ni-btn ni-btn-sm ni-btn-success">Generate</button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6">Tidak ada jadwal recurring dalam 3 bulan ke depan.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 8: Run full test suite**

```bash
python manage.py test apps.pendapatan -v 2
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/pendapatan/views.py apps/pendapatan/urls.py apps/pendapatan/forms.py
git add templates/pendapatan/
git commit -m "feat(pendapatan): recurring template views, URLs, and templates"
```

---

## Task 6: Full test run

- [ ] **Step 1: Run all affected apps**

```bash
python manage.py test apps.pendapatan apps.piutang apps.sales -v 2
```

Expected: all tests PASS, zero regressions.

- [ ] **Step 2: Smoke test in browser**

```bash
python manage.py runserver
```

- Open `/pendapatan/recurring/` — list renders
- Click "Buat Template" — form renders with all fields
- Create template with `frekuensi=bulanan`, `auto_confirm=False`
- On detail page, click "Generate Sekarang" — new pendapatan created as draft
- Check `tanggal_berikutnya` advanced by 1 month
- Edit template, set `auto_confirm=True`
- Generate again — new pendapatan created as confirmed

- [ ] **Step 3: Test management command**

```bash
python manage.py generate_recurring_pendapatan
```

Expected: processes templates with `tanggal_berikutnya <= today`, prints summary.

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "feat(pendapatan): Phase 5 complete — recurring revenue templates"
```
