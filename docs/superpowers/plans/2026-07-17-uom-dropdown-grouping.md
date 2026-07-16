# UOM Dropdown Grouping by Dimension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every "full catalogue" UOM dropdown in the app (Item UOM Conversion form, Production Create form, Purchase quick-add modal, BOM line select) group its options by dimension using `<optgroup>`, ordered by the fixed `DIMENSION_CHOICES` order and, within each group, ascending `factor_to_base` (null-factor packaging units last).

**Architecture:** A single queryset method `UnitOfMeasure.objects.for_dropdown()` becomes the one source of truth for ordering. Django form fields consume it through a new reusable `GroupedModelChoiceField` (renders real `<optgroup>` via Django's own choice-grouping support). JS-driven selects consume it as a pre-sorted, pre-grouped list serialized to JSON, and the JS only detects dimension-boundary changes while looping — no client-side sorting.

**Tech Stack:** Django (forms, ORM `Case`/`When` annotations), vanilla JS (no new libraries).

Spec: `docs/superpowers/specs/2026-07-17-uom-dropdown-grouping-design.md`

---

### Task 1: `UnitOfMeasure.objects.for_dropdown()` ordering

**Files:**
- Modify: `apps/uom/models.py`
- Test: `apps/uom/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/uom/tests.py`, in a new test class (place after `UnitOfMeasureModelTests`):

```python
class ForDropdownOrderingTests(TestCase):
    def setUp(self):
        # Deliberately created out of the expected output order, and with
        # unique kodes so this test doesn't depend on the seeded system units.
        self.w_kg = UnitOfMeasure.objects.create(
            kode='t_kg', nama='Test Kg', dimension='weight', factor_to_base=Decimal('1'))
        self.c_box = UnitOfMeasure.objects.create(
            kode='t_box', nama='Test Box', dimension='count', factor_to_base=None)
        self.w_gram = UnitOfMeasure.objects.create(
            kode='t_gram', nama='Test Gram', dimension='weight', factor_to_base=Decimal('0.001'))
        self.c_pcs = UnitOfMeasure.objects.create(
            kode='t_pcs', nama='Test Pcs', dimension='count', factor_to_base=Decimal('1'))

    def test_orders_by_dimension_then_factor_then_kode(self):
        kodes = list(
            UnitOfMeasure.objects
            .filter(kode__in=['t_kg', 't_box', 't_gram', 't_pcs'])
            .for_dropdown()
            .values_list('kode', flat=True)
        )
        # count (DIMENSION_CHOICES[0]) before weight (DIMENSION_CHOICES[1]);
        # within count: factor=1 before null; within weight: 0.001 before 1.
        self.assertEqual(kodes, ['t_pcs', 't_box', 't_gram', 't_kg'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.ForDropdownOrderingTests -v 2`
Expected: FAIL with `AttributeError: 'QuerySet' object has no attribute 'for_dropdown'`

- [ ] **Step 3: Implement `for_dropdown()`**

In `apps/uom/models.py`, add a custom queryset and wire it up as the model's manager. Insert after the `DIMENSION_CHOICES` list and before `class UnitOfMeasure`:

```python
class UnitOfMeasureQuerySet(models.QuerySet):
    def for_dropdown(self):
        """Order for dropdown display: grouped by dimension (following
        DIMENSION_CHOICES order), then by factor_to_base ascending within
        each dimension (custom packaging units with no factor sort last)."""
        dimension_rank = models.Case(
            *[
                models.When(dimension=code, then=models.Value(i))
                for i, (code, _label) in enumerate(DIMENSION_CHOICES)
            ],
            output_field=models.IntegerField(),
        )
        factor_null_rank = models.Case(
            models.When(factor_to_base__isnull=True, then=models.Value(1)),
            default=models.Value(0),
            output_field=models.IntegerField(),
        )
        return self.annotate(
            _dim_rank=dimension_rank,
            _factor_null=factor_null_rank,
        ).order_by('_dim_rank', '_factor_null', 'factor_to_base', 'kode')
```

Then change the `UnitOfMeasure` class to use it as the default manager, by adding this line right after the `class UnitOfMeasure(models.Model):` line (before `kode = ...`):

```python
    objects = UnitOfMeasureQuerySet.as_manager()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.ForDropdownOrderingTests -v 2`
Expected: PASS

- [ ] **Step 5: Run the full uom test suite to check nothing else broke**

Run: `python manage.py test apps.uom -v 2`
Expected: all PASS (adding a custom manager via `as_manager()` preserves all default `QuerySet` behavior, so no other test should be affected)

- [ ] **Step 6: Commit**

```bash
git add apps/uom/models.py apps/uom/tests.py
git commit -m "feat(uom): add for_dropdown() ordering by dimension then factor"
```

---

### Task 2: `GroupedModelChoiceField` + apply to `ItemUOMForm.uom`

**Files:**
- Create: `apps/uom/fields.py`
- Modify: `apps/uom/forms.py`
- Test: `apps/uom/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/uom/tests.py` (near `ItemUOMCrudTests`, e.g. right after it):

```python
class ItemUOMFormGroupedDropdownTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='grp@example.com', password='pw123456', name='G')
        self.client.force_login(self.user)
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(
            nama='Grouped Item', tipe_item='ITM', stock_uom=self.pcs)

    def test_conversion_create_form_renders_optgroups_in_dimension_order(self):
        resp = self.client.get(reverse('uom:conversion_create'))
        content = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        count_pos = content.index('<optgroup label="Count / Jumlah">')
        weight_pos = content.index('<optgroup label="Berat">')
        volume_pos = content.index('<optgroup label="Volume">')
        length_pos = content.index('<optgroup label="Panjang">')
        area_pos = content.index('<optgroup label="Luas">')
        self.assertTrue(count_pos < weight_pos < volume_pos < length_pos < area_pos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.ItemUOMFormGroupedDropdownTests -v 2`
Expected: FAIL — `ValueError: substring not found` (no `<optgroup>` markup exists yet)

- [ ] **Step 3: Create `apps/uom/fields.py`**

```python
"""Reusable form fields for the uom app."""
import itertools
from functools import partial

from django.forms.models import ModelChoiceField, ModelChoiceIterator


class GroupedModelChoiceIterator(ModelChoiceIterator):
    def __init__(self, field, groupby):
        self.groupby = groupby
        super().__init__(field)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        for group, objs in itertools.groupby(self.queryset, self.groupby):
            yield (group, [self.choice(obj) for obj in objs])


class GroupedModelChoiceField(ModelChoiceField):
    """A ModelChoiceField that renders <optgroup> elements.

    ``choices_groupby`` receives a model instance and returns its group
    label. The queryset must already be sorted so instances sharing a group
    are contiguous — itertools.groupby only groups consecutive items.
    """
    def __init__(self, *args, choices_groupby, **kwargs):
        self.iterator = partial(GroupedModelChoiceIterator, groupby=choices_groupby)
        super().__init__(*args, **kwargs)
```

- [ ] **Step 4: Apply it to `ItemUOMForm.uom`**

In `apps/uom/forms.py`, add the import and declare the field explicitly:

```python
from django import forms

from .fields import GroupedModelChoiceField
from .models import ItemUOM, UnitOfMeasure
```

```python
class ItemUOMForm(forms.ModelForm):
    uom = GroupedModelChoiceField(
        queryset=UnitOfMeasure.objects.for_dropdown(),
        choices_groupby=lambda u: u.get_dimension_display(),
        label='Satuan',
    )

    class Meta:
        model = ItemUOM
        fields = ('item', 'uom', 'qty_in_stock_uom')
```

(Keep the existing `clean()` method unchanged below it.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.ItemUOMFormGroupedDropdownTests -v 2`
Expected: PASS

- [ ] **Step 6: Run the full uom test suite**

Run: `python manage.py test apps.uom -v 2`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add apps/uom/fields.py apps/uom/forms.py apps/uom/tests.py
git commit -m "feat(uom): render Item UOM conversion dropdown grouped by dimension"
```

---

### Task 3: Apply `GroupedModelChoiceField` to `ProductionOrderForm.input_uom`

**Files:**
- Modify: `apps/manufacturing/forms.py`
- Test: `apps/manufacturing/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/manufacturing/tests.py`, near `test_bom_create_get_renders_input_uom_select_markup` (same test class):

```python
    def test_production_create_get_renders_input_uom_optgroups_in_order(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:production_create'))
        content = response.content.decode()
        count_pos = content.index('<optgroup label="Count / Jumlah">')
        weight_pos = content.index('<optgroup label="Berat">')
        volume_pos = content.index('<optgroup label="Volume">')
        length_pos = content.index('<optgroup label="Panjang">')
        area_pos = content.index('<optgroup label="Luas">')
        self.assertTrue(count_pos < weight_pos < volume_pos < length_pos < area_pos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.manufacturing.tests.ManufacturingUomTests.test_production_create_get_renders_input_uom_optgroups_in_order -v 2`

Expected: FAIL — `ValueError: substring not found`

- [ ] **Step 3: Update `ProductionOrderForm` in `apps/manufacturing/forms.py`**

Add the import:

```python
from apps.uom.fields import GroupedModelChoiceField
```

Replace the `input_uom` field declaration:

```python
    input_uom = GroupedModelChoiceField(
        queryset=None,
        choices_groupby=lambda u: u.get_dimension_display(),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input', 'id': 'id_input_uom'}),
        label='Satuan Input Qty Produksi',
        help_text='Opsional. Bila dipilih, Qty Diproduksi di atas dibaca dalam satuan ini dan '
                   'dikonversi otomatis ke satuan stok Finished Good.',
    )
```

And in `__init__`, change the queryset assignment:

```python
        from apps.uom.models import UnitOfMeasure
        self.fields['input_uom'].queryset = UnitOfMeasure.objects.for_dropdown()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.manufacturing.tests.ManufacturingUomTests.test_production_create_get_renders_input_uom_optgroups_in_order -v 2`
Expected: PASS

- [ ] **Step 5: Run the full manufacturing test suite**

Run: `python manage.py test apps.manufacturing -v 2`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/manufacturing/forms.py apps/manufacturing/tests.py
git commit -m "feat(manufacturing): render Production Create input_uom dropdown grouped by dimension"
```

---

### Task 4: Purchase quick-add modal (JS-driven, 3 selects)

**Files:**
- Modify: `apps/purchase/views.py`
- Modify: `templates/purchase/purchase_form.html`
- Test: `apps/purchase/tests.py`

- [ ] **Step 1: Write the failing test**

Add a new test class to `apps/purchase/tests.py` (place it near the end of the file; `Role`, `User`, `Client`, `reverse` and `TestCase` are already imported at the top of this file — this follows the same `Role.objects.create(...)` + `User.objects.create_user(email=..., password=..., role=role)` pattern used by `test_purchase_create_post_converts_carton_to_base`):

```python
class PurchaseCreateUomModalGroupingTests(TestCase):
    def setUp(self):
        role = Role.objects.create(kode='admin-puom', nama='Admin PUOM')
        self.user = User.objects.create_user(email='puom@test.com', password='pass1234', role=role)
        self.client.force_login(self.user)

    def test_purchase_create_get_includes_dimension_labels_for_modal_uom_js(self):
        resp = self.client.get(reverse('purchase:create'))
        content = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        # dimension_label must be present in the JSON fed to UOM_LIST so the
        # populateModalUomSelects() JS can build <optgroup> boundaries.
        self.assertIn('dimension_label', content)
        self.assertIn('Count / Jumlah', content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.purchase.tests.PurchaseCreateUomModalGroupingTests -v 2`
Expected: FAIL — `dimension_label` not in content

- [ ] **Step 3: Update `_get_uom_list_data()` in `apps/purchase/views.py`**

```python
def _get_uom_list_data() -> list[dict]:
    """Return active UnitOfMeasure options for the item-master quick-add modal,
    pre-sorted and grouped by dimension for the populateModalUomSelects() JS."""
    return [
        {
            'id': u.pk, 'kode': u.kode, 'nama': u.nama,
            'dimension': u.dimension, 'dimension_label': u.get_dimension_display(),
        }
        for u in UnitOfMeasure.objects.filter(is_active=True).for_dropdown()
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.purchase.tests.PurchaseCreateUomModalGroupingTests -v 2`
Expected: PASS

- [ ] **Step 5: Update the JS in `templates/purchase/purchase_form.html`**

Find `populateModalUomSelects` (around line 1109) and replace it:

```javascript
  function populateModalUomSelects() {
    if (_modalUomSelectsPopulated) return;
    ['modal_stock_uom', 'modal_purchase_uom', 'modal_sales_uom'].forEach(function (id) {
      var sel = document.getElementById(id);
      var currentLabel = null;
      var currentGroupEl = null;
      UOM_LIST.forEach(function (u) {
        if (u.dimension_label !== currentLabel) {
          currentLabel = u.dimension_label;
          currentGroupEl = document.createElement('optgroup');
          currentGroupEl.label = currentLabel;
          sel.appendChild(currentGroupEl);
        }
        var opt = document.createElement('option');
        opt.value = u.id; opt.textContent = u.kode + ' - ' + u.nama;
        currentGroupEl.appendChild(opt);
      });
    });
    _modalUomSelectsPopulated = true;
  }
```

- [ ] **Step 6: Manual smoke check**

Run: `python manage.py runserver` (or the project's usual `run` skill), open the Purchase create page, click "+ Buat item baru..." to open the quick-add modal, and confirm the "Satuan Stok" / "Satuan Pembelian" / "Satuan Penjualan" dropdowns show grouped `<optgroup>` headers (Count / Jumlah, Berat, Volume, Panjang, Luas) in that order, each with units ascending by size. Stop the server after checking.

- [ ] **Step 7: Run the full purchase test suite**

Run: `python manage.py test apps.purchase -v 2`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add apps/purchase/views.py templates/purchase/purchase_form.html apps/purchase/tests.py
git commit -m "feat(purchase): group quick-add modal UOM dropdowns by dimension"
```

---

### Task 5: BOM line "Satuan Input" select (JS-driven, fixes ordering bug)

**Files:**
- Modify: `apps/manufacturing/views.py`
- Modify: `templates/manufacturing/bom_form.html`
- Test: `apps/manufacturing/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/manufacturing/tests.py`, in the same test class as `test_bom_create_get_renders_input_uom_select_markup`:

```python
    def test_bom_create_get_uom_data_is_ordered_list_not_dict(self):
        """UOM_DATA must be a JSON array (order-preserving), not an object
        keyed by numeric id — JS sorts numeric-string object keys ascending
        regardless of insertion order, which silently discarded the
        backend's dimension/kode ordering."""
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('manufacturing:bom_create'))
        content = response.content.decode()
        uom_data_start = content.index('var UOM_DATA = ') + len('var UOM_DATA = ')
        uom_data_json = content[uom_data_start:content.index(';', uom_data_start)]
        import json
        data = json.loads(uom_data_json)
        self.assertIsInstance(data, list)
        self.assertIn('dimension_label', data[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.manufacturing.tests.ManufacturingUomTests.test_bom_create_get_uom_data_is_ordered_list_not_dict -v 2`
Expected: FAIL — `AssertionError` (currently a dict, not a list)

- [ ] **Step 3: Update `_uom_catalogue()` in `apps/manufacturing/views.py`**

```python
def _uom_catalogue():
    """All UOMs as an ordered list, grouped and sorted by dimension, for the
    row-builder input_uom select. Must stay a list (not a dict keyed by id) —
    JS iterates numeric-string object keys in ascending numeric order
    regardless of insertion order, which would silently undo the backend's
    dimension/factor ordering."""
    from apps.uom.models import UnitOfMeasure
    return [
        {
            'id': str(u.pk),
            'kode': u.kode,
            'nama': u.nama,
            'dimension': u.dimension,
            'dimension_label': u.get_dimension_display(),
        }
        for u in UnitOfMeasure.objects.for_dropdown()
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.manufacturing.tests.ManufacturingUomTests.test_bom_create_get_uom_data_is_ordered_list_not_dict -v 2`
Expected: PASS

- [ ] **Step 5: Update the JS in `templates/manufacturing/bom_form.html`**

Update the comment and variable usage around line 150-171:

```javascript
  // RM_DATA: { "id": { item_id, nama, stock, fifo_cost } } — pre-loaded from view
  var RM_DATA = {{ rm_data_json|safe }};
  // UOM_DATA: [{ id, kode, nama, dimension, dimension_label }, ...] — full UOM
  // catalogue for the "Satuan Input" select, pre-sorted and grouped by
  // dimension (kept as an array, not a dict, so JS preserves that order)
  var UOM_DATA = {{ uom_data_json|safe }};
  var lineIndex = 0;
  var _tomSelects = {};  // row-uid → TomSelect instance

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function buildUomOptionsHtml(selectedUomId) {
    var html = '<option value="">Base (default)</option>';
    var currentLabel = null;
    UOM_DATA.forEach(function (u) {
      if (u.dimension_label !== currentLabel) {
        if (currentLabel !== null) html += '</optgroup>';
        currentLabel = u.dimension_label;
        html += '<optgroup label="' + escapeHtml(currentLabel) + '">';
      }
      var selected = (selectedUomId && String(selectedUomId) === String(u.id)) ? ' selected' : '';
      html += '<option value="' + u.id + '"' + selected + '>' + escapeHtml(u.kode) + ' — ' + escapeHtml(u.nama) + '</option>';
    });
    if (currentLabel !== null) html += '</optgroup>';
    return html;
  }
```

- [ ] **Step 6: Manual smoke check**

Open the BOM create page, add a raw-material line, and confirm the "Satuan Input" dropdown shows grouped `<optgroup>` headers in dimension order, with units ascending by size within each group. Also open BOM edit for an existing BOM with a line that has a custom `input_uom` set, and confirm it still shows as selected.

- [ ] **Step 7: Run the full manufacturing test suite**

Run: `python manage.py test apps.manufacturing -v 2`
Expected: all PASS (including the existing `test_bom_create_get_renders_input_uom_select_markup` and `test_bom_update_get_prefills_existing_line_input_uom`, which only check substrings and remain valid)

- [ ] **Step 8: Commit**

```bash
git add apps/manufacturing/views.py templates/manufacturing/bom_form.html apps/manufacturing/tests.py
git commit -m "fix(manufacturing): BOM input_uom dropdown was silently unordered by JS; group by dimension"
```

---

### Task 6: Full regression pass

- [ ] **Step 1: Run the full test suite for all touched apps**

Run: `python manage.py test apps.uom apps.manufacturing apps.purchase -v 2`
Expected: all PASS

- [ ] **Step 2: Confirm no other app imports the changed shapes**

Run: `grep -rn "_uom_catalogue\|_get_uom_list_data\|UOM_DATA\|UOM_LIST" apps/ templates/ --include=*.py --include=*.html`
Expected: only the files touched in Tasks 4-5 appear (confirms no other consumer depends on the old dict shape of `_uom_catalogue()`).
