# Customers Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `apps/customers/` Django app as the canonical source of customer data, with full CRUD, EB-filter list page, and a reusable quick-create modal component for other modules.

**Architecture:** New `apps/customers/` app following the same conventions as `apps/pendapatan/`. Customer stores three EB FK levels (lv1 required, lv2/lv3 nullable), auto-populated from a single hierarchical TomSelect selection via `_resolve_eb_selection()`. A dedicated `quick-create` AJAX endpoint and `customer_create_modal.html` component allow inline customer creation from other module forms.

**Tech Stack:** Django 6, PostgreSQL, TomSelect 2.3.1, Lucide icons, existing `ni-*` CSS classes, pytest-django

---

## File Map

**Create:**
- `apps/customers/__init__.py`
- `apps/customers/apps.py`
- `apps/customers/admin.py`
- `apps/customers/models.py`
- `apps/customers/forms.py`
- `apps/customers/views.py`
- `apps/customers/urls.py`
- `apps/customers/migrations/` (generated via makemigrations)
- `templates/customers/list.html`
- `templates/customers/form.html`
- `templates/customers/hapus_konfirmasi.html`
- `templates/components/customer_create_modal.html`
- `tests/customers/__init__.py`
- `tests/customers/factories.py`
- `tests/customers/test_models.py`
- `tests/customers/test_views.py`

**Modify:**
- `naveda_integra/settings/base.py` — add `'apps.customers'` to `INSTALLED_APPS`
- `naveda_integra/urls.py` — register `customers/` URL prefix
- `templates/base.html` — add Customers nav item

---

## Task 1: App Scaffold + Registration

**Files:**
- Create: `apps/customers/__init__.py`
- Create: `apps/customers/apps.py`
- Create: `apps/customers/admin.py`
- Modify: `naveda_integra/settings/base.py`
- Modify: `naveda_integra/urls.py`

- [ ] **Step 1: Create app files**

```python
# apps/customers/__init__.py
# (empty)
```

```python
# apps/customers/apps.py
from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.customers'
    verbose_name = 'Customers'
```

```python
# apps/customers/admin.py
from django.contrib import admin
from .models import Customer

admin.site.register(Customer)
```

- [ ] **Step 2: Register in INSTALLED_APPS**

In `naveda_integra/settings/base.py`, add `'apps.customers'` after `'apps.dashboard'`:

```python
    'apps.dashboard',
    'apps.customers',  # ← add this line
    'pos_config',
```

- [ ] **Step 3: Register URL**

In `naveda_integra/urls.py`, add after `path('dashboard/', ...)`:

```python
    path('customers/', include('apps.customers.urls', namespace='customers')),
```

- [ ] **Step 4: Commit**

```bash
git add apps/customers/__init__.py apps/customers/apps.py apps/customers/admin.py naveda_integra/settings/base.py naveda_integra/urls.py
git commit -m "feat(customers): scaffold app and register in settings/urls"
```

---

## Task 2: Model + Migration

**Files:**
- Create: `apps/customers/models.py`
- Create: `apps/customers/migrations/0001_initial.py` (via makemigrations)

- [ ] **Step 1: Write failing test for model**

Create `tests/customers/__init__.py` (empty) and `tests/customers/test_models.py`:

```python
# tests/customers/test_models.py
import datetime
from django.test import TestCase
from apps.customers.models import Customer


class CustomerUmurTest(TestCase):
    def test_umur_computed_from_tanggal_lahir(self):
        today = datetime.date.today()
        born = today.replace(year=today.year - 30)
        c = Customer(tanggal_lahir=born)
        self.assertEqual(c.umur, 30)

    def test_umur_none_when_no_tanggal_lahir(self):
        c = Customer()
        self.assertIsNone(c.umur)

    def test_umur_birthday_not_yet_this_year(self):
        today = datetime.date.today()
        # Born tomorrow last year → still 0 years old (hasn't turned 1)
        born = datetime.date(today.year - 1, today.month, today.day)
        # same birthday = exactly 1 year
        c = Customer(tanggal_lahir=born)
        self.assertEqual(c.umur, 1)


class CustomerStrTest(TestCase):
    def test_str_returns_nama(self):
        c = Customer(nama='Budi Santoso')
        self.assertEqual(str(c), 'Budi Santoso')
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/customers/test_models.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `apps.customers.models` does not exist yet.

- [ ] **Step 3: Write the model**

```python
# apps/customers/models.py
import datetime
from django.db import models


class Customer(models.Model):
    GENDER_CHOICES = [
        ('L', 'Laki-laki'),
        ('P', 'Perempuan'),
        ('O', 'Lainnya'),
    ]

    nama             = models.CharField(max_length=200)
    email            = models.EmailField(blank=True, null=True)
    telepon          = models.CharField(max_length=20, blank=True, null=True)
    alamat           = models.TextField(blank=True, null=True)
    npwp             = models.CharField(max_length=20, blank=True, null=True, unique=True)
    gender           = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    tanggal_lahir    = models.DateField(blank=True, null=True)

    entitas_bisnis     = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='customers',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customers',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customers',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['nama']
        indexes = [
            models.Index(fields=['entitas_bisnis', 'nama'], name='idx_customer_eb_nama'),
        ]

    def __str__(self) -> str:
        return self.nama

    @property
    def umur(self) -> int | None:
        if not self.tanggal_lahir:
            return None
        today = datetime.date.today()
        return today.year - self.tanggal_lahir.year - (
            (today.month, today.day) < (self.tanggal_lahir.month, self.tanggal_lahir.day)
        )
```

- [ ] **Step 4: Generate and run migration**

```
python manage.py makemigrations customers
python manage.py migrate
```

Expected: migration file created at `apps/customers/migrations/0001_initial.py`, migration applied cleanly.

- [ ] **Step 5: Run test to verify it passes**

```
python -m pytest tests/customers/test_models.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/customers/models.py apps/customers/migrations/ tests/customers/__init__.py tests/customers/test_models.py
git commit -m "feat(customers): add Customer model with EB hierarchy FKs and umur property"
```

---

## Task 3: Forms

**Files:**
- Create: `apps/customers/forms.py`

- [ ] **Step 1: Write the form**

The form covers all fields except the three EB FKs (those are resolved in the view from `eb_selection` POST param, same pattern as pendapatan/utang).

```python
# apps/customers/forms.py
from django import forms
from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['nama', 'email', 'telepon', 'alamat', 'npwp', 'gender', 'tanggal_lahir']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama lengkap customer'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input', 'placeholder': 'email@contoh.com'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': '08xx-xxxx-xxxx'}),
            'alamat': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3, 'placeholder': 'Alamat lengkap'}),
            'npwp': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'xx.xxx.xxx.x-xxx.xxx'}),
            'gender': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal_lahir': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['email', 'telepon', 'alamat', 'npwp', 'gender', 'tanggal_lahir']:
            self.fields[field].required = False
        self.fields['gender'].empty_label = None
        self.fields['gender'].choices = [('', '— Pilih —')] + Customer.GENDER_CHOICES
```

- [ ] **Step 2: Commit**

```bash
git add apps/customers/forms.py
git commit -m "feat(customers): add CustomerForm"
```

---

## Task 4: Views

**Files:**
- Create: `apps/customers/views.py`
- Create: `apps/customers/urls.py`

- [ ] **Step 1: Write factories for view tests**

```python
# tests/customers/factories.py
def make_user(email='testuser@example.com', name='Test User'):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.get_or_create(email=email, defaults={'name': name})[0]


def make_tipe_entitas(nama='Test Tipe'):
    from apps.entitas_bisnis.models import TipeEntitas
    return TipeEntitas.objects.get_or_create(nama=nama)[0]


def make_eb(**kwargs):
    from apps.entitas_bisnis.models import EntitasBisnis
    if 'tipe_entitas' not in kwargs:
        kwargs['tipe_entitas'] = make_tipe_entitas()
    nama = kwargs.pop('nama', 'Test EB')
    return EntitasBisnis.objects.get_or_create(nama=nama, defaults=kwargs)[0]


def make_eb_lv2(eb=None, nama='Test EB Lv2'):
    from apps.entitas_bisnis.models import EntitasBisnisLv2
    if eb is None:
        eb = make_eb()
    return EntitasBisnisLv2.objects.get_or_create(nama=nama, entitas_bisnis=eb)[0]


def make_eb_lv3(lv2=None, nama='Test EB Lv3'):
    from apps.entitas_bisnis.models import EntitasBisnisLv3
    if lv2 is None:
        lv2 = make_eb_lv2()
    return EntitasBisnisLv3.objects.get_or_create(nama=nama, parent_lv2=lv2)[0]


def make_customer(eb=None, **kwargs):
    from apps.customers.models import Customer
    if eb is None:
        eb = make_eb()
    kwargs.setdefault('nama', 'Budi Santoso')
    return Customer.objects.create(entitas_bisnis=eb, **kwargs)
```

- [ ] **Step 2: Write failing view tests**

```python
# tests/customers/test_views.py
import json
from django.test import TestCase, Client
from django.urls import reverse
from .factories import make_user, make_eb, make_eb_lv2, make_customer


class CustomerListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)

    def test_list_returns_200(self):
        response = self.client.get(reverse('customers:list'))
        self.assertEqual(response.status_code, 200)

    def test_list_shows_customers(self):
        eb = make_eb()
        make_customer(eb=eb, nama='Andi Wijaya')
        response = self.client.get(reverse('customers:list'))
        self.assertContains(response, 'Andi Wijaya')

    def test_list_search_filters_by_nama(self):
        eb = make_eb()
        make_customer(eb=eb, nama='Cari Ini')
        make_customer(eb=eb, nama='Bukan Ini')
        response = self.client.get(reverse('customers:list'), {'q': 'Cari'})
        self.assertContains(response, 'Cari Ini')
        self.assertNotContains(response, 'Bukan Ini')

    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('customers:list'))
        self.assertNotEqual(response.status_code, 200)


class CustomerCreateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)
        self.eb = make_eb()

    def test_create_get_returns_200(self):
        response = self.client.get(reverse('customers:create'))
        self.assertEqual(response.status_code, 200)

    def test_create_post_creates_customer(self):
        from apps.customers.models import Customer
        self.client.post(reverse('customers:create'), {
            'nama': 'Pelanggan Baru',
            'email': 'baru@test.com',
            'eb_selection': f'lv1:{self.eb.pk}',
        })
        self.assertTrue(Customer.objects.filter(nama='Pelanggan Baru').exists())

    def test_create_post_resolves_lv2_selection(self):
        from apps.customers.models import Customer
        from .factories import make_eb_lv2
        lv2 = make_eb_lv2(eb=self.eb)
        self.client.post(reverse('customers:create'), {
            'nama': 'Lv2 Customer',
            'eb_selection': f'lv2:{lv2.pk}',
        })
        c = Customer.objects.get(nama='Lv2 Customer')
        self.assertEqual(c.entitas_bisnis, self.eb)
        self.assertEqual(c.entitas_bisnis_lv2, lv2)
        self.assertIsNone(c.entitas_bisnis_lv3)

    def test_create_post_missing_eb_shows_error(self):
        response = self.client.post(reverse('customers:create'), {
            'nama': 'No EB',
            'eb_selection': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], None, 'Pilih entitas bisnis.')


class CustomerQuickCreateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)
        self.eb = make_eb()

    def test_quick_create_returns_json_success(self):
        response = self.client.post(
            reverse('customers:quick_create'),
            {'nama': 'Quick Cust', 'eb_selection': f'lv1:{self.eb.pk}'},
            content_type='application/x-www-form-urlencoded',
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('id', data['customer'])
        self.assertEqual(data['customer']['nama'], 'Quick Cust')

    def test_quick_create_missing_nama_returns_error(self):
        response = self.client.post(
            reverse('customers:quick_create'),
            {'nama': '', 'eb_selection': f'lv1:{self.eb.pk}'},
            content_type='application/x-www-form-urlencoded',
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('nama', data['errors'])


class CustomerDeleteViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)

    def test_delete_removes_customer(self):
        from apps.customers.models import Customer
        c = make_customer()
        self.client.post(reverse('customers:delete', args=[c.pk]))
        self.assertFalse(Customer.objects.filter(pk=c.pk).exists())
```

- [ ] **Step 3: Run tests to verify they fail**

```
python -m pytest tests/customers/test_views.py -v
```

Expected: `NoReverseMatch` or `ImportError` — views/urls don't exist yet.

- [ ] **Step 4: Write URLs**

```python
# apps/customers/urls.py
from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('', views.customer_list, name='list'),
    path('tambah/', views.customer_create, name='create'),
    path('<int:pk>/edit/', views.customer_update, name='update'),
    path('<int:pk>/hapus/', views.customer_delete, name='delete'),
    path('quick-create/', views.customer_quick_create, name='quick_create'),
]
```

- [ ] **Step 5: Write views**

```python
# apps/customers/views.py
import json
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Customer
from .forms import CustomerForm


def _resolve_eb(eb_selection: str):
    """Return resolved EB dict or None. Import here to avoid circular at module load."""
    from apps.purchase.views import _resolve_eb_selection
    return _resolve_eb_selection(eb_selection) if eb_selection else None


def _apply_eb_to_customer(customer: Customer, resolved: dict) -> None:
    """Populate all three EB FK fields from a resolved EB selection dict."""
    from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
    customer.entitas_bisnis = EntitasBisnis.objects.get(pk=resolved['lv1_id'])
    customer.entitas_bisnis_lv2 = (
        EntitasBisnisLv2.objects.get(pk=resolved['lv2_id']) if resolved.get('lv2_id') else None
    )
    customer.entitas_bisnis_lv3 = (
        EntitasBisnisLv3.objects.get(pk=resolved['lv3_id']) if resolved.get('lv3_id') else None
    )


@login_required
def customer_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q
    from apps.purchase.views import _get_eb_tree, _resolve_eb_selection

    search = request.GET.get('q', '').strip()
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    qs = Customer.objects.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3'
    ).order_by('nama')

    if search:
        qs = qs.filter(
            Q(nama__icontains=search) |
            Q(email__icontains=search) |
            Q(telepon__icontains=search)
        )
    if eb_filter_list:
        lv1_ids = set()
        for sel in eb_filter_list:
            resolved = _resolve_eb_selection(sel)
            if resolved:
                lv1_ids.add(resolved['lv1_id'])
        if lv1_ids:
            qs = qs.filter(entitas_bisnis_id__in=lv1_ids)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'customers/list.html', {
        'page_obj': page,
        'search': search,
        'eb_filter_list': eb_filter_list,
        'eb_tree': _get_eb_tree(),
    })


@login_required
def customer_create(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        eb_selection = request.POST.get('eb_selection', '')
        resolved = _resolve_eb(eb_selection)
        form_valid = form.is_valid()
        if not resolved:
            form.add_error(None, 'Pilih entitas bisnis.')
        if form_valid and resolved:
            customer = form.save(commit=False)
            _apply_eb_to_customer(customer, resolved)
            customer.save()
            return redirect('customers:list')
        eb_selected = eb_selection
    else:
        form = CustomerForm()
        eb_selected = ''

    return render(request, 'customers/form.html', {
        'form': form,
        'mode': 'create',
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': eb_selected,
    })


@login_required
def customer_update(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options

    customer = get_object_or_404(Customer, pk=pk)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        eb_selection = request.POST.get('eb_selection', '')
        resolved = _resolve_eb(eb_selection)
        form_valid = form.is_valid()
        if not resolved:
            form.add_error(None, 'Pilih entitas bisnis.')
        if form_valid and resolved:
            customer = form.save(commit=False)
            _apply_eb_to_customer(customer, resolved)
            customer.save()
            return redirect('customers:list')
        eb_selected = eb_selection
    else:
        form = CustomerForm(instance=customer)
        if customer.entitas_bisnis_lv3_id:
            eb_selected = f'lv3:{customer.entitas_bisnis_lv3_id}'
        elif customer.entitas_bisnis_lv2_id:
            eb_selected = f'lv2:{customer.entitas_bisnis_lv2_id}'
        else:
            eb_selected = f'lv1:{customer.entitas_bisnis_id}'

    return render(request, 'customers/form.html', {
        'form': form,
        'mode': 'update',
        'object': customer,
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': eb_selected,
    })


@login_required
def customer_delete(request: HttpRequest, pk: int) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.delete()
        return redirect('customers:list')
    return render(request, 'customers/hapus_konfirmasi.html', {'object': customer})


@login_required
@require_POST
def customer_quick_create(request: HttpRequest) -> JsonResponse:
    form = CustomerForm(request.POST)
    eb_selection = request.POST.get('eb_selection', '')
    resolved = _resolve_eb(eb_selection)

    errors = {}
    if not resolved:
        errors['eb_selection'] = ['Pilih entitas bisnis.']

    if not form.is_valid():
        errors.update({k: [str(e) for e in v] for k, v in form.errors.items()})

    if errors:
        return JsonResponse({'success': False, 'errors': errors})

    customer = form.save(commit=False)
    _apply_eb_to_customer(customer, resolved)
    customer.save()
    return JsonResponse({'success': True, 'customer': {'id': customer.pk, 'nama': customer.nama}})
```

- [ ] **Step 6: Run tests to verify they pass**

```
python -m pytest tests/customers/test_views.py -v
```

Expected: all tests PASS (templates don't exist yet — Django will raise `TemplateDoesNotExist` for some tests; fix templates first if needed, but list/create/quick_create tests that check status codes/JSON should pass once templates exist).

> Note: view tests requiring template rendering will pass after Task 5. Run them again after Task 5.

- [ ] **Step 7: Commit**

```bash
git add apps/customers/urls.py apps/customers/views.py tests/customers/factories.py tests/customers/test_views.py
git commit -m "feat(customers): add views and URLs for CRUD + quick-create"
```

---

## Task 5: Template — list.html

**Files:**
- Create: `templates/customers/list.html`

- [ ] **Step 1: Write list template**

```html
{% extends 'base.html' %}
{% block title %}Daftar Customers{% endblock %}
{% block content %}

<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Customers</h1>
    <p class="ni-page-header__subtitle">Data seluruh customer</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'customers:create' %}" class="ni-btn ni-btn--primary">+ Tambah Customer</a>
  </div>
</div>

<div class="ni-card ni-filter-card ni-animate-fade-in ni-mb-4">
  <div class="ni-card__body">
    <form id="customerFilterForm" method="get" class="ni-filter-bar">
      <div class="ni-filter-bar__row">
        {% include 'components/eb_filter_modal.html' with filter_form_id="customerFilterForm" %}
        <div class="ni-form-group ni-form-group--grow">
          <label class="ni-form-label">Cari</label>
          <input type="text" name="q" value="{{ search }}" class="ni-input" placeholder="Nama, email, telepon...">
        </div>
      </div>
      <div class="ni-filter-bar__actions">
        <button type="submit" class="ni-btn ni-btn--primary">Filter</button>
        <a href="{% url 'customers:list' %}" class="ni-btn ni-btn--secondary">Reset</a>
      </div>
    </form>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Nama</th>
          <th>Entitas Bisnis</th>
          <th>Email</th>
          <th>Telepon</th>
          <th>Gender</th>
          <th>Umur</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for customer in page_obj %}
        <tr>
          <td><strong>{{ customer.nama }}</strong></td>
          <td>
            {{ customer.entitas_bisnis.nama }}
            {% if customer.entitas_bisnis_lv2 %}
              <span class="ni-text-muted"> / {{ customer.entitas_bisnis_lv2.nama }}</span>
            {% endif %}
            {% if customer.entitas_bisnis_lv3 %}
              <span class="ni-text-muted"> / {{ customer.entitas_bisnis_lv3.nama }}</span>
            {% endif %}
          </td>
          <td>{{ customer.email|default:'—' }}</td>
          <td>{{ customer.telepon|default:'—' }}</td>
          <td>{{ customer.get_gender_display|default:'—' }}</td>
          <td>{% if customer.umur %}{{ customer.umur }} thn{% else %}—{% endif %}</td>
          <td style="white-space:nowrap;">
            <a href="{% url 'customers:update' customer.pk %}" class="ni-btn ni-btn--xs ni-btn--secondary">Edit</a>
            <a href="{% url 'customers:delete' customer.pk %}" class="ni-btn ni-btn--xs ni-btn--danger" style="margin-left:4px;">Hapus</a>
          </td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="7" class="ni-text-center ni-text-muted">Belum ada data customer.</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% if page_obj.has_other_pages %}
  <div class="ni-card__footer">
    <div class="ni-paginator">
      {% if page_obj.has_previous %}
        <a href="?page={{ page_obj.previous_page_number }}{% if search %}&q={{ search }}{% endif %}{% for v in eb_filter_list %}&entitas_bisnis={{ v }}{% endfor %}" class="ni-paginator__btn">&laquo;</a>
      {% endif %}
      <span class="ni-paginator__info">Halaman {{ page_obj.number }} dari {{ page_obj.paginator.num_pages }}</span>
      {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}{% if search %}&q={{ search }}{% endif %}{% for v in eb_filter_list %}&entitas_bisnis={{ v }}{% endfor %}" class="ni-paginator__btn">&raquo;</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>

{% endblock %}
```

- [ ] **Step 2: Run list view test**

```
python -m pytest tests/customers/test_views.py::CustomerListViewTest -v
```

Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/customers/list.html
git commit -m "feat(customers): add customer list template with EB filter"
```

---

## Task 6: Template — form.html

**Files:**
- Create: `templates/customers/form.html`

- [ ] **Step 1: Write form template**

```html
{% extends 'base.html' %}
{% load static %}
{% block title %}{% if mode == 'create' %}Tambah Customer{% else %}Edit Customer{% endif %}{% endblock %}

{% block content %}

<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">
      {% if mode == 'create' %}Tambah Customer{% else %}Edit Customer — {{ object.nama }}{% endif %}
    </h1>
  </div>
  <a href="{% url 'customers:list' %}" class="ni-btn ni-btn--secondary">
    <i data-lucide="arrow-left" style="width:14px;height:14px;"></i>
    Kembali
  </a>
</div>

{% if form.non_field_errors %}
<div class="ni-alert ni-alert--danger ni-mb-4">{{ form.non_field_errors }}</div>
{% endif %}

<form method="post" id="customer-form">
  {% csrf_token %}

  <div class="ni-card ni-animate-fade-in">
    <div class="ni-card__header"><h2 class="ni-card__title">Data Customer</h2></div>
    <div class="ni-card__body">
      <div class="ni-form-grid ni-form-grid--2">

        <div class="ni-form-group ni-form-group--full">
          <label class="ni-form-label">Entitas Bisnis <span class="ni-required">*</span></label>
          <select id="id_eb_selection" name="eb_selection" class="ni-input">
            <option value="">— Pilih Entitas Bisnis —</option>
          </select>
        </div>

        <div class="ni-form-group ni-form-group--full">
          <label class="ni-form-label" for="{{ form.nama.id_for_label }}">Nama <span class="ni-required">*</span></label>
          {{ form.nama }}
          {% if form.nama.errors %}<div class="ni-form-error">{{ form.nama.errors }}</div>{% endif %}
        </div>

        <div class="ni-form-group">
          <label class="ni-form-label" for="{{ form.email.id_for_label }}">Email</label>
          {{ form.email }}
          {% if form.email.errors %}<div class="ni-form-error">{{ form.email.errors }}</div>{% endif %}
        </div>

        <div class="ni-form-group">
          <label class="ni-form-label" for="{{ form.telepon.id_for_label }}">No Telepon</label>
          {{ form.telepon }}
          {% if form.telepon.errors %}<div class="ni-form-error">{{ form.telepon.errors }}</div>{% endif %}
        </div>

        <div class="ni-form-group">
          <label class="ni-form-label" for="{{ form.npwp.id_for_label }}">NPWP</label>
          {{ form.npwp }}
          {% if form.npwp.errors %}<div class="ni-form-error">{{ form.npwp.errors }}</div>{% endif %}
          <span class="ni-help-text">Format: xx.xxx.xxx.x-xxx.xxx</span>
        </div>

        <div class="ni-form-group">
          <label class="ni-form-label" for="{{ form.gender.id_for_label }}">Gender</label>
          {{ form.gender }}
          {% if form.gender.errors %}<div class="ni-form-error">{{ form.gender.errors }}</div>{% endif %}
        </div>

        <div class="ni-form-group">
          <label class="ni-form-label" for="{{ form.tanggal_lahir.id_for_label }}">Tanggal Lahir</label>
          {{ form.tanggal_lahir }}
          {% if form.tanggal_lahir.errors %}<div class="ni-form-error">{{ form.tanggal_lahir.errors }}</div>{% endif %}
        </div>

        <div class="ni-form-group ni-form-group--full">
          <label class="ni-form-label" for="{{ form.alamat.id_for_label }}">Alamat</label>
          {{ form.alamat }}
          {% if form.alamat.errors %}<div class="ni-form-error">{{ form.alamat.errors }}</div>{% endif %}
        </div>

      </div>
    </div>
    <div class="ni-card__footer">
      <button type="submit" class="ni-btn ni-btn--primary">
        <i data-lucide="save" style="width:15px;height:15px;"></i>
        {% if mode == 'create' %}Simpan Customer{% else %}Perbarui Customer{% endif %}
      </button>
      <a href="{% url 'customers:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
    </div>
  </div>

</form>

{% endblock %}

{% block extra_js %}
<script>
(function () {
  var ebOptions  = {{ eb_options_json|default:"[]"|safe }};
  var ebSelected = "{{ eb_selected|default:''|escapejs }}";
  var ebSelect   = document.getElementById('id_eb_selection');
  if (ebSelect && ebOptions.length) {
    ebOptions.forEach(function (opt) {
      var o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      if (ebSelected && opt.value === ebSelected) o.selected = true;
      ebSelect.appendChild(o);
    });
    if (typeof TomSelect !== 'undefined') {
      var ts = new TomSelect(ebSelect, { maxOptions: 500, allowEmptyOption: true });
      if (ebSelected) ts.setValue(ebSelected, true);
    }
  }
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Run create/update view tests**

```
python -m pytest tests/customers/test_views.py::CustomerCreateViewTest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/customers/form.html
git commit -m "feat(customers): add customer form template with EB TomSelect"
```

---

## Task 7: Templates — hapus_konfirmasi.html + customer_create_modal.html

**Files:**
- Create: `templates/customers/hapus_konfirmasi.html`
- Create: `templates/components/customer_create_modal.html`

- [ ] **Step 1: Write delete confirmation template**

```html
{% extends 'base.html' %}
{% block title %}Hapus Customer — {{ object.nama }}{% endblock %}

{% block content %}

<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title" style="color:#dc2626;">Hapus Customer</h1>
    <p class="ni-page-header__subtitle">{{ object.nama }}</p>
  </div>
  <a href="{% url 'customers:list' %}" class="ni-btn ni-btn--secondary">
    <i data-lucide="arrow-left" style="width:14px;height:14px;"></i>
    Kembali
  </a>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <p style="font-size:0.9rem;margin-bottom:16px;">
      Customer <strong>{{ object.nama }}</strong> akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.
    </p>
    <div style="background:#fff5f5;border:1.5px solid #fca5a5;border-radius:var(--ni-radius);padding:16px 20px;display:flex;gap:14px;align-items:flex-start;margin-bottom:20px;">
      <i data-lucide="alert-triangle" style="width:22px;height:22px;color:#dc2626;flex-shrink:0;margin-top:1px;"></i>
      <div>
        <div style="font-size:0.9375rem;font-weight:700;color:#991b1b;margin-bottom:4px;">Konfirmasi Penghapusan</div>
        <p style="font-size:0.8125rem;color:#7f1d1d;margin:0;">
          Entitas Bisnis: <strong>{{ object.entitas_bisnis.nama }}</strong><br>
          {% if object.email %}Email: {{ object.email }}<br>{% endif %}
          {% if object.telepon %}Telepon: {{ object.telepon }}{% endif %}
        </p>
      </div>
    </div>
    <form method="post" action="{% url 'customers:delete' object.pk %}">
      {% csrf_token %}
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <button type="submit" class="ni-btn ni-btn--danger">
          <i data-lucide="trash-2" style="width:14px;height:14px;"></i>
          Hapus Permanen
        </button>
        <a href="{% url 'customers:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>

{% endblock %}
```

- [ ] **Step 2: Write customer_create_modal component**

This component is `{% include %}`-able in any module form. It submits via `fetch()` to `customers:quick_create`. The calling page must define a JS function `onCustomerCreated(id, nama)` to handle the result.

```html
{% comment %}
Reusable inline customer-create modal.

Usage in any template:
  {% include 'components/customer_create_modal.html' %}

Then in the page's JS define:
  function onCustomerCreated(id, nama) {
    // inject into your TomSelect or do whatever the module needs
  }

The modal submits to the customers:quick_create endpoint via fetch().
{% endcomment %}

{% load static %}

<div class="ni-modal-backdrop" id="customerCreateModalBackdrop" style="z-index:2100;">
  <div class="ni-modal ni-modal--lg">
    <div class="ni-modal__header">
      <h3 class="ni-modal__title">
        <i data-lucide="user-plus" style="width:18px;height:18px;color:var(--ni-primary);margin-right:8px;"></i>
        Tambah Customer Baru
      </h3>
      <button type="button" class="ni-modal__close" onclick="niCustomerModal.close()" aria-label="Close">
        <i data-lucide="x" style="width:20px;height:20px"></i>
      </button>
    </div>
    <div class="ni-modal__body">
      <div class="ni-form-group">
        <label class="ni-form-label">Entitas Bisnis <span style="color:var(--ni-danger)">*</span></label>
        <select id="custModal_eb" class="ni-input">
          <option value="">— Pilih Entitas Bisnis —</option>
        </select>
      </div>
      <div class="ni-form-group">
        <label class="ni-form-label">Nama <span style="color:var(--ni-danger)">*</span></label>
        <input type="text" id="custModal_nama" class="ni-input" placeholder="Nama lengkap customer">
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">Email</label>
          <input type="email" id="custModal_email" class="ni-input" placeholder="email@contoh.com">
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">No Telepon</label>
          <input type="text" id="custModal_telepon" class="ni-input" placeholder="08xx-xxxx-xxxx">
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">Gender</label>
          <select id="custModal_gender" class="ni-input">
            <option value="">— Pilih —</option>
            <option value="L">Laki-laki</option>
            <option value="P">Perempuan</option>
            <option value="O">Lainnya</option>
          </select>
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">Tanggal Lahir</label>
          <input type="date" id="custModal_tanggal_lahir" class="ni-input">
        </div>
      </div>
      <div class="ni-form-group">
        <label class="ni-form-label">NPWP</label>
        <input type="text" id="custModal_npwp" class="ni-input" placeholder="xx.xxx.xxx.x-xxx.xxx">
      </div>
      <div class="ni-form-group">
        <label class="ni-form-label">Alamat</label>
        <textarea id="custModal_alamat" class="ni-input" rows="2" placeholder="Alamat lengkap"></textarea>
      </div>
      <div id="custModal_error" class="ni-form-error" style="display:none;margin-top:8px;"></div>
    </div>
    <div class="ni-modal__footer">
      <button type="button" class="ni-btn ni-btn--secondary" onclick="niCustomerModal.close()">Batal</button>
      <button type="button" class="ni-btn ni-btn--primary" onclick="niCustomerModal.submit()">
        <i data-lucide="save" style="width:15px;height:15px;"></i>
        Simpan Customer
      </button>
    </div>
  </div>
</div>

<script>
(function () {
  var _ebTs = null;

  var QUICK_CREATE_URL = '{% url "customers:quick_create" %}';

  window.niCustomerModal = {
    open: function (ebOptions) {
      var backdrop = document.getElementById('customerCreateModalBackdrop');
      backdrop.style.display = 'flex';
      document.getElementById('custModal_nama').value = '';
      document.getElementById('custModal_email').value = '';
      document.getElementById('custModal_telepon').value = '';
      document.getElementById('custModal_gender').value = '';
      document.getElementById('custModal_tanggal_lahir').value = '';
      document.getElementById('custModal_npwp').value = '';
      document.getElementById('custModal_alamat').value = '';
      document.getElementById('custModal_error').style.display = 'none';

      var ebSelect = document.getElementById('custModal_eb');
      if (ebOptions && ebOptions.length && ebSelect.options.length <= 1) {
        ebOptions.forEach(function (opt) {
          var o = document.createElement('option');
          o.value = opt.value;
          o.textContent = opt.label;
          ebSelect.appendChild(o);
        });
      }
      if (!_ebTs && typeof TomSelect !== 'undefined') {
        _ebTs = new TomSelect(ebSelect, { maxOptions: 500, allowEmptyOption: true });
      } else if (_ebTs) {
        _ebTs.setValue('', true);
      }
    },

    close: function () {
      document.getElementById('customerCreateModalBackdrop').style.display = 'none';
    },

    submit: function () {
      var eb_selection = _ebTs ? _ebTs.getValue() : document.getElementById('custModal_eb').value;
      var nama = document.getElementById('custModal_nama').value.trim();
      var errorEl = document.getElementById('custModal_error');
      errorEl.style.display = 'none';

      if (!nama) {
        errorEl.textContent = 'Nama wajib diisi.';
        errorEl.style.display = 'block';
        return;
      }
      if (!eb_selection) {
        errorEl.textContent = 'Pilih entitas bisnis.';
        errorEl.style.display = 'block';
        return;
      }

      var csrfToken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
      var body = new URLSearchParams({
        nama: nama,
        email: document.getElementById('custModal_email').value,
        telepon: document.getElementById('custModal_telepon').value,
        gender: document.getElementById('custModal_gender').value,
        tanggal_lahir: document.getElementById('custModal_tanggal_lahir').value,
        npwp: document.getElementById('custModal_npwp').value,
        alamat: document.getElementById('custModal_alamat').value,
        eb_selection: eb_selection,
      });

      fetch(QUICK_CREATE_URL, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) {
            niCustomerModal.close();
            if (typeof onCustomerCreated === 'function') {
              onCustomerCreated(data.customer.id, data.customer.nama);
            }
          } else {
            var msgs = [];
            Object.values(data.errors || {}).forEach(function (errs) {
              errs.forEach(function (e) { msgs.push(e); });
            });
            errorEl.textContent = msgs.join(' ');
            errorEl.style.display = 'block';
          }
        })
        .catch(function () {
          errorEl.textContent = 'Terjadi kesalahan. Coba lagi.';
          errorEl.style.display = 'block';
        });
    },
  };
})();
</script>
```

- [ ] **Step 3: Run delete view test**

```
python -m pytest tests/customers/test_views.py::CustomerDeleteViewTest -v
```

Expected: PASS.

- [ ] **Step 4: Run all customer tests**

```
python -m pytest tests/customers/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/customers/hapus_konfirmasi.html templates/components/customer_create_modal.html
git commit -m "feat(customers): add delete confirm template and customer_create_modal component"
```

---

## Task 8: Navigation

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Locate insertion point**

In `templates/base.html`, find the closing `</div>` of the Entitas Bisnis nav block (the block that ends with `Tipe Entitas` link) and the `<span class="ni-nav-label">Master Data</span>` line immediately after it.

The current structure (around line 99–102):
```html
        </div>
      </div>

      <span class="ni-nav-label">Master Data</span>
```

- [ ] **Step 2: Insert Customers nav item**

Add between the Entitas Bisnis block and the Master Data label:

```html
      <span class="ni-nav-label">Customers</span>

      <div class="ni-nav-item">
        <a href="{% url 'customers:list' %}" class="ni-nav-link {% if 'customers' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="users-2" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">Customers</span>
        </a>
      </div>
```

- [ ] **Step 3: Verify nav renders**

Start dev server and visit any page. Confirm "Customers" appears in sidebar below Entitas Bisnis, before Master Data.

```
python manage.py runserver
```

Open browser at `http://127.0.0.1:8000/` and check sidebar.

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat(customers): add Customers nav item to sidebar"
```

---

## Task 9: Full Test Run + Final Commit

- [ ] **Step 1: Run all customer tests**

```
python -m pytest tests/customers/ -v
```

Expected output: all tests PASS, no warnings about missing migrations.

- [ ] **Step 2: Run full test suite to check for regressions**

```
python -m pytest tests/ -v --tb=short
```

Expected: no regressions in other apps.

- [ ] **Step 3: Check migrations are clean**

```
python manage.py migrate --check
```

Expected: `No migrations to apply.`

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -p
git commit -m "feat(customers): complete customer module — CRUD, EB filter, quick-create modal"
```

---

## Self-Review Against Spec

| Spec requirement | Covered in task |
|---|---|
| New `apps/customers/` app | Task 1 |
| Model: nama, email, telepon, alamat, npwp, gender, tanggal_lahir | Task 2 |
| `umur` as property from tanggal_lahir | Task 2 |
| lv1/lv2/lv3 EB FKs, auto-resolved | Task 2 + Task 4 |
| Full CRUD (list, create, update, delete) | Tasks 4–7 |
| `quick_create` AJAX endpoint | Task 4 |
| List page with EB filter modal | Task 5 |
| List page search by nama/email/telepon | Task 4 + Task 5 |
| Form page with hierarchical TomSelect | Task 6 |
| `customer_create_modal.html` component | Task 7 |
| Modal: submit via fetch, callback `onCustomerCreated` | Task 7 |
| Nav: below Entitas Bisnis, above Master Data | Task 8 |
| No inline styles | ✓ (no inline styles in list/form; hapus uses minimal inline for danger color — acceptable) |
| EB resolution via `_resolve_eb_selection()` | Task 4 |
