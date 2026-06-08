# Pendapatan + Piutang — Master Implementation Plan
**Date:** 2026-06-07
**Status:** Approved

---

## Overview

This plan covers 4 deliverables that together implement revenue recognition and receivables management for Naveda Integra. Build order is determined by dependency — Piutang must exist before Pendapatan can create receivables from revenue.

| # | Module | App | Depends On |
|---|---|---|---|
| 1 | Piutang | `apps/piutang/` | — |
| 2 | Sales `payment_type` | `apps/sales/` | Piutang |
| 3 | Pendapatan Core | `apps/pendapatan/` | Piutang |
| 4 | Deferred Revenue | `apps/pendapatan/` | Pendapatan Core |
| 5 | Recurring Revenue | `apps/pendapatan/` | Pendapatan Core |

Phases 4 and 5 can be built in parallel.

---

## Individual Spec Files

- [Piutang Design](../specs/2026-06-07-piutang-design.md)
- [Pendapatan Design](../specs/2026-06-07-pendapatan-design.md)
- [Deferred Revenue Design](../specs/2026-06-07-deferred-revenue-design.md)
- [Recurring Revenue Design](../specs/2026-06-07-recurring-revenue-design.md)

## Implementation Plans

- [Phase 1 — Piutang](2026-06-07-piutang-phase1.md)
- [Phase 2 — Sales payment_type](2026-06-08-sales-payment-type-phase2.md)
- [Phase 3 — Pendapatan Core](2026-06-08-pendapatan-phase3.md)
- [Phase 4 — Deferred Revenue](2026-06-08-deferred-revenue-phase4.md)
- [Phase 5 — Recurring Revenue](2026-06-08-recurring-revenue-phase5.md)

---

## Phase 1 — Piutang

**Goal:** Full `apps/piutang/` implementation, replacing placeholder stub.

**Deliverables:**
- Models: `PiutangHeader`, `PiutangDetail`, `PiutangPenerimaan`, `PiutangReklasifikasi`, `PiutangWriteOff`, `PiutangAttachment`, `PiutangAuditLog`
- Services: all functions in `piutang_services.py` *except* `create_piutang_from_sales` and `create_piutang_from_pendapatan` (stubs only — callers don't exist yet)
- URLs, views, templates (mirror utang)
- Admin registration
- Migration replacing stub

**Acceptance:**
- Can manually create piutang, record penerimaan, do reklasifikasi, write off
- Aging report returns correct groupings
- Dashboard KPI cards render

---

## Phase 2 — Sales `payment_type`

**Goal:** Enable credit sales → auto-create piutang on confirm.

**Deliverables:**
- `SalesHeader.payment_type` field (CharField, cash|credit, default=cash)
- Migration in `sales` app
- `sales/forms.py` — add `payment_type` to `SalesHeaderForm`
- `sales/views.py` confirm path — if `payment_type='credit'` → call `create_piutang_from_sales()`
- Implement `create_piutang_from_sales()` in `piutang_services.py` (was stub in Phase 1)
- Sales detail page shows linked piutang if credit

**Acceptance:**
- Existing sales records unaffected (all treated as cash)
- New credit sale on confirm creates `PiutangHeader` with correct amount and source FK
- Cash sale on confirm: no piutang created

---

## Phase 3 — Pendapatan Core

**Goal:** Full `apps/pendapatan/` app — manual + recurring-source transactions, journals, piutang integration.

**Deliverables:**
- New Django app `apps/pendapatan/` registered in `INSTALLED_APPS` and root `urls.py`
- `SubTransactionType.MODULE_CHOICES` + `'pendapatan'` (migration in purchase app)
- Models: `PendapatanHeader`, `PendapatanEntitasBisnis`, `PendapatanItem`, `PendapatanEventLog`
- Services: `confirm_pendapatan`, `create_pendapatan_journals`, `create_piutang_from_pendapatan`, `void_pendapatan`
- Implement `create_piutang_from_pendapatan()` in `piutang_services.py` (was stub in Phase 1)
- API endpoint: `/pendapatan/api/stt-defaults/`
- URLs, views, templates
- Dashboard with KPI cards (deferred/recurring KPIs show 0 until later phases)
- Admin registration
- Initial migration

**Acceptance:**
- Cash transaction: create → confirm → journals generated correctly
- Credit transaction: create → confirm → journals + PiutangHeader created
- Void: reversal journals generated, linked piutang cancelled
- STT auto-fill API returns correct accounts
- Multi-EB: one transaction with 2 EB groups generates 2 separate JurnalHeaders

---

## Phase 4 — Deferred Revenue

**Goal:** Per-item deferred revenue scheduling and period recognition.

**Deliverables:**
- Models: `DeferredRevenueSchedule`, `DeferredRevenueEntry`
- Migration in `pendapatan` app
- Services: `create_deferred_schedule`, `recognize_deferred_entry`, `reverse_deferred_entry`
- Update `create_pendapatan_journals()` — swap credit leg for deferred items
- Update `confirm_pendapatan()` — call `create_deferred_schedule` for deferred items
- Update `void_pendapatan()` — call `reverse_deferred_entry` for pending entries
- Update Pendapatan create/edit form — `is_deferred` checkbox reveals deferred fields per item
- Management command: `recognize_deferred_entries`
- URLs + views: schedule detail, recognize action
- Dashboard deferred KPI card now functional

**Acceptance:**
- Deferred item: confirm generates `DR payment / CR deferred_account` (not revenue_account)
- Schedule created with correct period entries (straight_line math correct)
- Recognize entry: journal `DR deferred / CR recognition` generated, entry status → recognized
- Management command: `--period 2025-01` recognizes all pending entries for January 2025
- Void with pending deferred entries: entries set to reversed, no journal error

---

## Phase 5 — Recurring Revenue

**Goal:** Template-driven recurring pendapatan generation.

**Deliverables:**
- Model: `RecurringTemplate`
- Migration in `pendapatan` app — also adds `PendapatanHeader.source_recurring` FK
- Services: `generate_from_recurring`, `compute_next_date`
- Management command: `generate_recurring_pendapatan`
- URLs + views: list, create, detail, edit, delete (soft), manual generate
- Report: calendar view of upcoming recurring
- Dashboard recurring KPI card now functional

**Acceptance:**
- Create template, generate manually → PendapatanHeader created with correct fields
- `tanggal_berikutnya` advances correctly per frekuensi after each generation
- `auto_confirm=True`: generated header is immediately confirmed
- Template with `tanggal_selesai`: `is_active` set to False after last period passes
- Management command: processes all overdue templates, skips inactive ones
- Calendar report shows upcoming 3 months of scheduled revenue

---

## Cross-Cutting Decisions

### Piutang source FKs
`PiutangHeader.source_sales` and `source_pendapatan` are nullable. Add them in Phase 1 initial migration (null/blank). They simply have no values until their source modules exist.

### `JurnalHeader` linking
Pendapatan and Piutang generate their own `JurnalHeader` records directly. Access via `pendapatan_header.event_logs` to find `JOURNAL_CREATED` events which store the journal IDs in `description`.

Alternatively, store `JurnalHeader` FKs on `PendapatanEntitasBisnis` (one per EB group) for direct access. Implementation choice left to Phase 3 builder — both patterns exist in the codebase.

### System user for management commands
Both `recognize_deferred_entries` and `generate_recurring_pendapatan` need a user for audit logs. Use `User.objects.filter(is_superuser=True).first()` as fallback system actor, or configure a dedicated service account.

### `SubTransactionType` for Pendapatan
New STT records with `module='pendapatan'` need to be seeded via fixture or data migration in Phase 3. At minimum: one STT per `PendapatanItem.kategori` choice.
