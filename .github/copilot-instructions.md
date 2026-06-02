# Copilot Instructions — Naveda Integra

> These instructions are automatically loaded by GitHub Copilot (in VS Code and on github.com)
> to ensure every prompt produces code consistent with this project's architecture and conventions.

---

## Approach
- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.

---

## Project Overview

Naveda Integra is a **Django 6.x** financial admin panel / ERP-lite for Indonesian businesses. It uses
a custom CSS design system (`ni-` prefix) for the frontend, Lucide icons, Chart.js for charts,
PostgreSQL for production, and SQLite for quick local development.

---

## Architecture & Directory Layout

```
naveda_integra/                 # Django project root (settings, urls, wsgi)
  settings/
    __init__.py                 # defaults to development
    base.py                     # shared settings (PostgreSQL by default)
    development.py              # SQLite override, DEBUG=True
    production.py               # reads env vars, DEBUG=False
apps/
  accounts/                     # Custom User model (email-based auth), Role, UserEntitasBisnis (RBAC)
  entitas_bisnis/               # Business entities, branches, business types
  master_data/                  # Chart of accounts hierarchy (Aset/Kewajiban/Ekuitas/Pendapatan/Beban Lv1→Lv2)
  jurnal/                       # Journal entries (header + detail), Manual Journal, Rekap Jurnal, Neraca Saldo
  sales/                        # Sales invoices (header + detail)
  piutang/                      # Receivables (header + detail)
  inventory/                    # Inventory mutations (header + detail)
templates/                      # Django templates (ni- design system)
static/
  css/                          # Modular CSS files (see Front-End section below)
  js/                           # Modular JS modules (sidebar.js, toast.js, etc.)
docs/                           # Markdown documentation
```

---

## Role-Based Access Control (RBAC) — MUST FOLLOW

The project implements RBAC via the `accounts.Role` model and `accounts.UserEntitasBisnis` junction table.

### Roles
| Role Code          | Label            | Access Scope |
|--------------------|------------------|-------------|
| `admin`            | Admin            | Full access to all features and all business entities. |
| `operator`         | Operator         | Same as Admin but some admin-only menus are hidden. |
| `business_owner`   | Pemilik Bisnis   | Can only see/manage data for EntitasBisnis linked via UserEntitasBisnis. |
| `business_employee`| Karyawan Bisnis  | Same as Business Owner but with restricted write access. |

### Implementation Rules
- **Always** check the user's role before granting access to data or features.
- Use `user.is_admin`, `user.is_operator`, `user.is_internal`, `user.is_business_owner`, `user.is_business_employee`, `user.is_business_user` properties on the User model.
- Business users (`business_owner` / `business_employee`) must only see EntitasBisnis records linked via `UserEntitasBisnis`.
- Internal users (`admin` / `operator`) see all EntitasBisnis records.
- Admin-only sidebar items are guarded by `{% if user.is_superuser or user.is_admin %}` in templates.
- When creating new views that show business-specific data, always filter by the user's linked entities for business users.

---

## Conventions — MUST FOLLOW

### Python / Django

- **Python 3.12+** — use modern type hints (e.g. `list[str]`, `dict[str, int]`, not `List[str]`).
- **Django 6.x** — do not use deprecated APIs.
- All models use `BigAutoField` as the default primary key (`DEFAULT_AUTO_FIELD`).
- Use **function-based views** with `@login_required` decorator (not class-based views).
- Use `select_related()` / `prefetch_related()` for querysets that cross FK boundaries.
- Models that are children (e.g. Cabang, Lv2, Detail) use `on_delete=models.CASCADE`.
- Lookup tables (e.g. TipeEntitas) that parent rows depend on use `on_delete=models.PROTECT`.
- `__str__` is required on every model.
- `class Meta` must include `verbose_name` and `verbose_name_plural` (in Bahasa Indonesia).

### Naming

- Model names: PascalCase, Bahasa Indonesia (e.g. `EntitasBisnis`, `TipeEntitas`).
- Field names: snake_case, Bahasa Indonesia where it makes sense (e.g. `nama`, `alamat_lengkap`, `status_aktif`).
- URL names: snake_case with colons for namespacing (e.g. `entitas_bisnis:list`, `master_data:aset_lv1_detail`).
- URL paths: kebab-case (e.g. `/entitas-bisnis/`, `/tipe-entitas/`).
- Template directories mirror the app name: `templates/<app_name>/`.

### Forms

- Always use `forms.ModelForm`.
- Add `ni-input` class to text/select widgets, `ni-checkbox` for checkboxes.
- Date fields use `type='date'` in the widget attrs.
- Wrap each field in `<div class="ni-form-group">` with `<label class="ni-form-label">`.
- Error messages use `<div class="ni-form-error">{{ field.errors }}</div>`.

### Templates

- Extend `base.html`.
- Use `{% block title %}`, `{% block content %}` (authenticated), `{% block content_auth %}` (login/register).
- Use `{% block extra_css %}` and `{% block extra_js %}` for page-specific assets.
- **Do NOT use Bootstrap classes.** Use the `ni-` design system exclusively (see Front-End section).
- Status badges: `<span class="ni-badge ni-badge--success">Aktif</span>` / `ni-badge--secondary` for Nonaktif.
- Use `{{ field|default:'-' }}` for optional fields in detail views.
- All user-facing text is in **Bahasa Indonesia**.

### Admin

- Register every model with `@admin.register`.
- Child models get `TabularInline` on the parent's admin class.
- Always set `extra = 0` on inlines.
- Use `list_display`, `list_filter`, `search_fields` on every admin class.

### Tests

- One `tests.py` per app.
- Use `django.test.TestCase` (not `unittest.TestCase`).
- Test classes: `<Model>ModelTests`, `<Model>ViewTests`.
- Always test `__str__`, unique constraints, FK cascades, and PROTECT behaviour.
- View tests must cover: list, detail, create (GET+POST), update, delete, and login-required.
- Create helper objects in `setUp`.
- Run tests with: `python manage.py test`.

### Settings

- `base.py` — shared config, reads `os.environ` for DB settings, defaults to PostgreSQL.
- `development.py` — imports base, overrides DB to SQLite if `DB_ENGINE` env var is not set.
- `production.py` — imports base, reads `SECRET_KEY` and `ALLOWED_HOSTS` from env.
- **Never** commit real secrets or `.env` files.

### Database

- **Production / Staging:** PostgreSQL 16+.
- **Local Development:** SQLite (via `development.py` defaults).
- Always use Django migrations. Never write raw SQL in application code.
- Use `Decimal` for monetary values (not `float`).

### Database Indexing (Critical for Millions of Rows)

The jurnal (double-entry ledger), akun, and sales tables are high-volume. Follow these rules:

- **Every FK used in `list_display` or queryset filters** must have a corresponding `db_index=True` or a composite `models.Index`.
- **Date fields** that appear in range queries (e.g. `tanggal`, `tanggal_transaksi`) should always have `db_index=True`.
- **Composite indexes** go in `class Meta: indexes = [...]` with explicit `name='idx_<table>_<columns>'`.
- Name indexes as `idx_<2-3 letter table abbrev>_<column hints>` (e.g. `idx_jh_tanggal_tipe`, `idx_jd_akun_header`).
- For the **ledger** (jurnal):
  - `JurnalHeader`: indexed on `(tanggal, tipe_transaksi)`, `(entitas_bisnis, tanggal)`, and `item`.
  - `JurnalDetail`: indexed on `(akun, jurnal_header)` for trial-balance/ledger aggregation, and `(jurnal_header, akun)` for header→detail joins.
  - `Akun`: indexed on `kategori_id`, `kategori_akun`, and composite `(kategori_id, kategori_akun)`.
- For **sales**: indexed on `(entitas_bisnis, tanggal_transaksi)` and `(status_pengiriman, tanggal_transaksi)`.
- **Admin N+1 prevention**: every `ModelAdmin` that displays FK fields in `list_display` must set `list_select_related`. Use `raw_id_fields` for high-cardinality FKs in admin forms.
- **Views**: always use `select_related()` when accessing FK fields, and `prefetch_related()` for reverse/M2M relations.

### Security

- Validate `next` redirect parameters with `url_has_allowed_host_and_scheme` + `resolve()` + `reverse()`.
- Use `{% csrf_token %}` in every form.
- Never trust user input for redirect URLs.

---

## Front-End Design System — MUST FOLLOW

The project uses a custom CSS design system with the `ni-` prefix. **Do NOT use Bootstrap.**
External CDN libraries: Lucide Icons (SVG), Chart.js 4.x (charts only).

### CSS Architecture

CSS is split into modular files under `static/css/`. Each file owns a single concern:

| File | Purpose |
|------|---------|
| `fonts.css` | Google Fonts (Inter), base typography |
| `layout.css` | CSS custom properties (design tokens), resets, app shell grid (sidebar + main) |
| `menubar.css` | Sidebar navigation: logo, nav items, submenus, user area, collapse/expand |
| `button.css` | `.ni-btn` base + variants (`--primary`, `--success`, `--warning`, `--danger`, `--secondary`, `--outline`, `--outline-danger`, `--ghost`), sizes (`--sm`, `--lg`), icon buttons, button groups |
| `card.css` | `.ni-card` + stat cards (`.ni-stat-card`), card grids |
| `chart.css` | Chart.js container styles |
| `dropdown.css` | Dropdown menus |
| `forms.css` | `.ni-form-group`, `.ni-form-label`, `.ni-input`, `.ni-select`, `.ni-checkbox`, `.ni-form-error` |
| `modal.css` | Modal dialogs with backdrop blur |
| `paginator.css` | Pagination |
| `photos.css` | Avatars, thumbnails, upload areas |
| `report.css` | KPI cards, report summaries, print styles |
| `section.css` | `.ni-page-header`, `.ni-section-header`, `.ni-detail-grid`, breadcrumbs, tabs, dividers |
| `table.css` | `.ni-table` + wrapper, badges (`.ni-badge`), toolbar, sticky headers |
| `toast.css` | Toast notifications (`.ni-toast`) + inline alerts (`.ni-alert`) |
| `wrapper.css` | `.ni-content-wrapper`, containers, auth layout, two-col/three-col grids |
| `animation.css` | Keyframe animations: `ni-animate-fade-in`, `ni-animate-slide-up`, skeleton loaders |
| `utilities.css` | Spacing (`.ni-m-*`, `.ni-p-*`), text (`.ni-text-center`, `.ni-text-muted`, `.ni-text-right`), flex, display |
| `tomselect.css` | Tom Select theming + dropdown overflow rules. **All TomSelect overrides go here, not in templates.** Apply `.ni-filter-card` on any `.ni-card` that hosts a TS dropdown so the menu isn't clipped. |
| `transaction-forms.css` | Shared styles for sales/purchase/jurnal multi-row entry forms |

### Styles — STRICT RULES

**Never put styles in HTML files.** This includes:

- ❌ `style="..."` attributes on any element (NO `<div style="...">`, NO `<i style="width:16px;height:16px">`).
- ❌ `<style>...</style>` blocks inside templates.
- ❌ `<link rel="stylesheet" href="https://cdn.../some.css">` per-page CDN imports — register globally in `base.html`.
- ❌ Page-specific hotfix CSS (`#someId .ts-dropdown { z-index: ... }`) — fold into the appropriate global file.

**Where styles live (single source of truth):**

- All styles → `static/css/<file>.css`, picked by concern from the table above.
- Tom Select theming + dropdown overflow → `static/css/tomselect.css` (loaded globally in `base.html`).
- Tom Select CDN (CSS + JS) → loaded once in `base.html`. Never re-add per template.
- Lucide icons are 16px by default via `.ni-btn svg { width: 16px }` — do NOT add `style="width:16px;height:16px"` on `<i data-lucide="...">`.

**In HTML, use class names only.** If a needed class doesn't exist, add it to the right CSS file (utilities for one-offs, the concern file for component bits) and use the class. Reuse before creating.

**When you spot inline styles** in a file you're editing, migrate them to classes in the appropriate CSS file as part of your change. Do not add new ones.

### Design Tokens (CSS Custom Properties)

All colors, spacing, shadows, and radii are defined as CSS custom properties in `layout.css` under `:root`.
Always use these variables — never hardcode colors:

```css
--ni-primary: #0054a6;          /* Brand blue */
--ni-primary-light: #e8f0fe;
--ni-primary-dark: #003d7a;
--ni-accent: #6366f1;           /* Purple accent */
--ni-success: #10b981;
--ni-warning: #f59e0b;
--ni-danger: #ef4444;
--ni-info: #06b6d4;
--ni-bg: #f8fafc;               /* Page background */
--ni-bg-card: #ffffff;
--ni-bg-sidebar: #0f172a;       /* Dark sidebar */
--ni-text: #1e293b;
--ni-text-muted: #64748b;
--ni-border: #e2e8f0;
--ni-radius: 10px;
--ni-radius-sm: 6px;
--ni-radius-lg: 16px;
--ni-shadow-sm / --ni-shadow / --ni-shadow-md / --ni-shadow-lg
--ni-transition: 200ms ease;
--ni-font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

### CSS Class Naming Convention

- **BEM-like with `ni-` prefix:** `ni-block`, `ni-block__element`, `ni-block--modifier`.
- Examples: `ni-card`, `ni-card__header`, `ni-card--hover`, `ni-btn--primary`, `ni-btn--sm`.
- When adding new components, follow this pattern.
- Put new styles in the appropriate modular CSS file (e.g., new button style → `button.css`).

### Template Patterns

Every template must follow these patterns. **Copy these exactly when creating new pages.**

#### List Page Pattern

```html
{% extends 'base.html' %}
{% block title %}Page Title{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Page Title</h1>
    <p class="ni-page-header__subtitle">Short description</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'app:create' %}" class="ni-btn ni-btn--success">
      <i data-lucide="plus" style="width:16px;height:16px"></i> Tambah
    </a>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Column</th><th>Aksi</th></tr></thead>
      <tbody>
        {% for obj in object_list %}
        <tr>
          <td>{{ obj.field }}</td>
          <td>
            <div class="ni-btn-row">
              <a href="{% url 'app:update' obj.pk %}" class="ni-btn ni-btn--warning ni-btn--sm">Edit</a>
              <a href="{% url 'app:delete' obj.pk %}" class="ni-btn ni-btn--outline-danger ni-btn--sm">Hapus</a>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="2" class="ni-text-center ni-text-muted">Belum ada data.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

#### Detail Page Pattern

```html
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <dl class="ni-detail-grid">
      <dt>Label</dt><dd>{{ object.field|default:'-' }}</dd>
      <dt>Status</dt><dd><span class="ni-badge ni-badge--success">Aktif</span></dd>
    </dl>
  </div>
</div>
```

#### Form Page Pattern

```html
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <form method="post">
      {% csrf_token %}
      {% for field in form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
      {% endfor %}
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'app:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>
```

#### Delete Confirmation Pattern

```html
<div class="ni-card ni-animate-fade-in" style="max-width:560px;">
  <div class="ni-card__body" style="text-align:center;padding:40px 32px;">
    <div style="width:48px;height:48px;border-radius:50%;background:#fef2f2;color:var(--ni-danger);display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
      <i data-lucide="trash-2" style="width:24px;height:24px"></i>
    </div>
    <p style="font-size:1rem;color:var(--ni-text);margin-bottom:24px;">Hapus <strong>{{ object }}</strong>?</p>
    <form method="post">
      {% csrf_token %}
      <div class="ni-btn-row" style="justify-content:center;">
        <button type="submit" class="ni-btn ni-btn--danger">Ya, Hapus</button>
        <a href="{% url 'app:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>
```

### JavaScript Architecture

JS is split into modular files under `static/js/`:

| File | Purpose |
|------|---------|
| `sidebar.js` | Sidebar collapse/expand, mobile toggle, submenu toggle. Auto-loads. |
| `toast.js` | Auto-dismiss toast notifications after 5 seconds. Auto-loads. |
| `chart-init.js` | Chart.js helpers: `niCharts.line()`, `niCharts.doughnut()`, `niCharts.bar()`. Load on dashboard pages via `{% block extra_js %}`. |
| `modal.js` | Modal open/close via `data-modal-open` / `data-modal-close` attributes. Load when modals are needed. |
| `table-utils.js` | Clickable rows via `data-href` attribute on `<tr>`. Load on table pages. |

**Rules for JS:**
- Use **IIFE** pattern `(function () { 'use strict'; ... })();` for every module to avoid global scope pollution.
- Export public APIs on `window` only when needed (e.g., `window.niModal`, `window.niCharts`).
- Use `data-*` attributes for JS hooks — never rely on `ni-` CSS classes for behaviour.
- Include page-specific JS via `{% block extra_js %}` with `{% load static %}`.
- CDN scripts (Chart.js, Lucide) are loaded before project JS.
- Lucide icons are initialized in `sidebar.js` via `lucide.createIcons()`.

### Icons

Use **Lucide** icons (loaded via CDN in base.html). Syntax:
```html
<i data-lucide="icon-name" style="width:16px;height:16px"></i>
```
Common icons: `plus`, `pencil`, `trash-2`, `chevron-right`, `building-2`, `book-open`, `database`, `tags`, `wallet`, `credit-card`, `landmark`, `layout-dashboard`, `user-plus`, `menu`, `chevrons-left`.

Browse all icons: https://lucide.dev/icons/

### Responsive Design

- **Desktop (>1024px):** Full sidebar (260px) + content area.
- **Tablet (768–1024px):** Collapsed sidebar (72px icons-only) + content area.
- **Mobile (<768px):** Sidebar hidden; fixed top bar with hamburger menu to open sidebar as overlay.
- Use CSS Grid / Flexbox for layouts. No fixed pixel widths for content.
- Tables wrapped in `.ni-table-wrapper` for horizontal scroll on mobile.

### Mobile Experience — MUST FOLLOW

**Every page and component must be tested for mobile usability.** Follow these rules:

#### Navigation
- The mobile top bar (`.ni-mobile-topbar`) is `position: fixed` at the top of the viewport on screens < 768px. It contains the hamburger toggle and app title.
- `.ni-main` has `padding-top: 56px` on mobile to account for the fixed top bar.
- The sidebar slides in from the left as an overlay when the hamburger is tapped, with a backdrop overlay (`.ni-sidebar-overlay`).
- Sidebar closes when tapping the backdrop overlay or navigating to a new page.

#### Layout Rules for Mobile
- **Never use fixed-width columns** (`grid-template-columns: 200px 1fr`) in inline styles. Use the responsive `ni-form-row` class or CSS Grid with `minmax()` / `auto-fit`.
- **Multi-column grids** (2-col, 3-col) must collapse to single-column on mobile. Use `ni-form-row`, `ni-two-col`, or `ni-three-col` utility classes which already have mobile breakpoints.
- **Inline `style` grids** like `style="display:grid;grid-template-columns:1fr 1fr"` should use `ni-form-row` class instead, which collapses to `1fr` on mobile.
- **Flex containers** with multiple items should use `flex-wrap: wrap` so items stack on narrow screens.

#### Tables
- **Always** wrap `<table>` in `.ni-table-wrapper` (or a `div` with `overflow-x: auto`) so tables scroll horizontally on mobile.
- For data-entry tables in forms (purchase items, journal details), set `min-width` on the table (e.g., `min-width: 600px`) inside a scrollable wrapper so columns remain usable.
- Prefer fewer columns on mobile-visible tables. Use `ni-hide-mobile` utility class on non-essential columns.

#### Forms
- Form fields should be full-width on mobile. The `ni-input` class already handles this.
- `ni-form-row` collapses to single-column on mobile (<768px). Always prefer this over inline grid styles.
- Button rows (`ni-btn-row`) should wrap and buttons should be full-width or at least tappable size (min 44px height).
- Date inputs, selects, and text inputs must have sufficient touch target size (the default `ni-input` padding handles this).

#### Modals
- On mobile, modals slide up from the bottom (bottom sheet pattern). This is already handled by `modal.css`.
- Modal size variants (`--sm`, `--lg`, `--xl`) all become full-width on mobile.

#### Cards and Stat Cards
- Card grids (`ni-card-grid--2`, `--3`, `--4`) collapse to single-column on mobile via existing breakpoints in `card.css`.
- Stat card text should remain readable. The responsive rules are in `card.css`.

#### Touch Targets
- All interactive elements (buttons, links, toggles) must have a minimum touch target of **44×44px** on mobile. The `ni-btn` base class meets this requirement.
- Avoid placing small interactive elements too close together. Use adequate `gap` spacing.

#### Responsive Utility Classes
Available responsive visibility classes in `utilities.css`:
```css
.ni-hide-mobile       /* Hidden on < 768px */
.ni-hide-tablet       /* Hidden on 768–1023px */
.ni-hide-desktop      /* Hidden on ≥ 1024px */
.ni-show-mobile-only  /* Visible only on < 768px */
.ni-show-desktop-only /* Visible only on ≥ 1024px */
```

#### Testing Checklist for New Pages
When creating or modifying any page, verify:
1. ✅ Hamburger menu is visible and functional on mobile viewport.
2. ✅ Page content is not hidden behind the fixed top bar (56px padding).
3. ✅ All tables scroll horizontally without breaking the page layout.
4. ✅ Form fields stack vertically and are full-width on mobile.
5. ✅ Buttons are tappable and not clipped or overflowing.
6. ✅ Modals are usable (bottom sheet on mobile).
7. ✅ No horizontal page scroll (only table wrappers should scroll).
8. ✅ Text is readable without zooming (minimum 13px / 0.8125rem).

---

## Header + Detail Pattern

Many apps follow this pattern (sales, jurnal, piutang, inventory):

1. **Header model** — contains metadata (date, reference numbers, FK to EntitasBisnis).
2. **Detail model** — FK to header with `on_delete=CASCADE`, `related_name='details'`.
3. **Admin** — header admin class has `TabularInline` for details.
4. **`__str__`** — header uses reference number, detail references header ID.

When creating new apps, follow this pattern.

---

## Dependencies

```
Django>=6.0,<7.0
django-extensions>=4.0,<5.0
django-debug-toolbar>=4.0,<7.0
ipython>=9.0,<10.0
psycopg2-binary>=2.9,<3.0
```

**CDN Libraries (no pip install needed):**
- Lucide Icons 0.460.0 — SVG icon library
- Chart.js 4.4.7 — charts (loaded on dashboard pages only)

Do not add new dependencies without explicit approval. Prefer Django's built-in utilities.

---

## Common Commands

```bash
# Run development server
python manage.py runserver

# Run all tests
python manage.py test

# Make migrations after model changes
python manage.py makemigrations <app_name>

# Apply migrations
python manage.py migrate

# Open enhanced shell
python manage.py shell_plus

# Collect static files
python manage.py collectstatic --noinput
```
