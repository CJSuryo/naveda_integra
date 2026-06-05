# EB Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guided checklist-dashboard wizard at `/entitas-bisnis/<pk>/setup/` that walks an admin through configuring everything a new Entitas Bisnis needs to operate the Kasir system.

**Architecture:** Server-rendered checklist page — completion status computed live on every GET from DB queries, no stored wizard state. Items 1 & 2 (lv2/lv3) use existing AJAX modal infrastructure in-page; items 3–6 link out with `?next=` redirect. Entry point is a "Setup Wizard" button on the lv1 edit page.

**Tech Stack:** Django, Django TestCase, existing `niEB` AJAX JS, `ni-*` CSS classes.

---

## File Map

| File | Change |
|---|---|
| `apps/entitas_bisnis/views.py` | Add `_compute_wizard_checks()` + `setup_wizard()` view |
| `apps/entitas_bisnis/urls.py` | Register `<int:pk>/setup/` → `setup_wizard` |
| `apps/entitas_bisnis/tests/test_wizard.py` | New — wizard view + checks tests |
| `templates/entitas_bisnis/setup_wizard.html` | New — full wizard page |
| `templates/entitas_bisnis/form.html` | Add "Setup Wizard" button |
| `apps/pos_config/views.py` | Add `?next=` support to `merchant_config` |
| `apps/accounts/views.py` | Add `?next=` + `?eb=` support to `user_create` |
| `templates/accounts/user_form.html` | Thread `?next=` + `?eb=` through form action |

---

### Task 1: `_compute_wizard_checks` helper + `setup_wizard` view + URL

**Files:**
- Modify: `apps/entitas_bisnis/views.py`
- Modify: `apps/entitas_bisnis/urls.py`
- Create: `apps/entitas_bisnis/tests/test_wizard.py`

- [ ] **Step 1: Write failing tests**

Create `apps/entitas_bisnis/tests/test_wizard.py`:
```python
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from apps.entitas_bisnis.views import _compute_wizard_checks


class ComputeWizardChecksTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda Kopi', tipe_entitas=tipe)

    def test_all_false_on_empty_eb(self):
        eb = EntitasBisnis.objects.select_related('pos_config').prefetch_related(
            'children_lv2__children_lv3'
        ).get(pk=self.eb.pk)
        checks = _compute_wizard_checks(eb)
        self.assertFalse(checks['lv2_ok'])
        self.assertFalse(checks['lv3_ok'])
        self.assertFalse(checks['pos_config_ok'])
        self.assertFalse(checks['stt_ok'])
        self.assertFalse(checks['users_ok'])
        self.assertFalse(checks['qris_ok'])
        self.assertFalse(checks['all_required_ok'])

    def test_lv2_ok_when_active_lv2_exists(self):
        EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Area A')
        eb = EntitasBisnis.objects.select_related('pos_config').prefetch_related(
            'children_lv2__children_lv3'
        ).get(pk=self.eb.pk)
        checks = _compute_wizard_checks(eb)
        self.assertTrue(checks['lv2_ok'])
        self.assertEqual(checks['lv2_count'], 1)

    def test_lv3_ok_when_active_lv3_exists(self):
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Area A')
        EntitasBisnisLv3.objects.create(parent_lv2=lv2, nama='Outlet X')
        eb = EntitasBisnis.objects.select_related('pos_config').prefetch_related(
            'children_lv2__children_lv3'
        ).get(pk=self.eb.pk)
        checks = _compute_wizard_checks(eb)
        self.assertTrue(checks['lv3_ok'])
        self.assertEqual(checks['lv3_count'], 1)

    def test_inactive_lv2_not_counted(self):
        EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Inactive', status_aktif=False)
        eb = EntitasBisnis.objects.select_related('pos_config').prefetch_related(
            'children_lv2__children_lv3'
        ).get(pk=self.eb.pk)
        checks = _compute_wizard_checks(eb)
        self.assertFalse(checks['lv2_ok'])


class SetupWizardViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda Kopi', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(
            email='admin@test.com', password='pass123', name='Admin'
        )
        self.client = Client()
        self.client.login(username='admin@test.com', password='pass123')

    def test_wizard_returns_200(self):
        resp = self.client.get(reverse('entitas_bisnis:setup_wizard', args=[self.eb.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_wizard_404_for_nonexistent_eb(self):
        resp = self.client.get(reverse('entitas_bisnis:setup_wizard', args=[99999]))
        self.assertEqual(resp.status_code, 404)

    def test_wizard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('entitas_bisnis:setup_wizard', args=[self.eb.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_checks_in_context(self):
        resp = self.client.get(reverse('entitas_bisnis:setup_wizard', args=[self.eb.pk]))
        self.assertIn('checks', resp.context)
        self.assertIn('eb', resp.context)
```

- [ ] **Step 2: Run tests (expect fail — view not defined)**

```
python manage.py test apps.entitas_bisnis.tests.test_wizard -v 2 --keepdb
```
Expected: `ImportError` or `AttributeError` — `_compute_wizard_checks` not found.

- [ ] **Step 3: Add `_compute_wizard_checks` and `setup_wizard` to views.py**

At the bottom of `apps/entitas_bisnis/views.py`, append:

```python
# ── Setup Wizard ──────────────────────────────────────────────────────────────

def _compute_wizard_checks(eb) -> dict:
    """Compute completion status for all wizard checklist items.

    eb must be fetched with select_related('pos_config') and
    prefetch_related('children_lv2__children_lv3').
    """
    from apps.entitas_bisnis.models import EntitasBisnisLv3
    from apps.pos_config.models import MerchantPOSConfig
    from apps.purchase.models import SubTransactionType
    from apps.accounts.models import UserEntitasBisnis

    lv2_list = [lv2 for lv2 in eb.children_lv2.all() if lv2.status_aktif]
    lv2_count = len(lv2_list)

    lv3_qs = EntitasBisnisLv3.objects.filter(
        parent_lv2__entitas_bisnis=eb, status_aktif=True
    )
    lv3_count = lv3_qs.count()

    pos_cfg = getattr(eb, 'pos_config', None)
    pos_config_ok = bool(
        pos_cfg and
        pos_cfg.sub_transaction_type_id and
        pos_cfg.revenue_account_id and
        pos_cfg.offset_coa_account_id and
        pos_cfg.default_payment_account_id
    )

    stt_exists = SubTransactionType.objects.filter(module='sales').exists()
    stt_assigned = bool(pos_cfg and pos_cfg.sub_transaction_type_id)
    stt_ok = stt_exists and stt_assigned

    users = list(
        UserEntitasBisnis.objects.filter(
            entitas_bisnis=eb, user__is_active=True
        ).select_related('user')
    )
    users_ok = len(users) > 0

    qris_ok = bool(pos_cfg and pos_cfg.qris_image)

    # Missing fields detail for POS Config card
    pos_missing = []
    if pos_cfg:
        if not pos_cfg.sub_transaction_type_id:
            pos_missing.append('Sub-Transaction Type')
        if not pos_cfg.revenue_account_id:
            pos_missing.append('Revenue Account')
        if not pos_cfg.offset_coa_account_id:
            pos_missing.append('HPP Account')
        if not pos_cfg.default_payment_account_id:
            pos_missing.append('Payment Account')

    all_required_ok = lv2_count > 0 and lv3_count > 0 and pos_config_ok and stt_ok and users_ok
    required_done = sum([
        lv2_count > 0,
        lv3_count > 0,
        pos_config_ok,
        stt_ok,
        users_ok,
    ])

    return {
        'lv2_list': lv2_list,
        'lv2_count': lv2_count,
        'lv2_ok': lv2_count > 0,
        'lv3_count': lv3_count,
        'lv3_ok': lv3_count > 0,
        'pos_config_ok': pos_config_ok,
        'pos_cfg': pos_cfg,
        'pos_missing': pos_missing,
        'stt_ok': stt_ok,
        'stt_exists': stt_exists,
        'stt_assigned': stt_assigned,
        'users': users,
        'users_ok': users_ok,
        'qris_ok': qris_ok,
        'all_required_ok': all_required_ok,
        'required_done': required_done,
        'required_total': 5,
    }


@login_required
def setup_wizard(request: HttpRequest, pk: int) -> HttpResponse:
    """Checklist dashboard wizard for configuring an Entitas Bisnis for Kasir."""
    eb = get_object_or_404(
        EntitasBisnis.objects
        .select_related('pos_config', 'tipe_entitas')
        .prefetch_related('children_lv2__children_lv3'),
        pk=pk,
    )
    checks = _compute_wizard_checks(eb)
    add_lv2_form = EntitasBisnisLv2Form()
    add_lv3_form = EntitasBisnisLv3Form()
    return render(request, 'entitas_bisnis/setup_wizard.html', {
        'eb': eb,
        'checks': checks,
        'add_lv2_form': add_lv2_form,
        'add_lv3_form': add_lv3_form,
    })
```

- [ ] **Step 4: Register URL in `apps/entitas_bisnis/urls.py`**

Add to urlpatterns:
```python
path('<int:pk>/setup/', views.setup_wizard, name='setup_wizard'),
```

- [ ] **Step 5: Run tests (expect pass)**

```
python manage.py test apps.entitas_bisnis.tests.test_wizard -v 2 --keepdb
```
Expected: all PASS (template doesn't exist yet — view will raise `TemplateDoesNotExist`, so create a minimal placeholder first):

Create `templates/entitas_bisnis/setup_wizard.html`:
```html
{% extends 'base.html' %}
{% block content %}WIZARD PLACEHOLDER{% endblock %}
```

Re-run — all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/entitas_bisnis/views.py apps/entitas_bisnis/urls.py apps/entitas_bisnis/tests/test_wizard.py templates/entitas_bisnis/setup_wizard.html
git commit -m "feat(entitas_bisnis): add setup_wizard view, _compute_wizard_checks, URL"
```

---

### Task 2: `?next=` support in pos_config + accounts views

**Files:**
- Modify: `apps/pos_config/views.py`
- Modify: `apps/accounts/views.py`
- Modify: `templates/accounts/user_form.html`

- [ ] **Step 1: Add `?next=` to `merchant_config` in `apps/pos_config/views.py`**

Find:
```python
        if form.is_valid():
            form.save()
            messages.success(request, 'Konfigurasi merchant POS disimpan.')
            return redirect('pos_config:merchant_config', pk=pk)
```
Replace with:
```python
        if form.is_valid():
            form.save()
            messages.success(request, 'Konfigurasi merchant POS disimpan.')
            next_url = request.GET.get('next', '')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('pos_config:merchant_config', pk=pk)
```

Also pass `next_url` to template context so the form action preserves it:
```python
    return render(request, 'pos_config/merchant_config_form.html', {
        'form': form, 'entitas': entitas, 'config': config,
        'next_url': request.GET.get('next', ''),
    })
```

In `templates/pos_config/merchant_config_form.html`, find the `<form method="post">` tag and change to:
```html
<form method="post" action="?{% if next_url %}next={{ next_url }}{% endif %}">
```

- [ ] **Step 2: Add `?next=` + `?eb=` to `user_create` in `apps/accounts/views.py`**

Find:
```python
    form = UserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user_obj = form.save()
        dj_messages.success(request, f'User {user_obj.email} berhasil dibuat.')
        return redirect('accounts:user_detail', pk=user_obj.pk)
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Tambah User'})
```
Replace with:
```python
    form = UserForm(request.POST or None)
    next_url = request.GET.get('next', '')
    eb_pk = request.GET.get('eb', '')
    if request.method == 'POST' and form.is_valid():
        user_obj = form.save()
        # Auto-associate with EB if ?eb= param present
        if eb_pk:
            from apps.accounts.models import UserEntitasBisnis
            from apps.entitas_bisnis.models import EntitasBisnis
            try:
                eb = EntitasBisnis.objects.get(pk=int(eb_pk))
                UserEntitasBisnis.objects.get_or_create(user=user_obj, entitas_bisnis=eb)
            except (EntitasBisnis.DoesNotExist, ValueError, TypeError):
                pass
        dj_messages.success(request, f'User {user_obj.email} berhasil dibuat.')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('accounts:user_detail', pk=user_obj.pk)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': 'Tambah User',
        'next_url': next_url,
        'eb_pk': eb_pk,
    })
```

- [ ] **Step 3: Update `templates/accounts/user_form.html` to thread params through form action**

Find `<form method="post">` and change to:
```html
<form method="post" action="?{% if next_url %}next={{ next_url }}{% endif %}{% if eb_pk %}&eb={{ eb_pk }}{% endif %}">
```

- [ ] **Step 4: Verify**

```
python manage.py check
```
Expected: 0 issues.

- [ ] **Step 5: Commit**

```bash
git add apps/pos_config/views.py apps/accounts/views.py templates/accounts/user_form.html
git commit -m "feat: add ?next= redirect support to merchant_config and user_create"
```

---

### Task 3: Full wizard template

**Files:**
- Replace: `templates/entitas_bisnis/setup_wizard.html`

- [ ] **Step 1: Read `templates/pos_config/merchant_config_form.html` to confirm the form action change landed correctly, then check `apps/purchase/models.py` for SubTransactionType URL**

```
python manage.py show_urls 2>/dev/null | grep stt || python manage.py check
```
Just confirm `python manage.py check` gives 0 issues — the URL for STT will link to Master Data tipe-transaksi list.

- [ ] **Step 2: Write the full wizard template**

Replace `templates/entitas_bisnis/setup_wizard.html` entirely with:

```html
{% extends 'base.html' %}
{% block title %}Setup Wizard — {{ eb.nama }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Setup Wizard</h1>
    <p class="ni-page-header__subtitle">{{ eb.nama }} · {{ eb.tipe_entitas }}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'entitas_bisnis:update' eb.pk %}" class="ni-btn ni-btn--secondary">
      <i data-lucide="arrow-left" style="width:14px;height:14px"></i> Kembali ke Edit
    </a>
  </div>
</div>

{% if checks.all_required_ok %}
<div class="ni-card ni-animate-fade-in" style="margin-bottom:20px;border-left:4px solid var(--ni-success,#16a34a);">
  <div class="ni-card__body">
    <div style="display:flex;align-items:center;gap:12px;">
      <i data-lucide="check-circle-2" style="width:32px;height:32px;color:var(--ni-success,#16a34a);flex-shrink:0;"></i>
      <div>
        <p style="font-weight:700;font-size:1.1rem;margin:0;">{{ eb.nama }} siap digunakan!</p>
        <p style="margin:4px 0 0;color:var(--ni-text-muted);">Semua konfigurasi wajib telah selesai.</p>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;">
        <a href="{% url 'sales:kasir_pos' %}" class="ni-btn ni-btn--primary">
          <i data-lucide="monitor-check" style="width:14px;height:14px"></i> Buka Kasir
        </a>
        <a href="{% url 'entitas_bisnis:list' %}" class="ni-btn ni-btn--secondary">Entitas Bisnis</a>
      </div>
    </div>
  </div>
</div>
{% else %}
<div class="ni-card ni-animate-fade-in" style="margin-bottom:20px;border-left:4px solid #d97706;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:center;gap:12px;">
      <i data-lucide="alert-triangle" style="width:28px;height:28px;color:#d97706;flex-shrink:0;"></i>
      <div>
        <p style="font-weight:700;margin:0;">Konfigurasi belum lengkap</p>
        <p style="margin:4px 0 0;color:var(--ni-text-muted);">Selesaikan semua item wajib di bawah sebelum menggunakan kasir.</p>
      </div>
    </div>
  </div>
</div>
{% endif %}

<!-- Progress bar -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:20px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
      <span style="font-weight:600;font-size:0.875rem;">Progress Wajib</span>
      <span style="font-size:0.875rem;color:var(--ni-text-muted);">{{ checks.required_done }} dari {{ checks.required_total }} selesai</span>
    </div>
    <div style="background:var(--ni-border);border-radius:8px;height:10px;overflow:hidden;">
      <div style="background:{% if checks.all_required_ok %}var(--ni-success,#16a34a){% else %}#d97706{% endif %};height:100%;border-radius:8px;width:{% widthratio checks.required_done checks.required_total 100 %}%;transition:width .3s;"></div>
    </div>
  </div>
</div>

<!-- ── Wajib ── -->
<div class="ni-section-header"><h2 class="ni-section-header__title">Wajib</h2></div>

<!-- 1. Toko (Lv2) -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.lv2_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">Toko (Level 2)</span>
          {% if checks.lv2_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Belum</span>
          {% endif %}
        </div>
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">
          {% if checks.lv2_ok %}{{ checks.lv2_count }} toko aktif terdaftar.{% else %}Tambahkan minimal 1 toko (cabang) untuk entitas bisnis ini.{% endif %}
        </p>
        {% if checks.lv2_list %}
        <div style="margin-bottom:10px;">
          {% for lv2 in checks.lv2_list %}
          <div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--ni-border);font-size:0.875rem;">
            <i data-lucide="store" style="width:14px;height:14px;flex-shrink:0;color:var(--ni-text-muted);"></i>
            <span>{{ lv2.nama }}</span>
            <span class="ni-badge ni-badge--success" style="font-size:0.7rem;">{{ lv2.children_lv3.count }} outlet</span>
          </div>
          {% endfor %}
        </div>
        {% endif %}
        <button type="button" class="ni-btn ni-btn--success ni-btn--sm" onclick="niEB.openAddLv2({{ eb.pk }})">
          <i data-lucide="plus" style="width:14px;height:14px"></i> Tambah Toko
        </button>
      </div>
    </div>
  </div>
</div>

<!-- 2. Outlet (Lv3) -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.lv3_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">Outlet (Level 3)</span>
          {% if checks.lv3_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Belum</span>
          {% endif %}
        </div>
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">
          {% if checks.lv3_ok %}{{ checks.lv3_count }} outlet aktif. Outlet adalah unit yang muncul di layar pilih kasir.{% else %}Tambahkan minimal 1 outlet. Outlet muncul sebagai pilihan di layar kasir.{% endif %}
        </p>
        {% for lv2 in checks.lv2_list %}
        <div style="margin-bottom:8px;">
          <div style="font-size:0.8rem;font-weight:600;color:var(--ni-text-muted);margin-bottom:4px;">{{ lv2.nama }}</div>
          {% for lv3 in lv2.children_lv3.all %}
          {% if lv3.status_aktif %}
          <div style="display:flex;align-items:center;gap:8px;padding:3px 0 3px 14px;font-size:0.875rem;">
            <i data-lucide="dot" style="width:12px;height:12px;flex-shrink:0;"></i>
            <span>{{ lv3.nama }}</span>
          </div>
          {% endif %}
          {% endfor %}
          <button type="button" class="ni-btn ni-btn--success ni-btn--sm" onclick="niEB.openAddLv3({{ eb.pk }}, {{ lv2.pk }})" style="margin-top:4px;">
            <i data-lucide="plus" style="width:12px;height:12px"></i> Tambah Outlet di {{ lv2.nama }}
          </button>
        </div>
        {% empty %}
        <p style="font-size:0.875rem;color:var(--ni-text-muted);">Tambahkan Toko (Lv2) terlebih dahulu sebelum menambah outlet.</p>
        {% endfor %}
      </div>
    </div>
  </div>
</div>

<!-- 3. POS Config -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.pos_config_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">POS Config</span>
          {% if checks.pos_config_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Belum</span>
          {% endif %}
        </div>
        {% if checks.pos_config_ok %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">
          Tax: {{ checks.pos_cfg.default_tax_pct }}% ·
          STT: {{ checks.pos_cfg.sub_transaction_type }} ·
          Revenue: {{ checks.pos_cfg.revenue_account }}
        </p>
        {% elif checks.pos_missing %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 4px;">Field belum diisi:</p>
        <ul style="margin:0 0 8px;padding-left:18px;font-size:0.875rem;color:var(--ni-danger,#dc2626);">
          {% for field in checks.pos_missing %}<li>{{ field }}</li>{% endfor %}
        </ul>
        {% else %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">Set akun akuntansi dan pajak default untuk semua transaksi POS.</p>
        {% endif %}
        <a href="{% url 'pos_config:merchant_config' eb.pk %}?next={% url 'entitas_bisnis:setup_wizard' eb.pk %}" class="ni-btn ni-btn--primary ni-btn--sm">
          <i data-lucide="settings" style="width:14px;height:14px"></i>
          {% if checks.pos_cfg %}Edit POS Config{% else %}Setup POS Config{% endif %}
        </a>
      </div>
    </div>
  </div>
</div>

<!-- 4. Sub-Transaction Type -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.stt_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">Sub-Transaction Type (Kasir)</span>
          {% if checks.stt_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Belum</span>
          {% endif %}
        </div>
        {% if checks.stt_ok %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">STT sudah diassign di POS Config: <strong>{{ checks.pos_cfg.sub_transaction_type }}</strong></p>
        {% elif not checks.stt_exists %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 4px;">Belum ada Sub-Transaction Type dengan module <code>sales</code>.</p>
        <p style="font-size:0.8rem;color:var(--ni-text-muted);margin:0 0 8px;">Buat STT baru di Master Data, lalu assign di POS Config.</p>
        <a href="{% url 'master_data:stt_create' %}?next={% url 'entitas_bisnis:setup_wizard' eb.pk %}" class="ni-btn ni-btn--primary ni-btn--sm">
          <i data-lucide="plus" style="width:14px;height:14px"></i> Buat Sub-Transaction Type
        </a>
        {% else %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">STT sudah ada tapi belum di-assign di POS Config.</p>
        <a href="{% url 'pos_config:merchant_config' eb.pk %}?next={% url 'entitas_bisnis:setup_wizard' eb.pk %}" class="ni-btn ni-btn--primary ni-btn--sm">
          <i data-lucide="settings" style="width:14px;height:14px"></i> Assign STT di POS Config
        </a>
        {% endif %}
      </div>
    </div>
  </div>
</div>

<!-- 5. Kasir User -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.users_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">Kasir User</span>
          {% if checks.users_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Belum</span>
          {% endif %}
        </div>
        {% if checks.users %}
        <div style="margin-bottom:8px;">
          {% for ueb in checks.users %}
          <div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--ni-border);font-size:0.875rem;">
            <i data-lucide="user" style="width:14px;height:14px;flex-shrink:0;color:var(--ni-text-muted);"></i>
            <span>{{ ueb.user.name }}</span>
            <span style="color:var(--ni-text-muted);">{{ ueb.user.email }}</span>
          </div>
          {% endfor %}
        </div>
        {% else %}
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">Tambahkan minimal 1 user yang bisa login sebagai kasir di outlet ini.</p>
        {% endif %}
        <a href="{% url 'accounts:user_create' %}?next={% url 'entitas_bisnis:setup_wizard' eb.pk %}&eb={{ eb.pk }}" class="ni-btn ni-btn--primary ni-btn--sm">
          <i data-lucide="user-plus" style="width:14px;height:14px"></i> Tambah User Kasir
        </a>
      </div>
    </div>
  </div>
</div>

<!-- ── Direkomendasikan ── -->
<div class="ni-section-header"><h2 class="ni-section-header__title">Direkomendasikan</h2></div>

<!-- 6. QRIS -->
<div class="ni-card ni-animate-fade-in" style="margin-bottom:12px;">
  <div class="ni-card__body">
    <div style="display:flex;align-items:flex-start;gap:14px;">
      <div style="flex-shrink:0;margin-top:2px;">
        {% if checks.qris_ok %}
        <i data-lucide="check-circle-2" style="width:24px;height:24px;color:var(--ni-success,#16a34a);"></i>
        {% else %}
        <i data-lucide="circle" style="width:24px;height:24px;color:var(--ni-text-muted);"></i>
        {% endif %}
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <span style="font-weight:700;font-size:1rem;">QRIS Image</span>
          {% if checks.qris_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Opsional</span>
          {% endif %}
        </div>
        <p style="color:var(--ni-text-muted);font-size:0.875rem;margin:0 0 8px;">
          {% if checks.qris_ok %}Gambar QRIS sudah diupload.{% else %}Upload gambar QR code untuk pembayaran QRIS di kasir.{% endif %}
        </p>
        <a href="{% url 'pos_config:merchant_config' eb.pk %}?next={% url 'entitas_bisnis:setup_wizard' eb.pk %}" class="ni-btn ni-btn--secondary ni-btn--sm">
          <i data-lucide="upload" style="width:14px;height:14px"></i>
          {% if checks.qris_ok %}Ganti QRIS{% else %}Upload QRIS{% endif %}
        </a>
      </div>
    </div>
  </div>
</div>

<!-- ── AJAX Modals (reuse same pattern as list.html) ── -->
<div class="ni-modal-backdrop" id="modalAddLv2">
  <div class="ni-modal">
    <div class="ni-modal__header">
      <h3 class="ni-modal__title">Tambah Toko (Level 2)</h3>
      <button class="ni-modal__close" type="button" onclick="niEB.close('modalAddLv2')"><i data-lucide="x"></i></button>
    </div>
    <div class="ni-modal__body">
      <div id="errAddLv2" style="display:none;" class="ni-alert ni-alert--danger"></div>
      <form id="formAddLv2" method="post" action="">
        {% csrf_token %}
        {% for field in add_lv2_form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}{% if field.field.required %} <span style="color:var(--ni-danger)">*</span>{% endif %}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
        {% endfor %}
      </form>
    </div>
    <div class="ni-modal__footer">
      <button type="button" class="ni-btn ni-btn--secondary" onclick="niEB.close('modalAddLv2')">Batal</button>
      <button type="button" class="ni-btn ni-btn--primary" onclick="niEB.submitAjax('formAddLv2', 'errAddLv2')">Simpan</button>
    </div>
  </div>
</div>

<div class="ni-modal-backdrop" id="modalAddLv3">
  <div class="ni-modal">
    <div class="ni-modal__header">
      <h3 class="ni-modal__title">Tambah Outlet (Level 3)</h3>
      <button class="ni-modal__close" type="button" onclick="niEB.close('modalAddLv3')"><i data-lucide="x"></i></button>
    </div>
    <div class="ni-modal__body">
      <div id="errAddLv3" style="display:none;" class="ni-alert ni-alert--danger"></div>
      <form id="formAddLv3" method="post" action="">
        {% csrf_token %}
        {% for field in add_lv3_form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}{% if field.field.required %} <span style="color:var(--ni-danger)">*</span>{% endif %}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
        {% endfor %}
      </form>
    </div>
    <div class="ni-modal__footer">
      <button type="button" class="ni-btn ni-btn--secondary" onclick="niEB.close('modalAddLv3')">Batal</button>
      <button type="button" class="ni-btn ni-btn--primary" onclick="niEB.submitAjax('formAddLv3', 'errAddLv3')">Simpan</button>
    </div>
  </div>
</div>

<script>
// niEB object — same pattern as list.html
const niEB = {
  open(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'flex';
  },
  close(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  },
  openAddLv2(ebPk) {
    const form = document.getElementById('formAddLv2');
    form.action = `/entitas-bisnis/${ebPk}/lv2/create/`;
    this.open('modalAddLv2');
  },
  openAddLv3(ebPk, lv2Pk) {
    const form = document.getElementById('formAddLv3');
    form.action = `/entitas-bisnis/${ebPk}/lv2/${lv2Pk}/lv3/create/`;
    this.open('modalAddLv3');
  },
  submitAjax(formId, errId) {
    const form = document.getElementById(formId);
    const err = document.getElementById(errId);
    const data = new FormData(form);
    fetch(form.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: data,
    })
      .then(r => r.json())
      .then(json => {
        if (json.success) {
          location.reload();
        } else {
          err.style.display = 'block';
          const msgs = Object.values(json.errors || {}).flat();
          err.textContent = msgs.join(' ');
        }
      })
      .catch(() => {
        err.style.display = 'block';
        err.textContent = 'Terjadi kesalahan. Coba lagi.';
      });
  },
};

// Close modal on backdrop click
document.querySelectorAll('.ni-modal-backdrop').forEach(backdrop => {
  backdrop.addEventListener('click', e => {
    if (e.target === backdrop) backdrop.style.display = 'none';
  });
});
</script>
{% endblock %}
```

**Note on `{% url 'master_data:stt_create' %}`:** Check if this URL name exists by running `python manage.py show_urls | grep stt`. If it doesn't exist, replace that button with:
```html
<a href="{% url 'master_data:tipe_transaksi_list' %}" class="ni-btn ni-btn--primary ni-btn--sm">
  <i data-lucide="list" style="width:14px;height:14px"></i> Kelola Sub-Transaction Type
</a>
```

- [ ] **Step 3: Verify page renders**

```
python manage.py runserver
```
Navigate to `/entitas-bisnis/<any_pk>/setup/` — page should render with all 6 checklist items visible.

- [ ] **Step 4: Run wizard tests**

```
python manage.py test apps.entitas_bisnis.tests.test_wizard -v 2 --keepdb
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/entitas_bisnis/setup_wizard.html
git commit -m "feat(entitas_bisnis): add full setup wizard template"
```

---

### Task 4: "Setup Wizard" button on lv1 edit page

**Files:**
- Modify: `templates/entitas_bisnis/form.html`

- [ ] **Step 1: Read current form.html to find insertion point**

Open `templates/entitas_bisnis/form.html`. The file has a `<div class="ni-btn-row"...>` with Simpan + Batal. Add the wizard button.

- [ ] **Step 2: Add Setup Wizard button**

Find the section in `templates/entitas_bisnis/form.html` that contains the "Kembali" / "Batal" button in the page header or btn-row — specifically the `{% if object.pk %}` block near the bottom that already has the "POS Configuration" section. Add the button to the page header actions.

Change the page header from:
```html
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">{{ title }}</h1>
  </div>
</div>
```
to:
```html
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">{{ title }}</h1>
  </div>
  {% if object.pk %}
  <div class="ni-page-header__actions">
    <a href="{% url 'entitas_bisnis:setup_wizard' object.pk %}" class="ni-btn ni-btn--primary ni-btn--sm">
      <i data-lucide="rocket" style="width:14px;height:14px"></i> Setup Wizard
    </a>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 3: Verify**

```
python manage.py check
```
Expected: 0 issues.

Navigate to `/entitas-bisnis/<pk>/edit/` — "Setup Wizard" button appears in page header.

- [ ] **Step 4: Commit**

```bash
git add templates/entitas_bisnis/form.html
git commit -m "feat(entitas_bisnis): add Setup Wizard button to lv1 edit page"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Checklist dashboard at `/entitas-bisnis/<pk>/setup/` — Task 1
- ✅ 5 required items + 1 recommended — Task 3 template
- ✅ Progress bar + completion banner — Task 3 template
- ✅ Items 1 & 2 inline AJAX (no page leave) — Task 3 template + niEB JS
- ✅ Items 3–6 link out with `?next=` — Task 2 + Task 3
- ✅ `?eb=` auto-association for user_create — Task 2
- ✅ "Setup Wizard" button on lv1 edit page — Task 4
- ✅ Always accessible, shows "Setup Complete" banner — Task 3

**Potential issues:**
- `{% url 'master_data:stt_create' %}` may not exist — addressed inline in Task 3 with fallback.
- `{% widthratio %}` tag requires `{% load %}` — Django's `widthratio` is in the default `django.template.defaulttags`, no load needed.
- The `niEB` JS in the wizard duplicates the list.html pattern — intentional (wizard is standalone, pulling in the full list.html JS would add unnecessary weight).
