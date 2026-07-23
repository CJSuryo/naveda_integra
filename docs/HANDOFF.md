# HANDOFF — Aggregator Integration Research & Self-Service Onboarding

**Date:** 2026-07-23
**Repo:** `stamps/ordering_system` (Omni) · branch `master`
**Status:** Research & design complete. **No code was written or changed.**
**Audience:** (a) the Claude Code agent / engineer porting these patterns to another POS project,
(b) the Omni team implementing self-service onboarding.

---

## 1. What was asked, what was produced

Two requests, answered in sequence:

1. *"Explain how GoFood / GrabFood / ShopeeFood integration works here — features, flaws, what's
   missing — so another project's POS can learn from it."*
2. *"Onboarding takes devops too long. Make it operable by a low-skill employee, with tutorials."*

**Deliverables (all new, all in `docs/`):**

| # | File | What it's for | Read it if you're… |
|---|---|---|---|
| 1 | [`aggregator_integration_guide.md`](aggregator_integration_guide.md) | How the integration actually works: architecture, data model, inbound/outbound flows, per-aggregator differences, flaws, feature inventory, **porting guide to another stack** | …porting to another project, or new to this codebase |
| 2 | [`aggregator_self_service_onboarding.md`](aggregator_self_service_onboarding.md) | Design for the onboarding wizard: state machine, adapters, credential vault, pre-flight checks, realtime (FCM vs WebSocket) | …building the onboarding system |
| 3 | [`aggregator_onboarding_plan_and_tutorial.md`](aggregator_onboarding_plan_and_tutorial.md) | **Capability verdict** (can each aggregator do self-service?), revised build plan, **operator tutorial** | …deciding scope, or writing the staff guide |
| 4 | `HANDOFF.md` | This file | …picking the work up cold |

**Recommended reading order:** 4 (this) → 1 → 3 → 2.

**Working tree state:** the three docs above are **untracked** (`??`). Nothing else was touched.
No migrations, no models, no endpoints. Commit them when ready.

---

## 2. Method — how these conclusions were reached (so you can trust or re-check them)

- **Codebase**: read the aggregator libraries (`libraries/{grabfood,gofood,shopeefood}/`), the webhook
  layer (`ordering_system/api/food/`), the backoffice setup screens
  (`ordering_system/backoffices/aggregators/`), the POS forwarding layer
  (`ordering_system/store_connect/orders.py`), and the models
  (`orders`, `merchants`, `stores`, `inventories`).
- **Official docs**: GoBiz Developer Portal (Facilitator model, authorization-code flow, outlet
  linking). Sources listed at the bottom of doc #3.
- **Not verified**: aggregator **portal UI** (screen names, menu paths, button labels). These are
  private and change; they are explicitly marked `[VERIFY]` in doc #3 rather than guessed. See §5.

---

## 3. Key findings (the ones that change decisions)

### 3.1 Architecture — the good part worth copying

Omni is two-way middleware between merchant POS systems and aggregators. Two **independent** flows:
inbound (aggregator → normalize → forward to POS) and outbound (Omni owns the menu → push catalog,
prices, stock, promos).

Best design ideas, worth porting as-is:
- **Normalized order model**: `Order` + `AggregatorMetadata` (1:1), so all aggregators collapse to one
  internal shape.
- **Banded status enum** (`AggregatorMetadata.Status`, `apps/orders/models.py:2298`): each aggregator
  gets a numeric band (GoFood 5–30, Grab 100–170, Shopee 210–340), monotonic within the band. Lets
  out-of-order webhooks be rejected with a plain integer compare. Cheapest possible ordering guard.
- **Three-layer idempotency**: Redis lock on external order id + existence check + business-rule dedup.
- **Configurable POS-trigger event** — merchants choose whether the kitchen sees the order on create,
  driver-allocated, or driver-arrived.
- **Never auto-cancel an aggregator order** on POS failure (`order.placed_via_aggregator` guard).
- **Query-by-reference before retry** when the POS times out, so retries don't duplicate POS orders.

### 3.2 Flaws — do not inherit these

1. Money is `float` throughout. **Use `Decimal` in the target project.**
2. Grab and GoFood duplicate ~80% of order/modifier logic; both `save_items` are `# noqa: C901`.
3. No service layer — logic sits in `libraries/*` module functions, contradicting the repo's own
   `CLAUDE.md`.
4. Idempotency depends on Redis; no DB unique constraint on `(aggregator_type, external_order_id)` as a
   backstop.
5. Two API generations live simultaneously (GoFood `old_url` vs `v1`).
6. Mixed English/Indonesian comments in `libraries/grabfood/orders.py`.

### 3.3 Biggest missing features (for any POS doing this)

Settlement/payout reconciliation (**largest gap** — no answer today), bidirectional status push (only
GoFood mark-food-ready exists), a single Decimal pricing/tax engine, menu diffing, and a
`WebhookEvent` table with replay.

### 3.4 The decisive onboarding finding — GoFood is on the wrong integration model

GoBiz offers two models. Omni uses the one that *cannot* be self-service:

| | **Direct Integration** (Omni today) | **Facilitator** (enables self-service) |
|---|---|---|
| Grant | `client_credentials` | `authorization_code` + refresh |
| Who authorizes | nobody — creds issued out-of-band | **the merchant** (phone → OTP → consent → Allow) |
| Outlet IDs | typed by hand | **auto-discovered** via `GET /integrations/partner/v1/token-info` |
| Linking | manual mapping | `PUT /integrations/partner/outlets/{outlet_id}/v1/link/gofood` |

**The migration is smaller than it looks.** Three facts from Omni's own code:
- `libraries/gofood/utils.py:69` `get_bearer_token()` already requests scopes including
  `partner:outlet:write partner:outlet:read` — the facilitator scopes.
- `GoFoodSettings.CreateNotificationUrl.v1` is already `/integrations/partner/v1/...` — Omni is
  **already on the facilitator URL namespace**, just authenticating the old way.
- `FoodAggregatorSettings` already has `access_token`, `access_token_expiration`, `refresh_token`,
  `refresh_token_expiration`.

So the work is: swap the grant, add consent redirect + callback, add token-info + link/unlink.
Catalog upload, notification subscriptions, mark-food-ready, and order webhooks are unaffected.

### 3.5 Self-service capability verdict

| Aggregator | Verdict |
|---|---|
| **GrabFood** | ✅ Already self-service (`get_self_activation_url` → Grab → `pushIntegrationStatus` callback auto-fills the store id). **This is the reference pattern.** |
| **GoFood** | ✅ Achievable, and *better* than Grab (outlets auto-discovered, operator types nothing) — **after** the Facilitator migration. |
| **ShopeeFood** | ❌ Not achievable. POS partner APIs are gated and not openly documented. Best case: devops does one-time credential setup, operator does **one validated copy-paste** of `shopeefood_store_id`. |

**Do not promise zero-touch ShopeeFood onboarding to stakeholders.**

### 3.6 Realtime — FCM already exists

New orders already push via **Firebase Cloud Messaging topics**
(`publish_new_order(order, store.pubsub_key)`, `apps/stores/notifications.py`). It is not polling.

Recommendation: **keep FCM as the durable guarantee** for native POS apps. Add WebSocket (Django
Channels + Redis channel layer, one group per store) **only** for a browser live-order board, emitted
alongside the existing FCM call. Never make order delivery depend on a live socket.

---

## 4. Decisions made (and why)

| Decision | Rationale |
|---|---|
| Model everything on Grab's activation flow | It already works in production and is the only fully self-service path today |
| Migrate GoFood to Facilitator rather than paper over Direct Integration with UI | UI can't fix a model that has no merchant-consent step; and Omni is already 70% there |
| Accept ShopeeFood as manual | No API exists to automate it; pretending otherwise creates a broken promise |
| Gate "Go live" behind automated pre-flight checks | Makes the **system**, not the operator, responsible for readiness — this is what makes it safe for low-skill staff |
| Keep FCM, add WebSocket only for the web board | FCM handles background delivery/reconnect/battery; sockets are worse for that and better for in-page updates |
| Mark portal UI steps `[VERIFY]` instead of inventing them | Wrong click-paths are worse than acknowledged gaps — the operator would follow them into a misconfiguration |

---

## 5. Verified vs unverified — read before shipping the tutorial

**Verified** (from official GoBiz docs or Omni source — safe to rely on):
API endpoints and grant types · the OTP → consent → authorization-code sequence · `token-info` returning
outlet id/name/address/phone/email · outlet link/unlink endpoints · the 7 GoFood webhook events ·
Omni's current scopes, URL namespace, and token storage fields · Grab's activation + `pushIntegrationStatus`
callback behaviour · FCM as the current realtime transport.

**NOT verified** (marked `[VERIFY]` in doc #3 — **must be filled before staff use it**):
Grab Merchant Portal / GoBiz / Shopee portal **screen names, menu paths, button labels**; the exact
Shopee portal field where the store ID lives and its format; EN vs Bahasa Indonesia wording differences.

**How to close this gap** (§4 of doc #3): one person does a screenshot pass over the three portals,
then **someone who has never done the setup follows the guide end-to-end on a test merchant**. Every
hesitation marks a missing sentence. That dry run — not the writing — is what makes the tutorial
actually foolproof.

---

## 6. Open questions / blockers

1. **Is Omni already a registered GoBiz Partner (Facilitator)?** If not, this is a **one-time,
   company-level** application via the GoBiz contact form, with an assessment step by their team.
   **This gates all GoFood self-service work** — start it now, in parallel with development, because
   the lead time is external and unknown.
2. **Migration strategy for existing GoFood merchants** on Direct Integration — they must keep working.
   Plan: keep `client_credentials` behind a flag, migrate merchant-by-merchant. **Do not big-bang.**
3. **Does ShopeeFood offer any partner-facing onboarding API** under NDA that public docs don't show?
   Worth asking your Shopee account manager directly — it would change §3.5.
4. **Who owns onboarding?** Client self-serve, or Omni staff on the client's behalf? This changes the
   RBAC split (which steps need devops permission) and the tutorial's tone.
5. **Which target project is doc #1's porting guide aimed at?** It was written stack-agnostic with
   bracketed choices. If it's `naveda_integra`, §11 can be made concrete — ask before assuming.

---

## 7. Recommended first actions

**If you're the Omni team:**
1. Start the GoBiz Facilitator partner application **today** (external lead time — blocker #1).
2. Build the onboarding **state machine + pre-flight checks** (doc #2 §3.1, §3.4). These deliver most of
   the devops-toil reduction *before* any UI work.
3. Wrap the GoFood 7-event webhook registration into **one idempotent "Register / Re-sync" call**
   (the code already exists in `create_notification_subscription`; it just needs a trigger and a
   create-vs-update reconcile).
4. Encrypt credentials at rest and add the config-template registry (kills the `old_url`/`v1` bug class).
5. Then the GoFood Facilitator migration, then the wizard UI, then (optionally) WebSockets.

**If you're the porting agent on another project:**
1. Read doc #1 §0–§3 for the model, then §11 for the adaptation guide.
2. Answer §11.1's questions about the target stack **before** writing code (framework, queue, money
   type, who owns the menu, is the target itself the POS, multi-tenancy).
3. Build in this order: canonical DTOs with `Decimal` → ingest + idempotency → **one** adapter
   end-to-end → outbound menu → extract the shared tax/modifier engine once a second adapter exists.
4. Copy: normalized model, banded-status guard, three-layer idempotency, never-auto-cancel rule.
   Rebuild: money handling, the flat status enum, the duplicated per-aggregator logic.

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| GoBiz Facilitator application delayed/refused | Kills GoFood self-service entirely | Apply immediately; keep Direct Integration working as fallback |
| Tutorial shipped with unverified portal steps | Operators misconfigure; worse than no guide | Block release on the §5 verification + dry run |
| Big-bang GoFood auth migration | Breaks live merchants' order flow | Feature-flag; migrate per merchant; keep both grants during rollout |
| Float money carried into the new project | Silent financial errors | Mandate `Decimal` from day one — cheap now, expensive later |
| Wrong outlet↔store mapping during onboarding | Orders to the wrong kitchen; corrupted sales data | Match by **address not name**; validate ID format; require pre-flight test order |
| Stakeholders promised zero-touch ShopeeFood | Broken commitment | Communicate §3.5 verdict early |

---

## 9. Glossary (for a cold reader)

- **Aggregator** — GrabFood / GoFood / ShopeeFood etc.
- **ATO / StoreConnect** — the downstream POS Omni forwards orders to.
- **Outlet / store id** — the aggregator's identifier for one branch; mapped in `AggregatorSettings`.
- **Config set** — a per-channel menu override profile (different names/prices/positions per aggregator).
- **Slash price** — an item-level discount; who funds it (merchant vs aggregator) changes reported revenue.
- **Facilitator model** — GoBiz's POS-partner integration model using merchant-consent OAuth.
- **Pre-flight** — the automated readiness checks that must pass before an integration goes live.
- **`pubsub_key`** — per-store Firebase topic used to push new orders to POS devices.
