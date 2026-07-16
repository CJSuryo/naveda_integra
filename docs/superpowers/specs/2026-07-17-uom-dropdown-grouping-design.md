# UOM Dropdown Grouping by Dimension

## Problem

UOM dropdowns across the app show every unit as a flat list, mixing units from
different dimensions (count, weight, volume, length, area) together. This
makes it harder to scan for the right unit, especially as the UOM catalogue
grows. The user wants every "full catalogue" UOM dropdown to visually group
units by dimension, with a consistent, predictable order.

Additionally, while investigating, we found a real ordering bug: in
`bom_form.html`, the UOM catalogue is passed to JS as a dict keyed by numeric
ID string (`UOM_DATA = {"12": {...}, "3": {...}}`). JavaScript always
iterates object keys that look like array indices in ascending numeric order,
regardless of insertion order — so the backend's `order_by('dimension',
'kode')` is silently discarded by the browser today. This fix is included
since it shares the same root cause (JS data shape) as the grouping work.

## Scope

**In scope** — "full catalogue" dropdowns, i.e. selects that offer every UOM
across all dimensions:

1. `ItemUOMForm.uom` (`apps/uom/forms.py`) — rendered in
   `templates/uom/item_conversion_form.html`.
2. `input_uom` field (`apps/manufacturing/forms.py`) — rendered in
   `templates/manufacturing/production_create.html`.
3. Purchase "quick-add item" modal — `modal_stock_uom`, `modal_purchase_uom`,
   `modal_sales_uom` in `templates/purchase/purchase_form.html`, populated
   from `_get_uom_list_data()` in `apps/purchase/views.py`.
4. BOM line "Satuan Input" select — `buildUomOptionsHtml()` in
   `templates/manufacturing/bom_form.html`, populated from
   `_uom_catalogue()` in `apps/manufacturing/views.py`.

**Out of scope** — the per-row/per-item UOM selects driven by `ITEM_UOMS` in
`purchase_form.html` and `sales_form.html` (`uomOptions()`). These only list
the 2-3 conversions defined for one specific item (all normally the same
dimension), so grouping adds no value there.

## Ordering rules

- **Group order**: fixed, following `DIMENSION_CHOICES` declaration order in
  `apps/uom/models.py` — Count/Jumlah, Berat, Volume, Panjang, Luas. Not
  alphabetical, and not "order of first appearance".
- **Within a group**: ascending by `factor_to_base` (smallest unit first,
  e.g. gram before kilogram). Units with `factor_to_base = NULL` (per-item
  custom packaging units, e.g. carton/dus) sort after all units that do have
  a factor, ordered by `kode` among themselves.

## Design

### 1. Single source of truth for ordering — `apps/uom/models.py`

Add a queryset method `UnitOfMeasure.objects.for_dropdown()` that annotates:
- `_dim_rank`: `Case(*[When(dimension=code, then=Value(i)) for i, (code, _) in
  enumerate(DIMENSION_CHOICES)], output_field=IntegerField())`
- `_factor_null`: `Case(When(factor_to_base__isnull=True, then=Value(1)),
  default=Value(0), output_field=IntegerField())`

and orders by `('_dim_rank', '_factor_null', 'factor_to_base', 'kode')`.

Every dropdown below sources from this method, so the ordering rule is
defined exactly once.

### 2. Django form dropdowns — real `<optgroup>` markup

New `apps/uom/fields.py` with the standard Django "grouped model choice
field" recipe:

```python
class GroupedModelChoiceIterator(ModelChoiceIterator):
    def __init__(self, field, groupby):
        self.groupby = groupby
        super().__init__(field)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        for group, objs in itertools.groupby(self.queryset, self.groupby):
            yield (group, [self.choice(obj) for obj in objs])


class GroupedModelChoiceField(ModelChoiceField):
    def __init__(self, *args, choices_groupby, **kwargs):
        self.iterator = functools.partial(GroupedModelChoiceIterator, groupby=choices_groupby)
        super().__init__(*args, **kwargs)
```

Because the queryset is pre-sorted by `for_dropdown()`, `itertools.groupby`
produces correct, contiguous groups without needing to sort in Python again.

Apply to:
- `ItemUOMForm.uom` — `GroupedModelChoiceField(queryset=UnitOfMeasure.objects.for_dropdown(), choices_groupby=lambda u: u.get_dimension_display(), label='Satuan')`
- `ProductionOrderForm.input_uom` (or equivalent, `apps/manufacturing/forms.py`) — same pattern, keeping existing widget attrs (`class`, `id`).

Django's `Select` widget renders `(group_label, [(value, label), ...])`
choices as real `<optgroup label="...">` elements automatically — no
template changes needed for these two forms.

### 3. JS-driven dropdowns — optgroups from pre-grouped backend data

Since the backend now emits data already ordered and grouped-by-dimension,
the JS only needs to detect a dimension change while looping over an array
and open/close an `<optgroup>` accordingly — no client-side grouping logic.

**Purchase modal** (`apps/purchase/views.py`):
- `_get_uom_list_data()` switches to `UnitOfMeasure.objects.filter(is_active=True)` ordered via `.for_dropdown()`, and each dict gains `dimension_label`
  (`u.get_dimension_display()`) alongside the existing `id`, `kode`, `nama`,
  `dimension`.
- `populateModalUomSelects()` in `purchase_form.html` rewritten to build
  `<optgroup>` elements while iterating `UOM_LIST`, opening a new group
  whenever `dimension_label` changes from the previous entry.

**BOM line select** (`apps/manufacturing/views.py`):
- `_uom_catalogue()` changes shape from `{id: {kode, nama}}` (a dict, which
  silently breaks ordering in JS as described above) to an **ordered list**:
  `[{id, kode, nama, dimension, dimension_label}, ...]`, built from
  `UnitOfMeasure.objects.for_dropdown()`.
- `buildUomOptionsHtml()` in `bom_form.html` rewritten to iterate the `UOM_DATA` array (no longer `Object.keys(...)`) and emit `<optgroup>` boundaries
  the same way as the purchase modal.

## Testing

- `apps/uom/tests.py`: new test asserting `UnitOfMeasure.objects.for_dropdown()`
  returns units in the expected order — dimension order per
  `DIMENSION_CHOICES`, then factor ascending, with null-factor units last
  within their dimension.
- `apps/uom/tests.py` or `apps/manufacturing/tests.py`: new test asserting
  rendered HTML for the Item UOM Conversion form / Production Create form
  contains `<optgroup label="...">` markup.
- Existing tests (e.g. `manufacturing/tests.py:1499` checking `'UOM_DATA' in
  content`) only assert substrings, not data shape, so they remain valid
  without changes.

## Non-goals

- No changes to `ITEM_UOMS`-driven per-row selects (see Scope).
- No changes to the `UnitOfMeasure` model schema or `DIMENSION_CHOICES`
  values/labels.
- No change to default `Meta.ordering` on `UnitOfMeasure` (`['dimension',
  'kode']`) — that continues to serve the Master Satuan list page
  (`unit_list.html`), which is a flat table, not a dropdown, and doesn't need
  regrouping.
