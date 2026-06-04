# Kasir POS — Phase 1: Data Models

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `created_by` FK + `SalesEventLog` to the sales app, and add `OutletPOSConfig` to pos_config for lv3 POS cascade.

**Architecture:** Pure Django model + migration work. No view changes yet. `SalesEventLog` is written to by views/services in later phases.

**Tech Stack:** Django ORM, pytest/django TestCase

---

### Task 1: SalesHeader.created_by + SalesEventLog

**Files:**
- Modify: `apps/sales/models.py`
- Modify: `apps/sales/tests.py`

- [ ] **Step 1: Add `created_by` to SalesHeader and define SalesEventLog**

In `apps/sales/models.py`, add at the top of imports:
```python
from django.conf import settings
```

Add `created_by` field inside `SalesHeader` after `updated_at`:
```python
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_created',
        verbose_name='Dibuat oleh',
    )
```

Append `SalesEventLog` class at the bottom of the file:
```python
class SalesEventLog(models.Model):
    EVENT_CHOICES = [
        ('CREATED', 'Dibuat'),
        ('EDITED', 'Diedit'),
        ('VOIDED', 'Dibatalkan'),
        ('FIFO_PROCESSED', 'FIFO Diproses'),
        ('JOURNAL_CREATED', 'Jurnal Dibuat'),
        ('PAYMENT_PROCESSED', 'Pembayaran Diproses'),
        ('LOCKED', 'Dikunci'),
    ]

    sales_header = models.ForeignKey(
        SalesHeader,
        on_delete=models.CASCADE,
        related_name='event_logs',
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    description = models.TextField(blank=True, default='')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_event_logs',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sales Event Log'
        verbose_name_plural = 'Sales Event Logs'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['sales_header', 'timestamp'], name='idx_sel_header_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.sales_header.transaction_id} — {self.event_type} @ {self.timestamp}'
```

- [ ] **Step 2: Write tests**

Add to `apps/sales/tests.py`:
```python
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesEventLog


class SalesEventLogTests(TestCase):
    def setUp(self):
        self.header = SalesHeader.objects.create()

    def test_log_creation(self):
        log = SalesEventLog.objects.create(
            sales_header=self.header,
            event_type='CREATED',
            description='Test',
        )
        self.assertEqual(log.sales_header, self.header)
        self.assertEqual(log.event_type, 'CREATED')
        self.assertIsNone(log.actor)

    def test_logs_ordered_by_timestamp(self):
        SalesEventLog.objects.create(sales_header=self.header, event_type='CREATED')
        SalesEventLog.objects.create(sales_header=self.header, event_type='EDITED')
        logs = list(SalesEventLog.objects.filter(sales_header=self.header))
        self.assertEqual(logs[0].event_type, 'CREATED')
        self.assertEqual(logs[1].event_type, 'EDITED')

    def test_cascade_delete(self):
        SalesEventLog.objects.create(sales_header=self.header, event_type='CREATED')
        self.header.delete()
        self.assertEqual(SalesEventLog.objects.count(), 0)


class SalesHeaderCreatedByTests(TestCase):
    def test_created_by_nullable(self):
        h = SalesHeader.objects.create()
        self.assertIsNone(h.created_by)
```

- [ ] **Step 3: Run tests (expect fail — models not migrated yet)**

```
python manage.py test apps.sales.tests.SalesEventLogTests -v 2
```
Expected: `OperationalError` or `ProgrammingError` — table/column not found.

- [ ] **Step 4: Generate and apply migration**

```
python manage.py makemigrations sales --name salesheader_createdby_eventlog
python manage.py migrate
```

- [ ] **Step 5: Run tests (expect pass)**

```
python manage.py test apps.sales.tests.SalesEventLogTests apps.sales.tests.SalesHeaderCreatedByTests -v 2
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/sales/models.py apps/sales/tests.py apps/sales/migrations/
git commit -m "feat(sales): add created_by FK and SalesEventLog model"
```

---

### Task 2: OutletPOSConfig model

**Files:**
- Modify: `apps/pos_config/models.py`
- Create: `apps/pos_config/tests/test_outlet_config.py`

- [ ] **Step 1: Add OutletPOSConfig to pos_config/models.py**

At the top of `apps/pos_config/models.py`, existing imports already have `EntitasBisnis`, `EntitasBisnisLv2`. Add `EntitasBisnisLv3`:
```python
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
```

Append at the bottom of the file:
```python
class OutletPOSConfig(models.Model):
    """Lv3-specific POS config. Overrides MerchantPOSConfig (lv1) for STT + accounts."""

    entitas_bisnis_lv3 = models.OneToOneField(
        EntitasBisnisLv3,
        on_delete=models.CASCADE,
        related_name='pos_config',
    )
    merchant_config = models.ForeignKey(
        MerchantPOSConfig,
        on_delete=models.CASCADE,
        related_name='outlets',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_configs',
        verbose_name='Sub-Transaction Type (Override)',
        help_text='Kosongkan = pakai default dari Merchant (lv1).',
    )
    revenue_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_revenue',
        verbose_name='Revenue Account (Override)',
    )
    offset_coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_offset',
        verbose_name='HPP Account (Override)',
    )
    default_payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_payment',
        verbose_name='Payment Account (Override)',
    )
    tax_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Tax % (Override)',
        help_text='Kosongkan = pakai default dari Store (lv2) atau Merchant (lv1).',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Outlet POS Config'

    def __str__(self) -> str:
        return f'Outlet POS Config — {self.entitas_bisnis_lv3.nama}'
```

- [ ] **Step 2: Write tests**

Create `apps/pos_config/tests/test_outlet_config.py`:
```python
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from apps.pos_config.models import MerchantPOSConfig, OutletPOSConfig


class OutletPOSConfigTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda Kopi', tipe_entitas=tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Senopati Area')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet Senopati')
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb,
            default_tax_pct=Decimal('11.00'),
        )

    def test_outlet_config_creation(self):
        cfg = OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
        )
        self.assertEqual(str(cfg), f'Outlet POS Config — {self.lv3.nama}')
        self.assertIsNone(cfg.tax_pct)
        self.assertTrue(cfg.is_active)

    def test_one_to_one_constraint(self):
        OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            OutletPOSConfig.objects.create(
                entitas_bisnis_lv3=self.lv3,
                merchant_config=self.merchant,
            )
```

- [ ] **Step 3: Run tests (expect fail — not migrated)**

```
python manage.py test apps.pos_config.tests.test_outlet_config -v 2
```
Expected: table does not exist error.

- [ ] **Step 4: Migrate**

```
python manage.py makemigrations pos_config --name outlet_pos_config
python manage.py migrate
```

- [ ] **Step 5: Run tests (expect pass)**

```
python manage.py test apps.pos_config.tests.test_outlet_config -v 2
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pos_config/models.py apps/pos_config/migrations/ apps/pos_config/tests/test_outlet_config.py
git commit -m "feat(pos_config): add OutletPOSConfig model for lv3 POS cascade"
```

---

### Task 3: resolve_pos_config utility

**Files:**
- Create: `apps/pos_config/utils.py`
- Create: `apps/pos_config/tests/test_utils.py`

- [ ] **Step 1: Write failing test first**

Create `apps/pos_config/tests/test_utils.py`:
```python
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from apps.pos_config.models import MerchantPOSConfig, StorePOSConfig, OutletPOSConfig
from apps.pos_config.utils import resolve_pos_config


class ResolvePOSConfigTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda', tipe_entitas=tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Area')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet')
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb,
            default_tax_pct=Decimal('11.00'),
        )

    def test_returns_merchant_defaults_when_no_overrides(self):
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertIsNone(cfg['sub_transaction_type'])
        self.assertEqual(cfg['tax_pct'], Decimal('11.00'))

    def test_store_tax_overrides_merchant(self):
        StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2,
            merchant_config=self.merchant,
            tax_pct=Decimal('5.00'),
        )
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('5.00'))

    def test_outlet_tax_overrides_store(self):
        StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2,
            merchant_config=self.merchant,
            tax_pct=Decimal('5.00'),
        )
        OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
            tax_pct=Decimal('0.00'),
        )
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('0.00'))

    def test_no_config_returns_zero_tax(self):
        eb2 = EntitasBisnis.objects.create(nama='Other', tipe_entitas=TipeEntitas.objects.first())
        lv2b = EntitasBisnisLv2.objects.create(entitas_bisnis=eb2, nama='B')
        lv3b = EntitasBisnisLv3.objects.create(parent_lv2=lv2b, nama='C')
        lv3b = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis', 'parent_lv2__pos_config',
        ).get(pk=lv3b.pk)
        cfg = resolve_pos_config(lv3b)
        self.assertEqual(cfg['tax_pct'], Decimal('0'))
```

- [ ] **Step 2: Run test to verify fail**

```
python manage.py test apps.pos_config.tests.test_utils -v 2
```
Expected: `ImportError: cannot import name 'resolve_pos_config'`

- [ ] **Step 3: Create utils.py**

Create `apps/pos_config/utils.py`:
```python
from decimal import Decimal


def resolve_pos_config(lv3) -> dict:
    """Return effective POS config for a lv3 outlet.

    Resolution order: lv3 (OutletPOSConfig) → lv2 (StorePOSConfig) → lv1 (MerchantPOSConfig).
    lv2 (StorePOSConfig) overrides tax only; STT + accounts cascade lv3 → lv1 directly.
    """
    outlet = getattr(lv3, 'pos_config', None)
    store = getattr(getattr(lv3, 'parent_lv2', None), 'pos_config', None)
    merchant = getattr(
        getattr(getattr(lv3, 'parent_lv2', None), 'entitas_bisnis', None),
        'pos_config',
        None,
    )

    def first(*vals):
        return next((v for v in vals if v is not None), None)

    tax = first(
        outlet.tax_pct if outlet else None,
        store.tax_pct if store else None,
        merchant.default_tax_pct if merchant else None,
    )

    return {
        'sub_transaction_type_id': first(
            outlet.sub_transaction_type_id if outlet else None,
            merchant.sub_transaction_type_id if merchant else None,
        ),
        'revenue_account_id': first(
            outlet.revenue_account_id if outlet else None,
            merchant.revenue_account_id if merchant else None,
        ),
        'offset_coa_account_id': first(
            outlet.offset_coa_account_id if outlet else None,
            merchant.offset_coa_account_id if merchant else None,
        ),
        'payment_account_id': first(
            outlet.default_payment_account_id if outlet else None,
            merchant.default_payment_account_id if merchant else None,
        ),
        'tax_pct': tax if tax is not None else Decimal('0'),
        'sub_transaction_type': first(
            outlet.sub_transaction_type_id if outlet else None,
            merchant.sub_transaction_type_id if merchant else None,
        ),
        'qris_image_url': (
            merchant.qris_image.url
            if merchant and merchant.qris_image
            else None
        ),
    }
```

- [ ] **Step 4: Run tests (expect pass)**

```
python manage.py test apps.pos_config.tests.test_utils -v 2
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/pos_config/utils.py apps/pos_config/tests/test_utils.py
git commit -m "feat(pos_config): add resolve_pos_config cascade utility"
```

---

### Task 4: OutletPOSConfig form + view + URL

**Files:**
- Modify: `apps/pos_config/forms.py`
- Modify: `apps/pos_config/views.py`
- Modify: `apps/pos_config/urls.py`

- [ ] **Step 1: Add OutletPOSConfigForm to forms.py**

Append to `apps/pos_config/forms.py`:
```python
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, OutletPOSConfig


class OutletPOSConfigForm(forms.ModelForm):
    class Meta:
        model = OutletPOSConfig
        fields = [
            'sub_transaction_type',
            'revenue_account',
            'offset_coa_account',
            'default_payment_account',
            'tax_pct',
            'is_active',
        ]
        widgets = {
            'sub_transaction_type': forms.Select(attrs=NI_INPUT_ATTRS),
            'revenue_account': forms.Select(attrs=NI_INPUT_ATTRS),
            'offset_coa_account': forms.Select(attrs=NI_INPUT_ATTRS),
            'default_payment_account': forms.Select(attrs=NI_INPUT_ATTRS),
            'tax_pct': forms.NumberInput(attrs={**NI_INPUT_ATTRS, 'step': '0.01', 'placeholder': 'Kosong = ikut parent'}),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
        }
```

- [ ] **Step 2: Add outlet_config view to pos_config/views.py**

Add import at top of `apps/pos_config/views.py`:
```python
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog, OutletPOSConfig
from .forms import MerchantPOSConfigForm, StorePOSConfigForm, PaymentMethodForm, WorkShiftForm, OutletPOSConfigForm
from .utils import resolve_pos_config
```

Append view function:
```python
@login_required
def outlet_config(request, lv3_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    lv3 = get_object_or_404(
        EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
        ),
        pk=lv3_pk,
    )
    merchant = getattr(lv3.parent_lv2.entitas_bisnis, 'pos_config', None)
    if not merchant:
        messages.warning(request, 'Merchant POS Config belum diset di level 1. Set di halaman Entitas Bisnis Level 1 terlebih dahulu.')
        return redirect('entitas_bisnis:lv3_update', pk=lv3.parent_lv2.pk, lv3_pk=lv3_pk)

    cfg, _ = OutletPOSConfig.objects.get_or_create(
        entitas_bisnis_lv3=lv3,
        defaults={'merchant_config': merchant},
    )
    effective = resolve_pos_config(
        EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=lv3_pk)
    )
    if request.method == 'POST':
        form = OutletPOSConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, f'Outlet POS Config untuk {lv3.nama} disimpan.')
            return redirect('pos_config:outlet_config', lv3_pk=lv3_pk)
    else:
        form = OutletPOSConfigForm(instance=cfg)
    return render(request, 'pos_config/outlet_config_form.html', {
        'form': form,
        'lv3': lv3,
        'cfg': cfg,
        'effective': effective,
    })
```

- [ ] **Step 3: Add URL**

In `apps/pos_config/urls.py`, add:
```python
path('outlet/<int:lv3_pk>/', views.outlet_config, name='outlet_config'),
```

- [ ] **Step 4: Create template `templates/pos_config/outlet_config_form.html`**

```html
{% extends 'base.html' %}
{% block title %}Outlet POS Config — {{ lv3.nama }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Outlet POS Config</h1>
    <p class="ni-page-header__subtitle">{{ lv3.nama }} · {{ lv3.parent_lv2.nama }}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="javascript:history.back()" class="ni-btn ni-btn--secondary">Kembali</a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:24px;">
  <div class="ni-card__header"><h3>Nilai Efektif (setelah cascade)</h3></div>
  <div class="ni-card__body">
    <dl class="ni-detail-grid">
      <dt>Sub-Transaction Type</dt><dd>{{ effective.sub_transaction_type_id|default:'—' }}</dd>
      <dt>Tax %</dt><dd>{{ effective.tax_pct }}%</dd>
      <dt>Revenue Account</dt><dd>{{ effective.revenue_account_id|default:'—' }}</dd>
      <dt>HPP Account</dt><dd>{{ effective.offset_coa_account_id|default:'—' }}</dd>
      <dt>Payment Account</dt><dd>{{ effective.payment_account_id|default:'—' }}</dd>
    </dl>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h3>Override untuk {{ lv3.nama }}</h3></div>
  <div class="ni-card__body">
    <form method="post">
      {% csrf_token %}
      <div class="ni-form-grid">
        {% for field in form %}
        <div class="ni-form-group">
          <label class="ni-label">{{ field.label }}</label>
          {{ field }}
          {% if field.help_text %}<small class="ni-help-text">{{ field.help_text }}</small>{% endif %}
          {% for err in field.errors %}<span class="ni-error">{{ err }}</span>{% endfor %}
        </div>
        {% endfor %}
      </div>
      <div style="margin-top:20px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Verify in browser**

```
python manage.py runserver
```
Navigate to `/pos/outlet/<lv3_pk>/` — verify form renders with effective values section.

- [ ] **Step 6: Commit**

```bash
git add apps/pos_config/forms.py apps/pos_config/views.py apps/pos_config/urls.py templates/pos_config/outlet_config_form.html
git commit -m "feat(pos_config): add OutletPOSConfig form, view, URL"
```
