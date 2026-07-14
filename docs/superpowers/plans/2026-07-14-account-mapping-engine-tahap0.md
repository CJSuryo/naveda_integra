# Account Mapping Engine — Tahap 0 (Fondasi) Implementation Plan

> ## ⚠️ SUPERSEDED — JANGAN DIEKSEKUSI
>
> Spec yang mendasari plan ini (`specs/2026-07-14-account-mapping-engine-design.md`) telah
> digantikan oleh `specs/2026-07-15-posting-engine-design.md`. Plan ini **belum punya satu pun
> pemanggil produksi**, sehingga membatalkannya sekarang **tidak berbiaya**.
>
> Yang **masih dapat dipakai ulang** saat plan Tahap 0 ditulis ulang: scaffold app Django,
> pola permission (`has_ni_perm` + `_check_perm`, **tapi diperketat ke superuser**), pola simpan
> AJAX ala modal CoA, konvensi tes `TestCase` di paket `tests/`, dan catatan **partial unique
> index** untuk baris scope global (SQL memperlakukan `NULL != NULL`).
>
> Yang **berubah** dan tidak boleh disalin apa adanya:
> - `AccountMapping` (satu FK `entitas_bisnis`) → `PemetaanAkun` dengan **rantai scope** +
>   **effective-dated**.
> - `Role` → `BarisJurnal`: bukan hanya akun, tetapi **arah (D/K/bertanda) + sumber angka +
>   sumber akun**. Baris bertanda punya **dua** slot akun (laba vs rugi = akun berbeda).
> - Registry jenis transaksi **di kode** → `JenisTransaksi` **di tabel**, disusun superuser
>   lewat UI. Yang tetap di kode hanyalah **katalog angka** yang diumumkan tiap modul.
> - Komponen baru yang belum ada di plan ini: **preview jurnal** di UI, dan **cek balance**
>   saat `JurnalHeader` di-post.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the Account Mapping Engine described in `docs/superpowers/specs/2026-07-14-account-mapping-engine-design.md`: the `AccountMapping` model, the code-level registry (`register_mapping`, `Role`), the `resolve_account` resolver, and an admin-only "Transaction Settings" matrix page — with **zero production callers**, so this stage carries zero risk to any running module.

**Architecture:** New Django app `apps/mapping` (label `mapping`). A process-global registry dict (populated by each domain app's `AppConfig.ready()` in later stages — empty in this stage except in tests) defines which `(module, transaction_type, role)` triples are valid and drives both the UI and resolver validation. `AccountMapping` rows store the admin's choice of `Akun` per triple, optionally scoped to an `EntitasBisnis` (NULL = global default). `resolve_account()` is the only read path: EB-specific → global → caller-supplied fallback → clear error. A thread-local, per-request cache (cleared on Django's `request_finished` signal) avoids repeat queries within one request.

**Tech Stack:** Django (existing project conventions: plain function-based views, Django `TestCase` in a `tests/` package, custom `has_ni_perm` permission system, AJAX-via-fetch/FormData/JSON pattern already used by the Chart of Accounts modal).

## Global Constraints

- **STT is not touched.** No existing model, view, or service in `apps/purchase`, `apps/sales`, `apps/pendapatan` changes in this plan.
- **Zero production callers in this stage.** No app other than `apps/mapping` itself may import or call `register_mapping`/`resolve_account` as part of this plan — that begins in Tahap 1 (Ekuitas pilot, a separate future plan). The registry is empty in production; only tests populate it.
- **Permission system:** this codebase uses a custom `has_ni_perm(code)` method on the user model (`apps/accounts/models.py:130`) + a `_check_perm(user, code)` view helper (`apps/accounts/views.py:29`), backed by `config/roles_permissions.toml` — **not** `@staff_member_required` or Django's built-in `permission_required`. Reuse the existing, currently-unused `settings_view` / `settings_update` permission codes (`config/roles_permissions.toml:277,282`) rather than adding new TOML entries.
- **Postgres backend** (`naveda_integra/settings/base.py:105`). A plain `unique_together`/`UniqueConstraint` on `(module, transaction_type, role, entitas_bisnis)` does **not** stop two rows both having `entitas_bisnis=NULL` for the same triple — SQL treats `NULL != NULL`. The "one global row per triple" invariant must be enforced with a **partial unique index** (`condition=Q(entitas_bisnis__isnull=True)`), plus a normal unique constraint for the non-null (per-EB) case.
- **Testing convention:** Django `TestCase` (not pytest — this repo has no pytest dependency), tests live in a `tests/` package (the newer convention, matching `apps/pos_config/tests/`, `apps/pajak/tests/`), one file per concern.
- **AJAX save convention:** mirror the Chart of Accounts modal (`apps/master_data/views.py:40-52`, `templates/master_data/chart_of_accounts.html:735-758`) — request carries header `X-Requested-With: XMLHttpRequest`, response is `JsonResponse({'success': True})` or `JsonResponse({'success': False, 'errors': {...}})`.

---

### Task 1: App scaffold — `apps.mapping` registered and wired

**Files:**
- Create: `apps/mapping/__init__.py`
- Create: `apps/mapping/apps.py`
- Create: `apps/mapping/urls.py`
- Create: `apps/mapping/migrations/__init__.py`
- Modify: `naveda_integra/settings/base.py:33-49` (INSTALLED_APPS)
- Modify: `naveda_integra/urls.py:31` (root urlconf)

**Interfaces:**
- Produces: Django app `apps.mapping` (label `mapping`), URL namespace `mapping` mounted at `/mapping/`, importable but with no views/models yet (added in later tasks).

- [ ] **Step 1: Create the app package**

`apps/mapping/__init__.py`:
```python
```
(empty file)

`apps/mapping/migrations/__init__.py`:
```python
```
(empty file)

`apps/mapping/apps.py`:
```python
from django.apps import AppConfig


class MappingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mapping'
    label = 'mapping'
    verbose_name = 'Account Mapping'
```

`apps/mapping/urls.py`:
```python
"""Account Mapping Engine URLs."""
from django.urls import path

app_name = 'mapping'

urlpatterns = []
```

- [ ] **Step 2: Register the app in `INSTALLED_APPS`**

In `naveda_integra/settings/base.py`, find:
```python
    'apps.aset_lainnya', 'apps.ekuitas', 'apps.manufacturing', 'apps.dashboard',
    'apps.customers',
```
Change to:
```python
    'apps.aset_lainnya', 'apps.ekuitas', 'apps.manufacturing', 'apps.dashboard',
    'apps.customers', 'apps.mapping',
```

- [ ] **Step 3: Mount the URL namespace**

In `naveda_integra/urls.py`, find:
```python
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('', include('apps.accounts.urls_home')),
```
Change to:
```python
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('mapping/', include('apps.mapping.urls', namespace='mapping')),
    path('', include('apps.accounts.urls_home')),
```

- [ ] **Step 4: Verify the project still boots**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add apps/mapping/__init__.py apps/mapping/apps.py apps/mapping/urls.py apps/mapping/migrations/__init__.py naveda_integra/settings/base.py naveda_integra/urls.py
git commit -m "feat(mapping): scaffold apps.mapping app"
```

---

### Task 2: Registry — `register_mapping`, `Role`, `TransactionType`

**Files:**
- Create: `apps/mapping/registry.py`
- Create: `apps/mapping/tests/__init__.py`
- Create: `apps/mapping/tests/test_registry.py`

**Interfaces:**
- Consumes: nothing (pure in-memory module).
- Produces: `Role(code, label, kategori, required=False)`, `TransactionType(code, label, roles: tuple[Role, ...])`, `ModuleRegistration(module, label, transaction_types: tuple[TransactionType, ...])` with method `.get_role(transaction_type, role) -> Role` (raises `MappingRegistryError`), `register_mapping(*, module: str, label: str, transaction_types: list[TransactionType]) -> None` (raises `MappingRegistryError` if `module` already registered), `get_registry() -> dict[str, ModuleRegistration]` (read-only snapshot), `get_role(module, transaction_type, role) -> Role` (raises `MappingRegistryError` if module/transaction_type/role unregistered), `clear_registry()` (test-only reset), exception class `MappingRegistryError(Exception)`.

- [ ] **Step 1: Write the failing tests**

`apps/mapping/tests/__init__.py`:
```python
```
(empty file)

`apps/mapping/tests/test_registry.py`:
```python
"""Unit tests for the mapping registry."""
from django.test import TestCase

from apps.mapping.registry import (
    MappingRegistryError, Role, TransactionType,
    clear_registry, get_registry, get_role, register_mapping,
)


class RegistryTests(TestCase):
    def tearDown(self):
        clear_registry()

    def test_register_and_get_registry(self):
        register_mapping(
            module='demo',
            label='Demo',
            transaction_types=[
                TransactionType(code='tt1', label='TT1', roles=(
                    Role('role_a', label='Role A', kategori='beban', required=True),
                )),
            ],
        )
        registry = get_registry()
        self.assertIn('demo', registry)
        self.assertEqual(registry['demo'].label, 'Demo')
        self.assertEqual(len(registry['demo'].transaction_types), 1)

    def test_register_duplicate_module_raises(self):
        register_mapping(module='demo', label='Demo', transaction_types=[])
        with self.assertRaises(MappingRegistryError):
            register_mapping(module='demo', label='Demo Again', transaction_types=[])

    def test_get_role_returns_registered_role(self):
        register_mapping(
            module='demo',
            label='Demo',
            transaction_types=[
                TransactionType(code='tt1', label='TT1', roles=(
                    Role('role_a', label='Role A', kategori='beban', required=True),
                )),
            ],
        )
        role = get_role('demo', 'tt1', 'role_a')
        self.assertEqual(role.label, 'Role A')
        self.assertTrue(role.required)

    def test_get_role_unregistered_module_raises(self):
        with self.assertRaises(MappingRegistryError):
            get_role('nope', 'tt1', 'role_a')

    def test_get_role_unregistered_role_raises(self):
        register_mapping(
            module='demo',
            label='Demo',
            transaction_types=[
                TransactionType(code='tt1', label='TT1', roles=(
                    Role('role_a', label='Role A', kategori='beban', required=True),
                )),
            ],
        )
        with self.assertRaises(MappingRegistryError):
            get_role('demo', 'tt1', 'role_b')

    def test_get_registry_is_read_only_snapshot(self):
        register_mapping(module='demo', label='Demo', transaction_types=[])
        registry = get_registry()
        registry['injected'] = 'should not persist'
        self.assertNotIn('injected', get_registry())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.mapping.tests.test_registry -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.mapping.registry'`

- [ ] **Step 3: Implement the registry**

`apps/mapping/registry.py`:
```python
"""Registry of valid (module, transaction_type, role) triples for account mapping.

Populated by each domain app's ``AppConfig.ready()`` calling ``register_mapping``.
Both the resolver and the Transaction Settings UI read this registry so they can
never disagree about which roles are valid — see
docs/superpowers/specs/2026-07-14-account-mapping-engine-design.md, Design §1.
"""
from dataclasses import dataclass


class MappingRegistryError(Exception):
    """Raised when a module registers, or a caller resolves, invalid mapping data."""


@dataclass(frozen=True)
class Role:
    code: str
    label: str
    kategori: str
    required: bool = False


@dataclass(frozen=True)
class TransactionType:
    code: str
    label: str
    roles: tuple[Role, ...]

    def get_role(self, role: str) -> Role:
        for r in self.roles:
            if r.code == role:
                return r
        raise MappingRegistryError(
            f"Role '{role}' tidak terdaftar pada transaction_type '{self.code}'."
        )


@dataclass(frozen=True)
class ModuleRegistration:
    module: str
    label: str
    transaction_types: tuple[TransactionType, ...]

    def get_transaction_type(self, transaction_type: str) -> TransactionType:
        for tt in self.transaction_types:
            if tt.code == transaction_type:
                return tt
        raise MappingRegistryError(
            f"Transaction type '{transaction_type}' tidak terdaftar pada modul '{self.module}'."
        )

    def get_role(self, transaction_type: str, role: str) -> Role:
        return self.get_transaction_type(transaction_type).get_role(role)


_REGISTRY: dict[str, ModuleRegistration] = {}


def register_mapping(*, module: str, label: str, transaction_types: list) -> None:
    if module in _REGISTRY:
        raise MappingRegistryError(f"Modul '{module}' sudah terdaftar di mapping registry.")
    _REGISTRY[module] = ModuleRegistration(
        module=module, label=label, transaction_types=tuple(transaction_types),
    )


def get_registry() -> dict:
    return dict(_REGISTRY)


def get_role(module: str, transaction_type: str, role: str) -> Role:
    if module not in _REGISTRY:
        raise MappingRegistryError(f"Modul '{module}' tidak terdaftar di mapping registry.")
    return _REGISTRY[module].get_role(transaction_type, role)


def clear_registry() -> None:
    """Reset the registry. Test-only — never call this from production code."""
    _REGISTRY.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.mapping.tests.test_registry -v 2`
Expected: `OK` (6 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/mapping/registry.py apps/mapping/tests/__init__.py apps/mapping/tests/test_registry.py
git commit -m "feat(mapping): add declarative mapping registry"
```

---

### Task 3: `AccountMapping` model, migration, admin

**Files:**
- Create: `apps/mapping/models.py`
- Create: `apps/mapping/migrations/0001_initial.py` (generated by `makemigrations`)
- Create: `apps/mapping/admin.py`
- Create: `apps/mapping/tests/test_models.py`

**Interfaces:**
- Consumes: `master_data.Akun`, `entitas_bisnis.EntitasBisnis` (existing models).
- Produces: `AccountMapping` model with fields `module` (`CharField`), `transaction_type` (`CharField`), `role` (`CharField`), `entitas_bisnis` (`FK`, null=True), `akun` (`FK`, `on_delete=PROTECT`), `created_at`, `updated_at`.

- [ ] **Step 1: Write the failing tests**

`apps/mapping/tests/test_models.py`:
```python
"""Unit tests for the AccountMapping model."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.mapping.models import AccountMapping
from apps.master_data.models import Akun


def _make_akun(kode='5.1.19', kategori='beban'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama='Beban Penyusutan')


def _make_eb(nama='EB Test'):
    tipe = TipeEntitas.objects.create(nama='Tipe Test')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe)


class AccountMappingModelTests(TestCase):
    def test_create_global_mapping(self):
        akun = _make_akun()
        m = AccountMapping.objects.create(
            module='demo', transaction_type='tt1', role='role_a', akun=akun,
        )
        self.assertIsNone(m.entitas_bisnis)
        self.assertEqual(m.akun, akun)

    def test_duplicate_global_mapping_for_same_triple_raises(self):
        akun1 = _make_akun('5.1.19')
        akun2 = _make_akun('5.1.20')
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun2)

    def test_duplicate_eb_mapping_for_same_triple_raises(self):
        eb = _make_eb()
        akun1 = _make_akun('5.1.19')
        akun2 = _make_akun('5.1.20')
        AccountMapping.objects.create(
            module='demo', transaction_type='tt1', role='role_a', entitas_bisnis=eb, akun=akun1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AccountMapping.objects.create(
                    module='demo', transaction_type='tt1', role='role_a', entitas_bisnis=eb, akun=akun2,
                )

    def test_global_and_eb_mapping_for_same_triple_coexist(self):
        eb = _make_eb()
        akun1 = _make_akun('5.1.19')
        akun2 = _make_akun('5.1.20')
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun1)
        AccountMapping.objects.create(
            module='demo', transaction_type='tt1', role='role_a', entitas_bisnis=eb, akun=akun2,
        )
        self.assertEqual(AccountMapping.objects.count(), 2)

    def test_akun_delete_protected(self):
        akun = _make_akun()
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            akun.delete()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.mapping.tests.test_models -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.mapping.models'`

- [ ] **Step 3: Implement the model**

`apps/mapping/models.py`:
```python
"""Account Mapping Engine models — see
docs/superpowers/specs/2026-07-14-account-mapping-engine-design.md, Design §1."""
from django.db import models
from django.db.models import Q


class AccountMapping(models.Model):
    """Admin-configured default Akun for one (module, transaction_type, role),
    optionally scoped to an Entitas Bisnis. entitas_bisnis=NULL is the global default."""
    module = models.CharField(max_length=50, db_index=True)
    transaction_type = models.CharField(max_length=50, db_index=True)
    role = models.CharField(max_length=50, db_index=True)
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='account_mappings',
        verbose_name='Entitas Bisnis',
    )
    akun = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name='Akun',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Account Mapping'
        verbose_name_plural = 'Account Mapping'
        indexes = [
            models.Index(fields=['module', 'transaction_type', 'role'], name='idx_mapping_lookup'),
        ]
        constraints = [
            # entitas_bisnis is non-null here: standard SQL uniqueness applies.
            models.UniqueConstraint(
                fields=['module', 'transaction_type', 'role', 'entitas_bisnis'],
                name='uniq_account_mapping_per_eb',
            ),
            # entitas_bisnis IS NULL rows are otherwise NOT caught by the constraint
            # above (SQL treats NULL <> NULL), so the "one global row per triple"
            # invariant needs its own partial unique index.
            models.UniqueConstraint(
                fields=['module', 'transaction_type', 'role'],
                condition=Q(entitas_bisnis__isnull=True),
                name='uniq_account_mapping_global',
            ),
        ]

    def __str__(self) -> str:
        scope = str(self.entitas_bisnis) if self.entitas_bisnis_id else 'Global'
        return f'{self.module}.{self.transaction_type}.{self.role} ({scope}) → {self.akun}'
```

`apps/mapping/admin.py`:
```python
from django.contrib import admin
from .models import AccountMapping


@admin.register(AccountMapping)
class AccountMappingAdmin(admin.ModelAdmin):
    list_display = ('module', 'transaction_type', 'role', 'entitas_bisnis', 'akun', 'updated_at')
    list_filter = ('module', 'transaction_type', 'entitas_bisnis')
    search_fields = ('module', 'transaction_type', 'role', 'akun__kode_akun', 'akun__nama')
    list_select_related = ('entitas_bisnis', 'akun')
    raw_id_fields = ('akun', 'entitas_bisnis')
```

- [ ] **Step 4: Generate and inspect the migration**

Run: `python manage.py makemigrations mapping`
Expected: `Migrations for 'mapping': apps/mapping/migrations/0001_initial.py` creating `AccountMapping` with the two `UniqueConstraint`s and the index above. Open the generated file and confirm both constraints and the index are present with `condition=models.Q(entitas_bisnis__isnull=True)` on the global one.

- [ ] **Step 5: Apply the migration and run tests**

Run: `python manage.py migrate mapping`
Expected: `Applying mapping.0001_initial... OK`

Run: `python manage.py test apps.mapping.tests.test_models -v 2`
Expected: `OK` (5 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/mapping/models.py apps/mapping/admin.py apps/mapping/migrations/0001_initial.py apps/mapping/tests/test_models.py
git commit -m "feat(mapping): add AccountMapping model with global/per-EB uniqueness"
```

---

### Task 4: Resolver — `resolve_account`

**Files:**
- Create: `apps/mapping/resolver.py`
- Modify: `apps/mapping/apps.py` (wire cache-clearing signal via `ready()`)
- Create: `apps/mapping/tests/test_resolver.py`

**Interfaces:**
- Consumes: `apps.mapping.registry.get_role`, `MappingRegistryError`; `apps.mapping.models.AccountMapping`.
- Produces: `resolve_account(module, transaction_type, role, entitas_bisnis=None, *, fallback=None) -> Akun`, exception `MappingNotConfiguredError(Exception)` (raised when no mapping row exists and no `fallback` was given), re-raises `MappingRegistryError` unchanged when the triple isn't registered.

- [ ] **Step 1: Write the failing tests**

`apps/mapping/tests/test_resolver.py`:
```python
"""Unit tests for resolve_account."""
from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.mapping.models import AccountMapping
from apps.mapping.registry import (
    Role, TransactionType, clear_registry, register_mapping,
)
from apps.mapping.registry import MappingRegistryError
from apps.mapping.resolver import MappingNotConfiguredError, resolve_account
from apps.master_data.models import Akun


def _make_akun(kode, kategori='beban'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


def _make_eb(nama='EB Test'):
    tipe = TipeEntitas.objects.create(nama='Tipe Test')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe)


class ResolveAccountTests(TestCase):
    def setUp(self):
        register_mapping(
            module='demo',
            label='Demo',
            transaction_types=[
                TransactionType(code='tt1', label='TT1', roles=(
                    Role('role_a', label='Role A', kategori='beban', required=True),
                )),
            ],
        )

    def tearDown(self):
        clear_registry()

    def test_unregistered_triple_raises_registry_error(self):
        with self.assertRaises(MappingRegistryError):
            resolve_account('nope', 'tt1', 'role_a')

    def test_no_mapping_no_fallback_raises_not_configured(self):
        with self.assertRaises(MappingNotConfiguredError):
            resolve_account('demo', 'tt1', 'role_a')

    def test_no_mapping_with_fallback_uses_fallback(self):
        akun = _make_akun('5.1.19')
        result = resolve_account('demo', 'tt1', 'role_a', fallback=lambda: akun)
        self.assertEqual(result, akun)

    def test_global_mapping_used_when_no_eb_override(self):
        akun = _make_akun('5.1.19')
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun)
        eb = _make_eb()
        result = resolve_account('demo', 'tt1', 'role_a', eb)
        self.assertEqual(result, akun)

    def test_eb_override_takes_priority_over_global(self):
        global_akun = _make_akun('5.1.19')
        eb_akun = _make_akun('5.1.20')
        eb = _make_eb()
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=global_akun)
        AccountMapping.objects.create(
            module='demo', transaction_type='tt1', role='role_a', entitas_bisnis=eb, akun=eb_akun,
        )
        result = resolve_account('demo', 'tt1', 'role_a', eb)
        self.assertEqual(result, eb_akun)

    def test_not_configured_error_message_mentions_role_label(self):
        with self.assertRaises(MappingNotConfiguredError) as ctx:
            resolve_account('demo', 'tt1', 'role_a')
        self.assertIn('Role A', str(ctx.exception))
        self.assertIn('Demo', str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.mapping.tests.test_resolver -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.mapping.resolver'`

- [ ] **Step 3: Implement the resolver**

`apps/mapping/resolver.py`:
```python
"""Single read path for account mapping — see
docs/superpowers/specs/2026-07-14-account-mapping-engine-design.md, Design §2.

Resolution order: EB-specific mapping -> global mapping -> caller fallback ->
MappingNotConfiguredError. A thread-local cache avoids repeat queries within
one request; it is cleared on Django's request_finished signal.
"""
import threading

from django.core.signals import request_finished

from .registry import get_role

_local = threading.local()


class MappingNotConfiguredError(Exception):
    """Raised when a required mapping has no row and no fallback was given."""


def _cache() -> dict:
    if not hasattr(_local, 'cache'):
        _local.cache = {}
    return _local.cache


def _clear_cache(**kwargs) -> None:
    _local.cache = {}


request_finished.connect(_clear_cache)


def resolve_account(module, transaction_type, role, entitas_bisnis=None, *, fallback=None):
    """Resolve the Akun configured for (module, transaction_type, role).

    Raises MappingRegistryError if the triple is not registered.
    Raises MappingNotConfiguredError if no mapping row exists and fallback is None.
    """
    from .models import AccountMapping  # local import: avoid app-loading-order issues

    role_def = get_role(module, transaction_type, role)

    eb_id = entitas_bisnis.pk if entitas_bisnis is not None else None
    cache_key = (module, transaction_type, role, eb_id)
    cache = _cache()
    if cache_key in cache:
        return cache[cache_key]

    akun = None
    if entitas_bisnis is not None:
        mapping = AccountMapping.objects.filter(
            module=module, transaction_type=transaction_type, role=role, entitas_bisnis=entitas_bisnis,
        ).select_related('akun').first()
        if mapping is not None:
            akun = mapping.akun

    if akun is None:
        mapping = AccountMapping.objects.filter(
            module=module, transaction_type=transaction_type, role=role, entitas_bisnis__isnull=True,
        ).select_related('akun').first()
        if mapping is not None:
            akun = mapping.akun

    if akun is None and fallback is not None:
        akun = fallback()

    if akun is None:
        raise MappingNotConfiguredError(
            f"Mapping '{role_def.label}' untuk {module} belum di-set."
        )

    cache[cache_key] = akun
    return akun
```

- [ ] **Step 4: Wire eager import so the signal connects on app load**

`apps/mapping/apps.py` — replace with:
```python
from django.apps import AppConfig


class MappingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mapping'
    label = 'mapping'
    verbose_name = 'Account Mapping'

    def ready(self):
        import apps.mapping.resolver  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test apps.mapping.tests.test_resolver -v 2`
Expected: `OK` (6 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/mapping/resolver.py apps/mapping/apps.py apps/mapping/tests/test_resolver.py
git commit -m "feat(mapping): add resolve_account with EB/global/fallback priority"
```

---

### Task 5: Forms and views — matrix page + AJAX save (admin-only)

**Files:**
- Create: `apps/mapping/forms.py`
- Create: `apps/mapping/views.py`
- Modify: `apps/mapping/urls.py`
- Create: `apps/mapping/tests/test_views.py`

**Interfaces:**
- Consumes: `apps.accounts.views._check_perm`, `apps.mapping.registry.get_registry`, `apps.mapping.models.AccountMapping`, `apps.master_data.models.Akun`, `apps.entitas_bisnis.models.EntitasBisnis`.
- Produces: view `settings_matrix` (GET, url name `mapping:settings`, requires `has_ni_perm('settings_view')`), view `save_mapping` (POST, url name `mapping:save`, requires `has_ni_perm('settings_update')`), form `AccountMappingForm`.

- [ ] **Step 1: Write the failing tests**

`apps/mapping/tests/test_views.py`:
```python
"""Unit tests for mapping views."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import NiPermission
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.mapping.models import AccountMapping
from apps.mapping.registry import Role, TransactionType, clear_registry, register_mapping
from apps.master_data.models import Akun

User = get_user_model()


def _make_akun(kode, kategori='beban'):
    return Akun.objects.create(kode_akun=kode, kategori_id=kategori, nama=f'Akun {kode}')


def _make_user(perm_codes=()):
    user = User.objects.create_user(email='u@test.com', password='pass', name='U')
    for code in perm_codes:
        perm, _ = NiPermission.objects.get_or_create(code=code, defaults={'name': code, 'module': 'Settings'})
        user.ni_permissions.add(perm)
    return user


class MappingViewsTests(TestCase):
    def setUp(self):
        register_mapping(
            module='demo',
            label='Demo',
            transaction_types=[
                TransactionType(code='tt1', label='TT1', roles=(
                    Role('role_a', label='Role A', kategori='beban', required=True),
                )),
            ],
        )
        self.client = Client()

    def tearDown(self):
        clear_registry()

    def test_settings_view_requires_login(self):
        response = self.client.get(reverse('mapping:settings'))
        self.assertEqual(response.status_code, 302)

    def test_settings_view_forbidden_without_permission(self):
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('mapping:settings'))
        self.assertEqual(response.status_code, 403)

    def test_settings_view_renders_registry_for_permitted_user(self):
        user = _make_user(['settings_view'])
        self.client.force_login(user)
        response = self.client.get(reverse('mapping:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Role A')

    def test_akun_dropdown_filtered_by_role_kategori(self):
        user = _make_user(['settings_view'])
        self.client.force_login(user)
        _make_akun('5.1.19', kategori='beban')
        _make_akun('1.2.7', kategori='aset')
        response = self.client.get(reverse('mapping:settings'))
        content = response.content.decode()
        self.assertIn('5.1.19', content)
        self.assertNotIn('1.2.7', content)

    def test_required_role_without_mapping_is_flagged(self):
        user = _make_user(['settings_view'])
        self.client.force_login(user)
        response = self.client.get(reverse('mapping:settings'))
        self.assertContains(response, 'wajib')

    def test_save_mapping_forbidden_without_settings_update(self):
        user = _make_user(['settings_view'])
        self.client.force_login(user)
        akun = _make_akun('5.1.19')
        response = self.client.post(
            reverse('mapping:save'),
            {'module': 'demo', 'transaction_type': 'tt1', 'role': 'role_a', 'akun': akun.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_save_mapping_creates_global_row(self):
        user = _make_user(['settings_update'])
        self.client.force_login(user)
        akun = _make_akun('5.1.19')
        response = self.client.post(
            reverse('mapping:save'),
            {'module': 'demo', 'transaction_type': 'tt1', 'role': 'role_a', 'akun': akun.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})
        mapping = AccountMapping.objects.get(module='demo', transaction_type='tt1', role='role_a')
        self.assertIsNone(mapping.entitas_bisnis)
        self.assertEqual(mapping.akun, akun)

    def test_save_mapping_upserts_existing_row(self):
        user = _make_user(['settings_update'])
        self.client.force_login(user)
        akun1 = _make_akun('5.1.19')
        akun2 = _make_akun('5.1.20')
        AccountMapping.objects.create(module='demo', transaction_type='tt1', role='role_a', akun=akun1)
        response = self.client.post(
            reverse('mapping:save'),
            {'module': 'demo', 'transaction_type': 'tt1', 'role': 'role_a', 'akun': akun2.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccountMapping.objects.filter(module='demo', transaction_type='tt1', role='role_a').count(), 1)
        mapping = AccountMapping.objects.get(module='demo', transaction_type='tt1', role='role_a')
        self.assertEqual(mapping.akun, akun2)

    def test_save_mapping_scoped_to_entitas_bisnis(self):
        user = _make_user(['settings_update'])
        self.client.force_login(user)
        tipe = TipeEntitas.objects.create(nama='Tipe Test')
        eb = EntitasBisnis.objects.create(nama='EB 1', tipe_entitas=tipe)
        akun = _make_akun('5.1.19')
        response = self.client.post(
            reverse('mapping:save'),
            {
                'module': 'demo', 'transaction_type': 'tt1', 'role': 'role_a',
                'akun': akun.pk, 'entitas_bisnis': eb.pk,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        mapping = AccountMapping.objects.get(module='demo', transaction_type='tt1', role='role_a')
        self.assertEqual(mapping.entitas_bisnis, eb)

    def test_save_mapping_invalid_role_returns_errors(self):
        user = _make_user(['settings_update'])
        self.client.force_login(user)
        akun = _make_akun('5.1.19')
        response = self.client.post(
            reverse('mapping:save'),
            {'module': 'demo', 'transaction_type': 'tt1', 'role': 'not_a_role', 'akun': akun.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body['success'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.mapping.tests.test_views -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.mapping.views'`

- [ ] **Step 3: Implement the form**

`apps/mapping/forms.py`:
```python
"""Forms for the Transaction Settings (Account Mapping) page."""
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun


class AccountMappingForm(forms.Form):
    module = forms.CharField(max_length=50)
    transaction_type = forms.CharField(max_length=50)
    role = forms.CharField(max_length=50)
    entitas_bisnis = forms.ModelChoiceField(queryset=EntitasBisnis.objects.all(), required=False)
    akun = forms.ModelChoiceField(queryset=Akun.objects.all())
```

- [ ] **Step 4: Implement the views**

`apps/mapping/views.py`:
```python
"""Transaction Settings (Account Mapping) views — admin-only."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.accounts.views import _check_perm
from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun

from .forms import AccountMappingForm
from .models import AccountMapping
from .registry import MappingRegistryError, get_registry, get_role


def _is_ajax(request: HttpRequest) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _build_matrix(entitas_bisnis):
    registry = get_registry()

    eb_mappings = {}
    if entitas_bisnis is not None:
        for m in AccountMapping.objects.filter(entitas_bisnis=entitas_bisnis).select_related('akun'):
            eb_mappings[(m.module, m.transaction_type, m.role)] = m

    global_mappings = {}
    for m in AccountMapping.objects.filter(entitas_bisnis__isnull=True).select_related('akun'):
        global_mappings[(m.module, m.transaction_type, m.role)] = m

    akun_by_kategori = {}

    def _akun_choices(kategori):
        if kategori not in akun_by_kategori:
            akun_by_kategori[kategori] = list(Akun.objects.filter(kategori_id=kategori).order_by('kode_akun'))
        return akun_by_kategori[kategori]

    modules = []
    for module_reg in sorted(registry.values(), key=lambda m: m.label):
        transaction_types = []
        for tt in module_reg.transaction_types:
            roles = []
            for role in tt.roles:
                key = (module_reg.module, tt.code, role.code)
                eb_mapping = eb_mappings.get(key)
                global_mapping = global_mappings.get(key)
                current = eb_mapping or global_mapping
                roles.append({
                    'role': role,
                    'current_akun': current.akun if current else None,
                    'is_inherited': entitas_bisnis is not None and eb_mapping is None and global_mapping is not None,
                    'akun_choices': _akun_choices(role.kategori),
                })
            transaction_types.append({'code': tt.code, 'label': tt.label, 'roles': roles})
        modules.append({'module': module_reg.module, 'label': module_reg.label, 'transaction_types': transaction_types})
    return modules


@login_required
def settings_matrix(request: HttpRequest):
    denied = _check_perm(request.user, 'settings_view')
    if denied:
        return denied
    eb_id = request.GET.get('entitas_bisnis') or None
    entitas_bisnis = get_object_or_404(EntitasBisnis, pk=eb_id) if eb_id else None
    modules = _build_matrix(entitas_bisnis)
    return render(request, 'mapping/settings.html', {
        'modules': modules,
        'entitas_bisnis_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'selected_entitas_bisnis': entitas_bisnis,
    })


@login_required
def save_mapping(request: HttpRequest):
    denied = _check_perm(request.user, 'settings_update')
    if denied:
        return denied
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    form = AccountMappingForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'errors': {k: [str(e) for e in v] for k, v in form.errors.items()}})

    module = form.cleaned_data['module']
    transaction_type = form.cleaned_data['transaction_type']
    role = form.cleaned_data['role']

    try:
        get_role(module, transaction_type, role)
    except MappingRegistryError as exc:
        return JsonResponse({'success': False, 'errors': {'role': [str(exc)]}})

    AccountMapping.objects.update_or_create(
        module=module,
        transaction_type=transaction_type,
        role=role,
        entitas_bisnis=form.cleaned_data['entitas_bisnis'],
        defaults={'akun': form.cleaned_data['akun']},
    )
    return JsonResponse({'success': True})
```

- [ ] **Step 5: Add a placeholder template (full template comes in Task 6) and wire URLs**

`templates/mapping/settings.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Transaction Settings</h1>
{% for module in modules %}
  <h2>{{ module.label }}</h2>
  {% for tt in module.transaction_types %}
    <h3>{{ tt.label }}</h3>
    {% for entry in tt.roles %}
      <p>{{ entry.role.label }}</p>
    {% endfor %}
  {% endfor %}
{% endfor %}
{% endblock %}
```

`apps/mapping/urls.py` — replace with:
```python
"""Account Mapping Engine URLs."""
from django.urls import path

from . import views

app_name = 'mapping'

urlpatterns = [
    path('settings/', views.settings_matrix, name='settings'),
    path('settings/save/', views.save_mapping, name='save'),
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test apps.mapping.tests.test_views -v 2`
Expected: `OK` (11 tests)

- [ ] **Step 7: Commit**

```bash
git add apps/mapping/forms.py apps/mapping/views.py apps/mapping/urls.py templates/mapping/settings.html apps/mapping/tests/test_views.py
git commit -m "feat(mapping): add admin-gated Transaction Settings views"
```

---

### Task 6: Real template UI + nav link

**Files:**
- Modify: `templates/mapping/settings.html`
- Modify: `templates/base.html` (add nav link)

**Interfaces:**
- Consumes: context from `settings_matrix` (Task 5): `modules`, `entitas_bisnis_list`, `selected_entitas_bisnis`.
- Produces: no new Python interfaces — UI only.

- [ ] **Step 1: Write the full template**

`templates/mapping/settings.html`:
```html
{% extends "base.html" %}
{% load static %}

{% block title %}Transaction Settings — Naveda Integra{% endblock %}

{% block content %}
<div class="ni-card">
  <div class="ni-card__header" style="display:flex; justify-content:space-between; align-items:center;">
    <h1>Transaction Settings</h1>
    <form method="get" style="display:flex; align-items:center; gap:8px;">
      <label for="eb-select">Entitas Bisnis:</label>
      <select id="eb-select" name="entitas_bisnis" class="ni-input" onchange="this.form.submit()">
        <option value="">Semua (Default Global)</option>
        {% for eb in entitas_bisnis_list %}
        <option value="{{ eb.pk }}" {% if selected_entitas_bisnis.pk == eb.pk %}selected{% endif %}>{{ eb.nama }}</option>
        {% endfor %}
      </select>
    </form>
  </div>

  <div class="ni-card__body">
    {% for module in modules %}
    <h2>{{ module.label }}</h2>
    {% for tt in module.transaction_types %}
    <h3 style="margin-left:12px;">{{ tt.label }}</h3>
    <table class="ni-table" style="margin-left:24px; margin-bottom:16px;">
      <tbody>
        {% for entry in tt.roles %}
        <tr>
          <td>
            {{ entry.role.label }}
            {% if entry.role.required and not entry.current_akun %}
            <span style="color:#c0392b;">(! wajib)</span>
            {% endif %}
          </td>
          <td>
            <form method="post" action="{% url 'mapping:save' %}" class="mapping-save-form">
              {% csrf_token %}
              <input type="hidden" name="module" value="{{ module.module }}">
              <input type="hidden" name="transaction_type" value="{{ tt.code }}">
              <input type="hidden" name="role" value="{{ entry.role.code }}">
              {% if selected_entitas_bisnis %}
              <input type="hidden" name="entitas_bisnis" value="{{ selected_entitas_bisnis.pk }}">
              {% endif %}
              <select name="akun" class="ni-input" onchange="this.form.requestSubmit()">
                <option value="">-- belum di-set --</option>
                {% for akun in entry.akun_choices %}
                <option value="{{ akun.pk }}" {% if entry.current_akun.pk == akun.pk %}selected{% endif %}>
                  {{ akun.kode_akun }} {{ akun.nama }}
                </option>
                {% endfor %}
              </select>
            </form>
          </td>
          <td>
            {% if entry.current_akun and entry.is_inherited %}
            <span style="opacity:0.6;">(warisan dari global)</span>
            {% elif entry.current_akun %}
            <span style="color:#27ae60;">(set)</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% endfor %}
    {% endfor %}
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
document.addEventListener('submit', function (e) {
  if (!e.target.classList.contains('mapping-save-form')) return;
  e.preventDefault();
  var form = e.target;
  var data = new FormData(form);
  fetch(form.action, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    body: data,
  })
    .then(function (r) { return r.json(); })
    .then(function (json) {
      if (json.success) {
        window.location.reload();
      } else {
        alert('Gagal menyimpan: ' + JSON.stringify(json.errors));
      }
    })
    .catch(function () {
      alert('Terjadi kesalahan. Silakan coba lagi.');
    });
});
</script>
{% endblock %}
```

- [ ] **Step 2: Add the nav link, gated by `settings_view`**

In `templates/base.html`, find:
```
      {% if user.is_superuser or user.is_admin %}
      <div class="ni-nav-item">
        <a href="{% url 'accounts:user_list' %}" class="ni-nav-link {% if 'accounts/users' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="users" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">User</span>
        </a>
      </div>
      {% endif %}
```
Change to:
```
      {% if user.is_superuser or user.is_admin %}
      <div class="ni-nav-item">
        <a href="{% url 'accounts:user_list' %}" class="ni-nav-link {% if 'accounts/users' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="users" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">User</span>
        </a>
      </div>
      {% endif %}

      {% load pos_tags %}
      {% if user|has_ni_perm:"settings_view" %}
      <div class="ni-nav-item">
        <a href="{% url 'mapping:settings' %}" class="ni-nav-link {% if 'mapping/settings' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="settings" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">Transaction Settings</span>
        </a>
      </div>
      {% endif %}
```

- [ ] **Step 3: Manual verification**

Run: `python manage.py runserver`
1. Log in as a user without `settings_view` — confirm no "Transaction Settings" link appears in the nav, and visiting `/mapping/settings/` directly returns 403.
2. Grant the logged-in user the `settings_view` permission (via `/accounts/users/` UI or `python manage.py shell` + `user.ni_permissions.add(NiPermission.objects.get(code='settings_view'))`) — confirm the nav link appears and the page renders (empty matrix is expected — no module registers in Tahap 0 yet).
3. Grant `settings_update` too, temporarily register a module in a shell (`from apps.mapping.registry import register_mapping, Role, TransactionType; register_mapping(module='demo', label='Demo', transaction_types=[TransactionType('tt1','TT1',(Role('role_a','Role A','beban', True),))])`) inside `runserver`'s process is not practical — instead confirm the save endpoint behavior via the Task 5 test suite (already covers this) and note that real end-to-end UI verification of a populated matrix happens in Tahap 1 once a real module registers.

- [ ] **Step 4: Commit**

```bash
git add templates/mapping/settings.html templates/base.html
git commit -m "feat(mapping): build Transaction Settings matrix UI and nav entry"
```

---

### Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full mapping test suite**

Run: `python manage.py test apps.mapping -v 2`
Expected: `OK` (all tests from Tasks 2-5 pass together, no cross-test registry leakage — confirms every test's `tearDown` correctly calls `clear_registry()`)

- [ ] **Step 2: Run the full project test suite to confirm no regressions**

Run: `python manage.py test`
Expected: `OK` — in particular no failures in `apps.master_data`, `apps.entitas_bisnis`, `apps.accounts`, `apps.jurnal`, `apps.purchase`, `apps.sales`, `apps.pendapatan` (confirms the Global Constraint "STT is not touched" held and nothing else was broken by `INSTALLED_APPS`/`urls.py` changes).

- [ ] **Step 3: Confirm `manage.py check` and migration state are clean**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `python manage.py makemigrations --check --dry-run`
Expected: no output / exit code 0 (no missing migrations).

- [ ] **Step 4: Final commit (if any cleanup was needed)**

If Steps 1-3 required no code changes, there is nothing to commit — Tahap 0 is complete. If a fix was needed, commit it with a message describing what regression it addressed.
