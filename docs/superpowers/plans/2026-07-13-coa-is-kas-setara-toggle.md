# CoA "Kas/Setara Kas" Toggle for Aset Level 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This project is NOT a git repository.** Skip every `git commit` step below — there is nothing to commit to. Just check the box and move to the next step.
>
> **Working directory for test/shell commands:** `naveda_integra/` (where `setup.cfg` and `manage.py` live), inside `d:\DATA\Documents\Kerja\Naveda Integra Finance\NIF Website Dev`.

**Goal:** Let a user toggle `Akun.is_kas_setara` for an Aset Level 2 account directly from the Chart of Accounts "Add"/"Edit" modals, instead of only via Django admin.

**Architecture:** `master_data.Akun` already has `is_kas_setara` (added in a prior feature). It's not a `ModelForm` field on `AsetLv2` (it lives on the synced `Akun` row, not `AsetLv2` itself), so it's read directly from `request.POST` in the two Aset Lv2 views and written to the corresponding `Akun` row after the `AsetLv2` save completes. The `chart_of_accounts` view is extended to attach the current `is_kas_setara` value onto each Aset `AsetLv2` object so the template can pass it into the Edit modal's JS. Only the Aset category's Add/Edit Lv2 modals get the checkbox — Kewajiban/Ekuitas/Pendapatan/Beban are untouched.

**Tech Stack:** Django (views, templates, vanilla JS in an inline `<script>` block), `pytest-django`.

**Reference spec:** `docs/superpowers/specs/2026-07-13-coa-is-kas-setara-toggle-design.md`

---

## File Structure

- Modify: `naveda_integra/apps/master_data/views.py` — import `Akun`; sync `is_kas_setara` in `aset_lv2_create`/`aset_lv2_update`; attach `is_kas_setara` to Aset Lv2 objects in `chart_of_accounts`.
- Modify: `naveda_integra/apps/master_data/tests.py` — new tests.
- Modify: `naveda_integra/templates/master_data/chart_of_accounts.html` — Add/Edit Lv2 modal markup + JS (`openAddLv2`, `openEditLv2`, and the two template call sites).

---

### Task 1: Sync `is_kas_setara` from the Aset Lv2 create/update views, and expose it to the CoA page

**Files:**
- Modify: `naveda_integra/apps/master_data/views.py:26-34` (import), `:259-294` (`aset_lv2_create`, `aset_lv2_update`), `:740-750` (`chart_of_accounts`, the `'Aset'` category dict)
- Modify: `naveda_integra/apps/master_data/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `naveda_integra/apps/master_data/tests.py` (reuse the existing `AsetViewTests`-style fixture pattern already in that file — `self.client`, `create_user()`, `self.lv1`):

```python
class AsetLv2IsKasSetaraSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = AsetLv1.objects.create(kode='1.1', nama='Aset Lancar')

    def test_create_with_checkbox_checked_sets_akun_true(self):
        self.client.post(
            reverse('master_data:aset_lv2_create', args=[self.lv1.pk]),
            {'nama': 'Kas Tunai', 'is_kas_setara': 'on'},
        )
        lv2 = AsetLv2.objects.get(nama='Kas Tunai')
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertTrue(akun.is_kas_setara)

    def test_create_without_checkbox_leaves_akun_false(self):
        self.client.post(
            reverse('master_data:aset_lv2_create', args=[self.lv1.pk]),
            {'nama': 'Piutang Dagang'},
        )
        lv2 = AsetLv2.objects.get(nama='Piutang Dagang')
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertFalse(akun.is_kas_setara)

    def test_update_toggling_checkbox_on_updates_akun(self):
        lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Bank BCA', aset=self.lv1)
        self.client.post(
            reverse('master_data:aset_lv2_update', args=[self.lv1.pk, lv2.pk]),
            {'nama': 'Bank BCA', 'is_kas_setara': 'on'},
        )
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertTrue(akun.is_kas_setara)

    def test_update_toggling_checkbox_off_updates_akun(self):
        lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Bank BCA', aset=self.lv1)
        Akun.objects.filter(kategori_id='aset', kategori_akun=lv2.pk).update(is_kas_setara=True)
        self.client.post(
            reverse('master_data:aset_lv2_update', args=[self.lv1.pk, lv2.pk]),
            {'nama': 'Bank BCA'},
        )
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertFalse(akun.is_kas_setara)


class ChartOfAccountsIsKasSetaraContextTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = AsetLv1.objects.create(kode='1.1', nama='Aset Lancar')
        self.lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Tunai', aset=self.lv1)
        Akun.objects.filter(kategori_id='aset', kategori_akun=self.lv2.pk).update(is_kas_setara=True)

    def test_aset_lv2_items_carry_is_kas_setara(self):
        resp = self.client.get(reverse('master_data:chart_of_accounts'))
        aset_category = next(c for c in resp.context['categories'] if c['name'] == 'Aset')
        lv1 = next(l for l in aset_category['items'] if l.pk == self.lv1.pk)
        lv2 = next(l for l in lv1.sorted_children if l.pk == self.lv2.pk)
        self.assertTrue(lv2.is_kas_setara)

    def test_aset_lv2_without_akun_flag_defaults_false(self):
        lv2b = AsetLv2.objects.create(kode='1.1.2', nama='Piutang Dagang', aset=self.lv1)
        resp = self.client.get(reverse('master_data:chart_of_accounts'))
        aset_category = next(c for c in resp.context['categories'] if c['name'] == 'Aset')
        lv1 = next(l for l in aset_category['items'] if l.pk == self.lv1.pk)
        lv2 = next(l for l in lv1.sorted_children if l.pk == lv2b.pk)
        self.assertFalse(lv2.is_kas_setara)
```

Also make sure `Client`, `reverse`, `AsetLv1`, `AsetLv2`, `Akun`, `create_user` are already imported/available at the top of `tests.py` (they are, per the existing file — no new imports needed).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/master_data/tests.py -k "IsKasSetaraSync or IsKasSetaraContext" -v`
Expected: FAIL — `Akun.DoesNotExist` or `AttributeError: 'AsetLv2' object has no attribute 'is_kas_setara'` (the view doesn't sync/attach it yet).

- [ ] **Step 3: Import `Akun` in views.py**

In `naveda_integra/apps/master_data/views.py`, change:

```python
from .models import (
    AsetLv1, AsetLv2,
    KewajibanLv1, KewajibanLv2,
    EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2,
    BebanLv1, BebanLv2,
    TipeTransaksi,
    Bukti,
)
```

to:

```python
from .models import (
    AsetLv1, AsetLv2,
    KewajibanLv1, KewajibanLv2,
    EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2,
    BebanLv1, BebanLv2,
    TipeTransaksi,
    Bukti,
    Akun,
)
```

- [ ] **Step 4: Sync `is_kas_setara` in `aset_lv2_create`**

Change:

```python
@login_required
def aset_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    form = AsetLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.aset = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(AsetLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Aset Level 2'})
```

to:

```python
@login_required
def aset_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    form = AsetLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.aset = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(AsetLv2, parent.kode)
        obj.save()
        Akun.objects.filter(kategori_id='aset', kategori_akun=obj.pk).update(
            is_kas_setara=request.POST.get('is_kas_setara') == 'on'
        )
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Aset Level 2'})
```

- [ ] **Step 5: Sync `is_kas_setara` in `aset_lv2_update`**

Change:

```python
@login_required
def aset_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    obj = get_object_or_404(AsetLv2, pk=pk, aset=parent)
    old_kode = obj.kode
    form = AsetLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(AsetLv2, 'aset', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Aset Level 2'})
```

to:

```python
@login_required
def aset_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    obj = get_object_or_404(AsetLv2, pk=pk, aset=parent)
    old_kode = obj.kode
    form = AsetLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(AsetLv2, 'aset', obj, old_kode, new_kode)
        else:
            form.save()
        Akun.objects.filter(kategori_id='aset', kategori_akun=obj.pk).update(
            is_kas_setara=request.POST.get('is_kas_setara') == 'on'
        )
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Aset Level 2'})
```

- [ ] **Step 6: Attach `is_kas_setara` onto Aset Lv2 objects in `chart_of_accounts`**

Change:

```python
    categories = [
        {
            'name': 'Aset', 'prefix': '1', 'slug': 'aset',
            'items': _sorted_items(AsetLv1.objects.all()),
            'lv1_create': 'master_data:aset_lv1_create',
            'lv1_update': 'master_data:aset_lv1_update',
            'lv1_delete': 'master_data:aset_lv1_delete',
            'lv2_create': 'master_data:aset_lv2_create',
            'lv2_update': 'master_data:aset_lv2_update',
            'lv2_delete': 'master_data:aset_lv2_delete',
        },
```

to:

```python
    aset_items = _sorted_items(AsetLv1.objects.all())
    kas_setara_map = dict(
        Akun.objects.filter(kategori_id='aset').values_list('kategori_akun', 'is_kas_setara')
    )
    for lv1 in aset_items:
        for lv2 in lv1.sorted_children:
            lv2.is_kas_setara = kas_setara_map.get(lv2.pk, False)

    categories = [
        {
            'name': 'Aset', 'prefix': '1', 'slug': 'aset',
            'items': aset_items,
            'lv1_create': 'master_data:aset_lv1_create',
            'lv1_update': 'master_data:aset_lv1_update',
            'lv1_delete': 'master_data:aset_lv1_delete',
            'lv2_create': 'master_data:aset_lv2_create',
            'lv2_update': 'master_data:aset_lv2_update',
            'lv2_delete': 'master_data:aset_lv2_delete',
        },
```

(The `Kewajiban`/`Ekuitas`/`Pendapatan`/`Beban` dicts right after are unchanged — leave their `'items': _sorted_items(...)` calls exactly as they are.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest apps/master_data/tests.py -k "IsKasSetaraSync or IsKasSetaraContext" -v`
Expected: PASS (6 tests)

- [ ] **Step 8: Run the full master_data test suite to check for regressions**

Run: `pytest apps/master_data/tests.py -v`
Expected: PASS (no regressions)

- [ ] **Step 9: Mark task complete** (no git repo — skip commit)

---

### Task 2: Add the checkbox to the Add/Edit Lv2 modals (Aset only)

**Files:**
- Modify: `naveda_integra/templates/master_data/chart_of_accounts.html` (Add Lv2 modal ~lines 168-194, Edit Lv2 modal ~lines 196-222, the Lv2 row's `openEditLv2` call ~line 70, and the JS `openAddLv2`/`openEditLv2` functions ~lines 373-392)

- [ ] **Step 1: Add the checkbox to the Add Lv2 modal, hidden by default**

Change:

```html
      <form id="coaFormAddLv2" method="post" action="">
        {% csrf_token %}
        <div class="ni-form-group">
          <label class="ni-form-label">Kode <span style="color:var(--ni-text-muted);font-size:0.8rem;">(opsional)</span></label>
          <input type="text" name="kode" class="ni-input" placeholder="Auto-generate jika kosong">
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">Nama <span style="color:var(--ni-danger)">*</span></label>
          <input type="text" name="nama" class="ni-input" required>
        </div>
      </form>
```

to:

```html
      <form id="coaFormAddLv2" method="post" action="">
        {% csrf_token %}
        <div class="ni-form-group">
          <label class="ni-form-label">Kode <span style="color:var(--ni-text-muted);font-size:0.8rem;">(opsional)</span></label>
          <input type="text" name="kode" class="ni-input" placeholder="Auto-generate jika kosong">
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">Nama <span style="color:var(--ni-danger)">*</span></label>
          <input type="text" name="nama" class="ni-input" required>
        </div>
        <div class="ni-form-group" id="coaAddLv2KasSetaraWrap" style="display:none;">
          <label class="ni-form-label" style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="is_kas_setara" id="coaAddLv2IsKasSetara">
            Kas/Setara Kas
          </label>
        </div>
      </form>
```

- [ ] **Step 2: Add the checkbox to the Edit Lv2 modal, hidden by default**

Change:

```html
      <form id="coaFormEditLv2" method="post" action="">
        {% csrf_token %}
        <div class="ni-form-group">
          <label class="ni-form-label">Kode</label>
          <input type="text" name="kode" class="ni-input" id="coaEditLv2Kode">
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">Nama <span style="color:var(--ni-danger)">*</span></label>
          <input type="text" name="nama" class="ni-input" id="coaEditLv2Nama" required>
        </div>
      </form>
```

to:

```html
      <form id="coaFormEditLv2" method="post" action="">
        {% csrf_token %}
        <div class="ni-form-group">
          <label class="ni-form-label">Kode</label>
          <input type="text" name="kode" class="ni-input" id="coaEditLv2Kode">
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">Nama <span style="color:var(--ni-danger)">*</span></label>
          <input type="text" name="nama" class="ni-input" id="coaEditLv2Nama" required>
        </div>
        <div class="ni-form-group" id="coaEditLv2KasSetaraWrap" style="display:none;">
          <label class="ni-form-label" style="display:flex;align-items:center;gap:6px;">
            <input type="checkbox" name="is_kas_setara" id="coaEditLv2IsKasSetara">
            Kas/Setara Kas
          </label>
        </div>
      </form>
```

- [ ] **Step 3: Pass category name + current flag value into the `openEditLv2` call site**

Change (in the Lv2 row loop, ~line 70):

```html
              <button type="button" class="ni-btn ni-btn--warning ni-btn--sm ni-btn--icon" title="Edit"
                onclick="niCoa.openEditLv2('{% url category.lv2_update lv1.pk lv2.pk %}', '{{ lv2.kode }}', '{{ lv2.nama|escapejs }}', {{ forloop.parentloop.parentloop.counter0 }}, {{ forloop.parentloop.counter0 }})">
                <i data-lucide="pencil"></i>
              </button>
```

to:

```html
              <button type="button" class="ni-btn ni-btn--warning ni-btn--sm ni-btn--icon" title="Edit"
                onclick="niCoa.openEditLv2('{% url category.lv2_update lv1.pk lv2.pk %}', '{{ lv2.kode }}', '{{ lv2.nama|escapejs }}', {{ forloop.parentloop.parentloop.counter0 }}, {{ forloop.parentloop.counter0 }}, '{{ category.name }}', {{ lv2.is_kas_setara|yesno:'true,false' }})">
                <i data-lucide="pencil"></i>
              </button>
```

(The `openAddLv2` call site a few lines above already passes `category.name` as its `catName` argument — no change needed there.)

- [ ] **Step 4: Update the `openAddLv2` JS function to show/hide the checkbox based on category**

Change:

```javascript
    openAddLv2: function (url, catName, catIdx, lv1Idx) {
      var form = document.getElementById('coaFormAddLv2');
      form.action = url;
      form.reset();
      document.getElementById('coaAddLv2Title').textContent = 'Tambah Akun ' + catName + ' Level 2';
      this.clearErr('coaErrAddLv2');
      this._activeCategory = catIdx;
      this._activeLv1 = lv1Idx;
      this.open('coaModalAddLv2');
    },
```

to:

```javascript
    openAddLv2: function (url, catName, catIdx, lv1Idx) {
      var form = document.getElementById('coaFormAddLv2');
      form.action = url;
      form.reset();
      document.getElementById('coaAddLv2Title').textContent = 'Tambah Akun ' + catName + ' Level 2';
      document.getElementById('coaAddLv2KasSetaraWrap').style.display = (catName === 'Aset') ? 'block' : 'none';
      this.clearErr('coaErrAddLv2');
      this._activeCategory = catIdx;
      this._activeLv1 = lv1Idx;
      this.open('coaModalAddLv2');
    },
```

- [ ] **Step 5: Update the `openEditLv2` JS function to accept and apply the new parameters**

Change:

```javascript
    openEditLv2: function (url, kode, nama, catIdx, lv1Idx) {
      var form = document.getElementById('coaFormEditLv2');
      form.action = url;
      document.getElementById('coaEditLv2Kode').value = kode;
      document.getElementById('coaEditLv2Nama').value = nama;
      this.clearErr('coaErrEditLv2');
      this._activeCategory = catIdx;
      this._activeLv1 = lv1Idx;
      this.open('coaModalEditLv2');
    },
```

to:

```javascript
    openEditLv2: function (url, kode, nama, catIdx, lv1Idx, catName, isKasSetara) {
      var form = document.getElementById('coaFormEditLv2');
      form.action = url;
      document.getElementById('coaEditLv2Kode').value = kode;
      document.getElementById('coaEditLv2Nama').value = nama;
      var isAset = (catName === 'Aset');
      document.getElementById('coaEditLv2KasSetaraWrap').style.display = isAset ? 'block' : 'none';
      document.getElementById('coaEditLv2IsKasSetara').checked = isAset && !!isKasSetara;
      this.clearErr('coaErrEditLv2');
      this._activeCategory = catIdx;
      this._activeLv1 = lv1Idx;
      this.open('coaModalEditLv2');
    },
```

- [ ] **Step 6: Run the Task 1 tests again to confirm nothing broke, plus a template-rendering smoke check**

Run: `pytest apps/master_data/tests.py -v`
Expected: PASS (no regressions; the Task 1 tests already assert on `resp.context['categories']`, not on the HTML string, so this step is a regression check, not new coverage)

Then add one more test to `naveda_integra/apps/master_data/tests.py` to lock in the rendered `onclick` wiring (add to `ChartOfAccountsIsKasSetaraContextTests`):

```python
    def test_edit_lv2_onclick_passes_category_name_and_flag(self):
        resp = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertContains(resp, "'Aset', true)")
```

Run: `pytest apps/master_data/tests.py -k ChartOfAccountsIsKasSetara -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Mark task complete** (no git repo — skip commit)

---

### Task 3: Manual verification in the browser

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server** (from `naveda_integra/`): `python manage.py runserver`

- [ ] **Step 2: Open the Chart of Accounts page, expand Aset → a Level 1 group**

Click "+" to add a new Level 2 account. Confirm the "Kas/Setara Kas" checkbox is visible in the Add modal (only for Aset — check a Kewajiban Level 1 group's "+" button shows no such checkbox).

- [ ] **Step 3: Create an account with the checkbox ticked**

Save it, then open `/admin/master_data/akun/`, find the new account, confirm `is_kas_setara` is checked.

- [ ] **Step 4: Edit that same account from the CoA page**

Click its pencil/Edit icon — confirm the checkbox opens already ticked. Untick it and save. Refresh `/admin/master_data/akun/` and confirm it's now unchecked.

- [ ] **Step 5: Confirm invoice feature still works end-to-end**

Since this Aset-account toggle is the same `is_kas_setara` field the invoice payment-label feature (shipped earlier) reads from, open a sales or pendapatan invoice using this account and confirm the Kas/Kredit label still reflects the flag correctly.

- [ ] **Step 6: Mark task complete** (no git repo — skip commit)
