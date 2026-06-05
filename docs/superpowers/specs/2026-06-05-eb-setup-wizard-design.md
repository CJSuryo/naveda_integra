# Entitas Bisnis Setup Wizard — Design Spec
**Date:** 2026-06-05  
**Status:** Approved  
**Scope:** Guided checklist dashboard to configure everything an Entitas Bisnis needs to operate the Kasir application.

---

## 1. Overview

An admin-facing setup wizard for configuring a new (or existing) Entitas Bisnis Level 1 from end to end. Entry point: a "Setup Wizard" button on the lv1 edit page. The wizard is a **checklist dashboard** — not a step-by-step linear flow. Each item links to the relevant form; forms redirect back to the wizard after saving. The wizard is always accessible (`/entitas-bisnis/<pk>/setup/`) and shows current completion state on every visit.

---

## 2. Architecture

### 2a. New URL & View

| | |
|---|---|
| **URL** | `GET /entitas-bisnis/<pk>/setup/` |
| **URL name** | `entitas_bisnis:setup_wizard` |
| **View** | `setup_wizard(request, pk)` in `apps/entitas_bisnis/views.py` — fetches `EntitasBisnis` with `select_related('pos_config', 'tipe_entitas')` and `prefetch_related('children_lv2__children_lv3')` |
| **Template** | `templates/entitas_bisnis/setup_wizard.html` |
| **Auth** | `@login_required` + `_check_perm(request.user, 'entitas_bisnis_manage')` |

### 2b. Entry Point

In `templates/entitas_bisnis/form.html` (lv1 edit page), add button after the form's save button when `object.pk` exists:

```html
<a href="{% url 'entitas_bisnis:setup_wizard' object.pk %}" class="ni-btn ni-btn--primary ni-btn--sm">
  <i data-lucide="rocket" style="width:14px;height:14px"></i> Setup Wizard
</a>
```

### 2c. `?next=` Redirect Support

Two existing views need `?next=` support added (minimal change — check for `next` in POST redirect only):

- `apps/pos_config/views.py` → `merchant_config`: after `form.save()`, redirect to `request.GET.get('next') or redirect('pos_config:merchant_config', pk=pk)`
- `apps/accounts/views.py` → `user_create`: after `form.save()`, redirect to `request.GET.get('next') or redirect('accounts:user_detail', pk=user_obj.pk)`. The `user_create` template's `<form>` action must include `?next=...&eb=...` query params so they survive the POST (use `action="?next={{ request.GET.next }}&eb={{ request.GET.eb }}"` or render them as hidden inputs).

Also handle auto-associating the EB when `?eb=<pk>` is present in `user_create`:
```python
eb_pk = request.GET.get('eb')
if eb_pk:
    from apps.accounts.models import UserEntitasBisnis
    try:
        UserEntitasBisnis.objects.get_or_create(user=user_obj, entitas_bisnis_id=int(eb_pk))
    except (ValueError, TypeError):
        pass
```

### 2d. lv2/lv3 Inline Add

Items 1 & 2 do NOT navigate away. They expand inline (chevron toggle) showing existing lv2/lv3 list + an add button that opens the existing AJAX modals (`niEB.openAddLv2`, `niEB.openAddLv3`). The wizard page includes the same modal HTML as `list.html` and loads the same `niEB` JS.

After an AJAX add succeeds, the page reloads to recompute checklist status.

---

## 3. Completion Logic

`setup_wizard` view computes a `checks` dict by querying the DB. All checks are read-only — no mutations in the view.

```python
def _compute_wizard_checks(eb):
    from apps.entitas_bisnis.models import EntitasBisnisLv3
    from apps.pos_config.models import MerchantPOSConfig
    from apps.purchase.models import SubTransactionType
    from apps.accounts.models import UserEntitasBisnis

    lv2_list = list(eb.children_lv2.filter(status_aktif=True).prefetch_related('children_lv3'))
    lv3_list = EntitasBisnisLv3.objects.filter(parent_lv2__entitas_bisnis=eb, status_aktif=True)

    pos_cfg = getattr(eb, 'pos_config', None)
    pos_config_complete = bool(
        pos_cfg and
        pos_cfg.sub_transaction_type_id and
        pos_cfg.revenue_account_id and
        pos_cfg.offset_coa_account_id and
        pos_cfg.default_payment_account_id
    )

    stt_exists = SubTransactionType.objects.filter(module='sales').exists()
    stt_assigned = bool(pos_cfg and pos_cfg.sub_transaction_type_id)

    users = UserEntitasBisnis.objects.filter(
        entitas_bisnis=eb, user__is_active=True
    ).select_related('user')

    return {
        'lv2_list': lv2_list,
        'lv3_count': lv3_list.count(),
        'lv2_ok': len(lv2_list) > 0,
        'lv3_ok': lv3_list.exists(),
        'pos_config_ok': pos_config_complete,
        'pos_cfg': pos_cfg,
        'stt_ok': stt_exists and stt_assigned,
        'stt_exists': stt_exists,
        'users': users,
        'users_ok': users.exists(),
        'qris_ok': bool(pos_cfg and pos_cfg.qris_image),
    }
```

**"Setup Complete"** = `lv2_ok AND lv3_ok AND pos_config_ok AND stt_ok AND users_ok`

---

## 4. Checklist Items

### Required (5 items)

**1. Toko (Lv2)**
- ✓ when: `lv2_ok = True`
- Sub-detail: "N toko aktif" or "Belum ada toko"
- Action: Expands inline — shows lv2 list + "Tambah Toko" button (AJAX modal `niEB.openAddLv2`)
- No page navigation

**2. Outlet (Lv3)**
- ✓ when: `lv3_ok = True`
- Sub-detail: "N outlet aktif" or "Belum ada outlet"
- Action: Expands inline — shows lv3 list grouped by lv2 + "Tambah Outlet" button per store (AJAX modal `niEB.openAddLv3`)
- No page navigation

**3. POS Config**
- ✓ when: `pos_config_ok = True`
- Sub-detail when incomplete: lists which fields are missing (e.g. "Revenue Account belum diisi")
- Sub-detail when complete: shows STT name, tax %, accounts
- Action button: "Setup POS Config →" → `/pos/config/<eb.pk>/?next=/entitas-bisnis/<eb.pk>/setup/`

**4. Sub-Transaction Type (Kasir)**
- ✓ when: `stt_ok = True`
- Two sub-states:
  - No STT exists at all → "Buat Sub-Transaction Type baru di Master Data terlebih dahulu, lalu assign di POS Config"
  - STT exists but not assigned → "STT sudah ada tapi belum di-assign di POS Config"
  - Both done → shows STT name
- Action button: "Buat STT →" (if no STT) → Master Data STT create, OR "Assign di POS Config →" (if STT exists but not assigned)

**5. Kasir User**
- ✓ when: `users_ok = True`
- Sub-detail: lists linked users (name + email) or "Belum ada user"
- Action button: "Tambah User Kasir →" → `/accounts/users/create/?next=/entitas-bisnis/<eb.pk>/setup/&eb=<eb.pk>`

### Recommended (1 item)

**6. QRIS Image**
- ✓ when: `qris_ok = True`
- Sub-detail: "Upload gambar QR untuk pembayaran QRIS"
- Action: "Upload QRIS →" → `/pos/config/<eb.pk>/?next=/entitas-bisnis/<eb.pk>/setup/`

---

## 5. Page Layout

### Header
```
← Kembali ke Edit Entitas Bisnis
[EB name]  ·  Setup Wizard
```

### Progress bar
```
[████████░░]  4 dari 5 langkah wajib selesai
```
Computed from count of required items that are `True`.

### Completion banner
**All done (green card):**
```
✓ [EB name] siap digunakan!
  Semua konfigurasi wajib telah selesai.
  [Buka Kasir →]  [Kembali ke Entitas Bisnis]
```

**Not done (amber card):**
```
⚠ Konfigurasi belum lengkap
  Selesaikan semua item wajib di bawah sebelum menggunakan kasir.
```

### Two-section checklist

**Wajib** section — 5 items. **Direkomendasikan** section — 1 item.

Each item card:
```
[✓/✗ icon]  [Title]           [Done / Belum badge]
             [Description]
             [Sub-detail]
                               [Action button →]
```

Items 1 & 2 have a chevron that expands the inline list + add button below the card.

---

## 6. File Checklist

| File | Change |
|---|---|
| `apps/entitas_bisnis/views.py` | Add `setup_wizard` view + `_compute_wizard_checks` helper |
| `apps/entitas_bisnis/urls.py` | Register `setup/<int:pk>/` → `setup_wizard` |
| `templates/entitas_bisnis/setup_wizard.html` | New — full wizard page |
| `templates/entitas_bisnis/form.html` | Add "Setup Wizard" button when `object.pk` exists |
| `apps/pos_config/views.py` | Add `?next=` redirect support to `merchant_config` |
| `apps/accounts/views.py` | Add `?next=` + `?eb=` support to `user_create` |

---

## 7. Out of Scope

- Step-by-step linear wizard flow (checklist dashboard chosen instead)
- Wizard "completion" persisted in DB (computed live on every GET)
- Inventory stocking (too complex to validate; covered in setup guide doc)
- Outlet-level POS Config (OutletPOSConfig) — accessible via lv3 edit page, not wizard
