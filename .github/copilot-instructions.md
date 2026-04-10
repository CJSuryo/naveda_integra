# Copilot Instructions — Naveda Integra

> These instructions are automatically loaded by GitHub Copilot (in VS Code and on github.com)
> to ensure every prompt produces code consistent with this project's architecture and conventions.

---

## Project Overview

Naveda Integra is a **Django 6.x** financial admin panel / ERP-lite for Indonesian businesses. It uses
Bootstrap 5 for the frontend, PostgreSQL for production, and SQLite for quick local development.

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
  accounts/                     # Custom User model (email-based auth)
  entitas_bisnis/               # Business entities, branches, business types
  master_data/                  # Chart of accounts hierarchy (Aset/Kewajiban/Ekuitas Lv1→Lv2)
  jurnal/                       # Journal entries (header + detail)
  sales/                        # Sales invoices (header + detail)
  piutang/                      # Receivables (header + detail)
  inventory/                    # Inventory mutations (header + detail)
templates/                      # Django templates (Bootstrap 5)
static/                         # Static assets (CSS, JS)
docs/                           # Markdown documentation
```

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
- Add Bootstrap `form-control` class to every widget.
- Checkbox inputs use `form-check-input`.
- Date fields use `type='date'` in the widget attrs.

### Templates

- Extend `base.html`.
- Use `{% block title %}` and `{% block content %}`.
- Tables use Bootstrap classes: `table table-striped table-hover`, `table-dark` for thead.
- Status badges: `<span class="badge bg-success">Aktif</span>` / `bg-secondary` for Nonaktif.
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
