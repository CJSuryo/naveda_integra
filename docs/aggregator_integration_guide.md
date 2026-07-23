# Food Aggregator Integration — Architecture, Analysis & Porting Guide

> **Purpose of this document.** It is a complete, self-contained explanation of how the "Omni"
> ordering system integrates with food-delivery aggregators (GrabFood, GoFood, ShopeeFood, plus
> FoodPanda / Deliveroo / TabSquare which share the same skeleton). It is written to be **read and
> acted on by another Claude Code agent** working on a *different* POS/ordering project. Every
> section separates **"what Omni does"** from **"what you should do in the target project"** so the
> patterns can be adapted rather than copied blindly.
>
> Source of truth: the `stamps/ordering_system` Django codebase. File references are
> `repo-relative` and clickable when opened inside that repo.

---

## 0. TL;DR for the porting agent

Omni is a **two-way middleware** sitting between merchant POS systems and multiple aggregators:

```
                 MENU / PRICE / STOCK  (outbound, Omni -> Aggregator)
   ┌────────┐   ─────────────────────────────────────────────▶   ┌────────────┐
   │  POS   │                                                     │ Aggregator │
   │ (ATO / │   ◀─────────────────────────────────────────────   │ Grab/Go/   │
   │ Moka…) │        ORDERS / STATUS  (inbound webhooks)          │ Shopee     │
   └────────┘                                                     └────────────┘
        ▲                         Omni (this repo)                       │
        └──────────────  order forwarded to POS  ◀──────────────────────┘
```

Two independent data flows, do not conflate them:

1. **Inbound (aggregator → Omni → POS):** aggregator calls Omni webhooks. Omni **normalizes** the
   payload into its internal `Order` + `AggregatorMetadata` models, then **forwards** the order to
   the merchant's POS ("ATO"/StoreConnect). Status callbacks (accepted, driver arrived, completed,
   cancelled) drive an internal state machine.
2. **Outbound (Omni → aggregator):** Omni **serializes its own catalog** (products, prices,
   modifiers, availability, promotions) and pushes it to each aggregator's menu API. Stock/price
   changes are propagated as targeted availability updates.

The three aggregators differ mainly in: **auth scheme**, **payload shape**, **status vocabulary**,
and **who owns the menu**. Omni hides those differences behind per-aggregator library modules with a
near-identical function surface (`create`, `update`, `cancel`, `complete`, `send_order_to_pos_if_needed`,
`upload_menus`, `update_menu_availability`, …).

**If you port one thing, port the normalization boundary:** a stable internal order model + a
per-aggregator adapter that translates in both directions. Everything else is detail.

---

## 1. Where the code lives

| Concern | Location |
|---|---|
| Webhook HTTP views (inbound) | `ordering_system/api/food/{grab,gofood,shopee}/views.py` |
| URL routing + auth/signature guards | `ordering_system/api/food/{...}/urls.py`, `ordering_system/api/food/views.py` |
| Input validation (forms) | `ordering_system/api/food/{...}/forms.py` |
| Order translation + state machine (business logic) | `libraries/{grabfood,gofood,shopeefood}/orders.py` (ShopeeFood: `libraries/shopeefood/__init__.py`) |
| Menu/price/stock serialization + outbound push | `libraries/{grabfood,gofood}/utils.py`, `libraries/{...}/serializers.py`, `libraries/shopeefood/__init__.py` |
| Per-aggregator credentials/behaviour flags | `ordering_system/apps/merchants/models.py` → `GrabFoodSettings`, `GoFoodSettings`, `ShopeeFoodSettings` |
| Per-store external IDs + tax + config-set selection | `ordering_system/apps/stores/models.py` → `AggregatorSettings` |
| Per-item aggregator price/stock/promo | `ordering_system/apps/inventories/models.py` → `AggregatorInventorySettings`, `AggregatorInventoryPromotion` |
| Order + normalized aggregator state | `ordering_system/apps/orders/models.py` → `Order`, `AggregatorMetadata` |
| Forwarding order to POS | `ordering_system/store_connect/orders.py` (sync) + `async_orders.py` |
| Enums shared across all of the above | `ordering_system/constants.py` → `AggregatorType`, `Channel`, `OrderType`, `PaymentMethods` |

**Design smell to note:** business logic lives in `libraries/*` (module-level functions), **not** in a
per-app `services.py`, which contradicts the repo's own `CLAUDE.md` "Service Layer" rule. When porting,
prefer putting adapters in a proper service layer (see §11).

---

## 2. The normalized data model (the heart of it)

Every aggregator order collapses into the same internal shape:

- **`Order`** — channel-agnostic order (totals, tax, discount, `net_revenue`, `type`, `payment_method`,
  `payment_status`, `channel`). Menu items become `Item` rows; add-ons become `ItemModifier` rows.
- **`AggregatorMetadata`** (1:1 with `Order`) — the adapter's "memory": `external_order_id`,
  `short_order_number`, `type` (`AggregatorType`), `order_type`, `status`, plus driver/customer fields.
- **`AggregatorSettings`** (1:1 with `Store`) — maps Omni store ↔ each aggregator's outlet id
  (`grab_food_store_id`, `gofood_store_id`, `shopeefood_store_id`), holds per-channel `*_tax_percentage`
  and optional per-channel **config set** (a menu-override profile).
- **`AggregatorInventorySettings`** (per `Inventory`) — per-item **channel-specific price** (`price`,
  `price_after_tax`, `discounted_price`), so the same product can be priced differently on Grab vs Go
  vs Shopee (aggregators charge commission, merchants mark up).
- **`{Grab,Go,Shopee}FoodSettings`** (1:1 with `Merchant`) — credentials + **behaviour flags** that
  change how orders are processed (see §6).

### The single most important trick: one status enum, namespaced by aggregator

`AggregatorMetadata.Status` (`ordering_system/apps/orders/models.py:2298`) is a **single `IntegerChoices`
enum** where each aggregator gets its own numeric band:

```
GoFood      5–30      (GOFOOD_ORDER_CREATED … GOFOOD_CANCELLED)
GrabFood    100–170   (GRABFOOD_UNCONFIRMED … GRABFOOD_CANCELLED)
ShopeeFood  210–270 / 305–340
FoodPanda   400–415
Deliveroo   501–505
TabSquare   601
```

Because the numbers are **monotonic within a band**, the code can express "ignore an out-of-order
webhook" as a plain integer comparison:

```python
# libraries/grabfood/orders.py
if order.aggregator_metadata.status > AggregatorMetadata.Status.GRABFOOD_ACCEPTED:
    order.logs.create(action=OrderLog.Action.ACCEPTED, notes="Grab, ignored(status > accepted)")
    return
```

This is the cheapest possible idempotency/ordering guard and it is used everywhere.
**Adopt this pattern** — it is the backbone of the whole state machine.

---

## 3. Inbound flow, end to end (aggregator → Omni → POS)

### 3.1 HTTP entry + authentication (the differentiator between aggregators)

All three subclass `BaseAPIView`, but authenticate differently
(`ordering_system/api/food/views.py`):

| Aggregator | Auth mechanism | Where |
|---|---|---|
| **GrabFood** | OAuth2 bearer token (`OAuth2Authentication`) + required scopes `resource.READ/WRITE`. Omni is the OAuth2 **provider** (`oauth/token` endpoint issues tokens to Grab). | `GrabAPIView` |
| **GoFood** | **HMAC-SHA256** of raw request body vs `X-Go-Signature` header, keyed by per-merchant `notification_secret_key`; merchant resolved from `enterprise_id` in the URL. | `GoFoodAPIView.initial()` |
| **ShopeeFood** | OAuth2 **+ optional** HMAC signature of `METHOD:path:payload` vs `X-SF-Signature`; vendor resolved from `vendor_id` in the URL. | `ShopeeAPIView` |

**Lesson for porting:** the auth strategy is per-partner and belongs in a thin view/middleware layer,
*not* in business logic. Note GoFood signs the **raw body** (so you must verify before DRF parses/mutates
it) while ShopeeFood signs a **canonicalized** string (compact-separator JSON) — signature verification
details are a top source of integration bugs. Use `hmac.compare_digest` (constant-time), as Omni does.

### 3.2 Concurrency guard: distributed lock per external order id

Every mutating webhook wraps work in a Redis lock keyed by the aggregator order number:

```python
# api/food/grab/views.py
with lock(f"grab-{payload['orderID']}", ttl=300, release_on_exit=True):
    order, created = process_order(payload)
    ...
```

Aggregators **retry** webhooks aggressively and fire near-simultaneous events (create + accept). Without
this lock you get duplicate orders / lost updates. On lock contention Omni returns a soft error asking the
caller to retry. **Port this** — it is not optional at scale.

### 3.3 Idempotency / duplicate handling (three layers)

1. **Lock** (above) serializes concurrent deliveries.
2. **Existence check**: look up `AggregatorMetadata.external_order_id`; if the order already exists,
   return success without re-creating (`GoFood OrderCreated`, `Shopee CreateOrder`, `Grab process_order`).
3. **Business-rule dedup**: GoFood optionally rejects a *different* order id with the **same customer +
   same grand total within 5 minutes** (`allow_double_order=False` → `DoubleOrderError`), because GoFood
   sometimes emits two order numbers for one basket.

Aggregators generally treat **any non-2xx as "retry"**, and each has an expected success code
(**Grab wants `204`**, Shopee wants its own JSON envelope). Returning the wrong code causes infinite retries.

### 3.4 Normalization (the payload → `Order` translation)

This is where most of the complexity lives (`libraries/grabfood/orders.py`,
`libraries/gofood/orders.py`, `libraries/shopeefood/__init__.py`). Responsibilities:

- **Resolve the store** from the aggregator outlet id / partner-merchant id.
- **Map external item ids → internal `Inventory`.** Omni encodes its own inventory/modifier ids *into*
  the menu it uploads, then decodes them on the way back (`get_original_id` strips an id prefix). This is
  the key that makes round-tripping possible — **you own both sides of the id.**
- **Un-bake prices.** Aggregators send **tax-inclusive** totals with discounts already applied. Omni must
  *reverse-engineer* subtotal, tax, packaging fee, and per-item/order discounts to store clean net figures.
  See `generate_order_data` (Grab) and `parse_order_payload` (Go). Tax can be taken from Omni settings or
  derived from the payload (`calculate_tax`). This is fiddly, merchant-configurable, and a bug magnet.
- **Expand modifiers into behaviours.** Modifiers aren't just add-ons; a modifier can *replace* the item
  (`REPLACE_ITEM`), *upsize* it (`UPSIZE_ITEM` → swap to a larger variant + its inventory), *create an
  extra line item* (`CREATE_EXTRA_ITEM`), or *turn an item into a meal* (`MAKE_INTO_MEAL` auto-adds a
  default drink). Both Grab and Go implement the same behaviour set with near-duplicate code.
- **Discounts & who funds them.** Merchant-funded vs aggregator-funded promos are separated because only
  merchant-funded amounts reduce merchant revenue. Grab "slash price" and Go "applied_promotions" each have
  a configurable `SlashPriceBehavior` (save as subtotal reduction vs as an order-level discount).
- **Create side records**: `AggregatorMetadata`, `DeliveryInfo` (address/coords/notes for delivery),
  `FBMetadata` (F&B sequence number), an aggregator `Payment` (`create_aggregator_payment`), and a
  sequence number.

### 3.5 Forward to POS — configurable trigger event

Omni does **not** always forward on create. Each aggregator's settings pick *which lifecycle event*
triggers POS delivery, per order type:

```python
# libraries/gofood/orders.py
def send_order_to_pos_if_needed(order, event):
    if order.pos_delivery_status:           # already sent → idempotent no-op
        return
    if (order.type == DELIVERY and gofood_settings.delivery_pos_trigger_event == event) or \
       (order.type == TAKE_OUT and gofood_settings.takeout_pos_trigger_event == event):
        order.send_to_pos(delay_duration=gofood_settings.send_to_pos_delay_duration)
```

Why: some merchants want the order to hit the kitchen only once a driver is allocated/arrived (to reduce
food waste on cancellations); others want it instantly. Grab is coarser (`delivery_pos_trigger_event`
∈ {CREATED, DRIVER_ALLOCATED, DRIVER_ARRIVED}; take-out/dine-in only on CREATED); Go is finer (separate
delivery/takeout/complete triggers + a `send_to_pos_delay_duration`).

### 3.6 POS delivery mechanics (`store_connect/orders.py`)

- Order is serialized (`serialize_order`) and POSTed to StoreConnect/ATO. On success Omni stores
  `downstream_order_id` + `pos_order_number` and marks `pos_delivery_status = SUCCESSFUL`
  (which also makes `send_order_to_pos_if_needed` idempotent forever after).
- **Async path**: mark `PENDING` and let a cron/RQ worker batch-send concurrently
  (`send_orders_concurrently`, `ThreadPoolExecutor`). Sync path retries with backoff.
- **Connectivity resilience**: on timeout, Omni *queries* the POS "by reference id" to check whether the
  order actually landed before retrying, avoiding duplicate POS orders.
- **Failure policy differs for aggregator orders**: a normal web order can be auto-cancelled on POS
  failure; **an aggregator order is never auto-cancelled** (`order.placed_via_aggregator` guard) — you
  can't cancel on Grab's behalf, so Omni logs/ignores instead. **Important porting rule.**

### 3.7 Status callbacks → internal state machine

After creation, aggregators send lifecycle callbacks that map to state transitions:

- **Grab**: one endpoint `order/state` with a `state` string → `OrderStateForm` maps to a
  `GRABFOOD_*` status, dispatches to `accept/confirm/in_transit/complete/cancel`
  (`libraries/grabfood/orders.py`). Each transition re-checks the monotonic status guard and may
  re-trigger POS send.
- **GoFood**: separate endpoints per event (`order-created`, `merchant-accepted`, `otw-pickup`,
  `driver-arrived`, `cancel`, `order-completed`). `driver_arrived`/`complete` can auto-complete the
  Omni order depending on `complete_order_trigger_event`. Omni can also **push status back** to Go
  (`send_mark_food_ready` PUTs "food prepared" to Go's API — a rare *outbound status* case, with RQ
  retries and 404/409 reconciliation).
- **ShopeeFood**: `order/status` endpoint; `OrderStatus` form detects **retry submissions** by comparing
  the incoming status to the stored one before acting.

---

## 4. Outbound flow (Omni → aggregator): menu, price, stock, promos

This is the half most POS teams underestimate. Omni is the **menu source of truth** and pushes to each
aggregator.

### 4.1 Menu upload (full catalog)

- Grab uses a **pull** model: Grab calls Omni's `merchant/menu` endpoint and Omni returns the serialized
  catalog (`GetMenuForm.get_data`, `libraries/grabfood/serializers.py`). Omni then **notifies** Grab to
  re-pull (`notify_menu_update`) and Grab reports back async via `menu/sync-status`.
- GoFood & ShopeeFood use a **push** model: Omni builds a catalog payload (`get_catalog_payload` for Go,
  `upload_menu` for Shopee) and POSTs it, then polls/receives a sync-status callback.
- Menu is assembled from `Store.get_aggregator_inventories(type=...)`, grouped by product Group, sorted by
  an aggregator-specific position, and each item/modifier is serialized with channel price (tax-adjusted),
  photos (sized), and availability.

### 4.2 Config sets (per-channel menu overrides)

`AggregatorSettings.*_config_set` lets a store present a **different menu per channel** (different names,
prices, positions, which modifiers appear) without duplicating products. `use_config_set(type)` toggles
between "use the raw inventory" and "use the config-set override" throughout the serializers. This is a
strong idea if your business needs channel-specific menus; skip it if you don't (adds real complexity).

### 4.3 Targeted availability / stock sync (out-of-stock integration)

Instead of re-uploading the whole menu when one item sells out, Omni pushes **single-item availability**:
`update_menu_availability(inventory_id)` / `update_modifier_availability(...)` (per aggregator in
`libraries/*/utils.py`). Gated by flags like `GrabFoodSettings.enable_out_of_stock_integration`.
These are typically fired from inventory-change signals/tasks and run on RQ with retries.

### 4.4 Promotions

`AggregatorInventoryPromotion` + per-aggregator `create_promotions` / `delete_campaigns` push discount
campaigns to the aggregator and, crucially, **record the campaign id** so that when an order comes back
referencing that campaign, Omni knows whether the discount was merchant-funded (Grab
`get_item_slash_price_campaign_ids` cross-checks incoming campaign ids against uploaded ones).

### 4.5 Store open/close & bulk ops

`pause_store`/`unpause_store` (Grab), `update_store_status` (Go) toggle the outlet online/offline. Bulk
helpers (`sync_*_stores`, `bulk_upload_promotions`, `bulk_send_catalogs`) fan out across a merchant's
stores via RQ jobs — menu ops are slow and must be async.

---

## 5. Per-aggregator cheat sheet

| Dimension | GrabFood | GoFood | ShopeeFood |
|---|---|---|---|
| Inbound auth | OAuth2 + scopes | HMAC body signature | OAuth2 (+ optional HMAC) |
| Menu ownership | Grab pulls from Omni | Omni pushes | Omni pushes |
| Order create | single `orders` endpoint, supports **edited orders** | `order-created`/`merchant-accepted` | `orders` endpoint |
| Status callbacks | one `order/state` + state string | many endpoints, one per event | `order/status` |
| Outbound status | none | **mark food ready** (PUT back to Go) | dish/option availability |
| Prices arrive as | tax-inclusive, `×100` minor units | tax-inclusive, already computed | tax-inclusive, divisor-normalized |
| Expected ack | **HTTP 204** | 204 | JSON OK envelope |
| Dedup quirk | edited-order replace-items path | double-order (customer+total, 5 min) | retry-submission status compare |
| Success code enum band | 100–170 | 5–30 | 210–270 / 305–340 |
| Loyalty hook | `v1/reward` (stamps calc), membership | — | — |

---

## 6. Merchant-configurable behaviour flags (why it's not one-size-fits-all)

These live on `{Grab,Go,Shopee}FoodSettings` and materially change processing. When porting, decide which
you actually need — each flag is a support/QA cost:

- **POS trigger event** (`delivery_pos_trigger_event`, `takeout_pos_trigger_event`,
  `complete_order_trigger_event`) — when the kitchen sees the order.
- **`send_to_pos_delay_duration`** — deliberate delay before POS send.
- **`allow_double_order`** — enable/disable the 5-minute dedup.
- **`slash_price_behavior`** — how item discounts hit subtotal vs order discount (affects reported revenue).
- **`delivery_fee_discount_behavior`** — whether delivery-fee promos are tracked.
- **`enable_out_of_stock_integration`**, **`use_internal_position`**, **`image_size`** — menu presentation.
- **Per-event notification-subscription ids + is_active** (Go) — Omni registers/【un】registers webhook
  subscriptions with Go's API and tracks each one.
- **Versioned URLs** (Go `CreateNotificationUrl`/`UpdateMenuUrl`/…: `old_url` vs `v1`) — the integration
  straddles two API generations via a `TextChoices` switch. See §7.

---

## 7. Weaknesses, flaws & tech debt in the current system

Report these honestly so the target project doesn't inherit them:

1. **No service layer for integrations.** All logic is module-level functions in `libraries/*`,
   violating the repo's own `CLAUDE.md`. Hard to unit-test in isolation, easy to create circular imports
   (note the local `from ... import` inside functions to dodge cycles).
2. **Grab and Go duplicate ~80% of order/modifier logic** (`save_items`, upsize/replace/extra-item
   handling, tax un-baking) with subtle divergences. A shared modifier-expansion + price-normalization
   core would remove a large class of "fixed in Grab but not Go" bugs.
3. **`save_items` is flagged `# noqa: C901`** (too complex) in both Grab and Go — high cyclomatic
   complexity, many `TODO`s, comments admitting unhandled cases (e.g. Grab "still does not know how to
   send edited order to POS", decimal-modifier-subtotal stored as int).
4. **Money as `float`.** Prices/tax/discounts are Python floats throughout (`FloatField`), with manual
   rounding via `merchant.settings.round`. This is a correctness risk for financial data; **use `Decimal`
   in the target project.**
5. **Mixed-language comments** (English + Indonesian) in `libraries/grabfood/orders.py` reduce
   maintainability for a new team.
6. **Dual API generations live simultaneously** (Go `old_url`/`v1`). Migration is incomplete; both paths
   must be maintained.
7. **Signature verification is bespoke per aggregator** and interacts with DRF request parsing (raw body
   vs canonical JSON). Fragile; a subtle change in body handling silently breaks auth.
8. **Idempotency relies on Redis lock availability.** If Redis is degraded, duplicate-order protection
   weakens. There's no DB unique constraint shown on `(type, external_order_id)` as a backstop — consider
   adding one.
9. **Status enum is one giant flat enum.** Convenient for comparisons, but adding an aggregator means
   editing a central model + migration; bands are hand-assigned and could collide.
10. **Outbound status is one-directional and partial** (only Go "mark food ready"). POS→aggregator status
    sync (e.g. "order rejected by kitchen") is thin.
11. **Tax logic is scattered and merchant-tunable** across `calculate_tax`, `get_tax_percentage`,
    `AggregatorSettings.*_tax_percentage`, and `tax_calculation_method` — easy to get wrong on edge cases
    (split orders, `merchantFundPromo`), acknowledged in code comments.

---

## 8. Feature inventory (what an aggregator integration for a POS should cover)

Use this as a checklist. ✅ = Omni has it; ⚠️ = partial; ❌ = missing/weak.

**Order ingestion**
- ✅ Receive & normalize orders from N aggregators
- ✅ Concurrency lock per external order id
- ✅ Idempotent create (existence check + lock)
- ✅ Business-rule duplicate detection (Go)
- ✅ Edited-order handling (Grab replace-items)
- ✅ Delivery vs take-out vs dine-in mapping
- ✅ Address / driver / customer capture
- ✅ Correct per-aggregator ack codes

**Order lifecycle**
- ✅ Status state machine with out-of-order guards
- ✅ Configurable POS-send trigger per event/order-type
- ✅ Cancellation handling (never auto-cancel aggregator orders)
- ⚠️ Outbound status to aggregator (only Go mark-food-ready)

**Menu / catalog (outbound)**
- ✅ Full menu upload/pull per aggregator
- ✅ Per-channel pricing (`AggregatorInventorySettings`)
- ✅ Per-channel menu overrides (config sets)
- ✅ Modifier groups + behaviours (upsize/replace/extra/meal)
- ✅ Photos, positions, selling times
- ✅ Async sync-status reconciliation

**Availability & pricing ops**
- ✅ Single-item out-of-stock push
- ✅ Modifier availability push
- ✅ Store pause/unpause (open/close)
- ✅ Promotion/campaign create+delete with id tracking
- ✅ Bulk multi-store operations (RQ fan-out)

**POS forwarding**
- ✅ Serialize + deliver to POS, store downstream ids
- ✅ Sync + async(batched) delivery
- ✅ Connectivity reconciliation (query-by-reference before retry)
- ✅ Configurable on-failure policy + error-report emails

**Financial**
- ✅ Tax un-baking, packaging fee, delivery fee, discounts
- ✅ Merchant-funded vs aggregator-funded promo separation
- ✅ Net vs gross revenue
- ⚠️ Uses float (should be Decimal)

**Observability**
- ✅ `ApiLog` / `OrderLog` audit trail per action
- ✅ Request logging (`request_loggers`)
- ✅ Sentry capture
- ⚠️ Reconciliation/settlement reporting against aggregator payouts — **not evident; recommended (see §9)**

---

## 9. Recommended features to ADD (missing or thin in Omni)

For a modern POS aggregator layer, prioritize:

1. **Settlement / payout reconciliation.** Ingest aggregator settlement reports and reconcile
   commission, promo funding, and net payout against Omni's recorded per-order figures. This is where
   merchants lose money and Omni currently has no visible answer.
2. **Bidirectional status sync.** Push POS/kitchen states (accepted, preparing, ready, rejected,
   out-for-delivery) back to *all* aggregators, not just Go. Reduces manual tablet juggling.
3. **Decimal money + a single pricing/tax engine.** One tested module that both un-bakes inbound totals
   and bakes outbound prices, shared by all aggregators.
4. **Unified adapter interface** (see §11) to kill the Grab/Go duplication.
5. **DB-level idempotency backstop**: unique `(aggregator_type, external_order_id)` constraint +
   an inbound `WebhookEvent` table (store raw payload, dedup by event id, enable replay).
6. **Dead-letter + replay** for failed webhooks and failed POS deliveries (beyond RQ retries).
7. **Menu diffing** to push only changed items (Omni mostly re-uploads or pushes single items; a proper
   diff reduces API load and sync errors).
8. **Rate-limit / backoff awareness** per aggregator API (menu ops especially).
9. **Config-driven aggregator registry** so onboarding a new aggregator is data + one adapter class, not
   edits across a dozen files + a central enum migration.
10. **Contract tests / recorded-fixture tests** per aggregator payload version (guards against the
    old_url/v1 drift problem).

---

## 10. Recommended features to REDUCE / drop (don't cargo-cult these)

- **The flat 700-line `AggregatorMetadata.Status` enum** — replace with per-aggregator status + a mapping
  to a small canonical lifecycle (see §11). Keep the *idea* of monotonic ordering, drop the giant enum.
- **Config sets** — only if the target business genuinely needs per-channel menus. Otherwise it's a large
  ongoing complexity tax.
- **Dual API-generation URL switches** — pick one API version; don't port `old_url`/`v1` straddling.
- **Per-event notification-subscription bookkeeping** — only relevant to Go's subscription model; skip for
  aggregators that don't require it.
- **Bespoke float rounding helpers** — replaced by a Decimal engine.
- **Loyalty/stamps endpoints** (`v1/reward`, membership) — Omni/BK-specific; drop unless target has the
  same loyalty program.

---

## 11. How to adapt this to the TARGET project's ecosystem

> This section is deliberately generic because the target stack may differ. Fill in the bracketed choices.

### 11.1 First, characterize the target

Before porting, the agent should answer (ask the user or infer from the target repo):

- **Framework**: Django? FastAPI? Node/Nest? Rails? → shapes where "views" and "tasks" go.
- **Async/queue**: Celery? RQ? Sidekiq? cloud tasks? → menu ops + POS delivery must be async.
- **Money type available**: Decimal/money lib? → mandate it; do not copy Omni's floats.
- **Which aggregators + which countries** (payload versions differ by region).
- **Menu ownership**: does the target want to be the menu source of truth (like Omni) or let the
  aggregator own the menu? This decides whether you build §4 at all.
- **POS target**: is there a StoreConnect-equivalent downstream, or is the target itself the POS
  (so "forward to POS" becomes "create local order")?
- **Multi-tenancy**: per-merchant/store scoping like Omni, or single-tenant?

### 11.2 Recommended target architecture (framework-agnostic)

```
inbound webhook  ─▶  [Transport layer]      auth + signature verify + raw-body capture
                     [WebhookEvent store]   persist raw payload, dedup by event id
                     [Adapter.parse_order]  aggregator payload -> CanonicalOrder DTO
                     [OrderService.ingest]  DTO -> domain Order (Decimal money)
                     [Idempotency]          DB unique (aggregator, external_id) + lock
                     [Dispatch]             forward to POS / create local order (async)
                     [Adapter.map_status]   status callback -> CanonicalStatus -> transition

outbound         ◀─  [MenuService.build]    domain catalog -> CanonicalMenu
                     [Adapter.serialize]    CanonicalMenu -> aggregator payload
                     [Adapter.push_*]       upload menu / availability / promo / store-status
```

Define **one adapter interface**, implement once per aggregator:

```python
class AggregatorAdapter(Protocol):
    type: AggregatorType
    # inbound
    def verify(self, request) -> None: ...                       # auth/signature
    def parse_order(self, payload) -> CanonicalOrder: ...
    def map_status(self, payload) -> CanonicalStatus: ...
    def ack_response(self, ok: bool): ...                        # per-aggregator success code
    # outbound
    def serialize_menu(self, menu: CanonicalMenu) -> dict: ...
    def push_menu(self, store, payload): ...
    def push_availability(self, item, available: bool): ...
    def push_status(self, order, status): ...                   # bidirectional (add this!)
```

Canonical lifecycle (small, shared) instead of Omni's flat enum:

```
CREATED → ACCEPTED → PREPARING → READY → PICKED_UP → COMPLETED
                                   └────────────────→ CANCELLED / FAILED
```

Each adapter maps its native states into this + keeps the aggregator-native code in
`WebhookEvent`/metadata for audit. Keep Omni's **monotonic-comparison** guard on the canonical order.

### 11.3 What to copy vs rebuild

| Omni concept | Copy as-is? | Guidance |
|---|---|---|
| Normalized `Order` + `AggregatorMetadata` split | ✅ copy the idea | best part of the design |
| Per-store external-id mapping (`AggregatorSettings`) | ✅ | essential |
| Per-item channel pricing (`AggregatorInventorySettings`) | ✅ if you own the menu | |
| Redis lock per external order id | ✅ | add DB unique constraint too |
| Configurable POS-trigger-event | ✅ | genuinely useful |
| "Never auto-cancel aggregator order" rule | ✅ | correctness rule |
| Query-by-reference reconciliation before retry | ✅ | prevents dup POS orders |
| Flat 700-line status enum | ❌ rebuild | canonical lifecycle + adapter mapping |
| `libraries/*` module-fn structure | ❌ rebuild | proper service layer + adapter classes |
| Float money | ❌ rebuild | Decimal |
| Grab/Go duplicated `save_items` | ❌ rebuild | one shared modifier-expansion core |
| Config sets, subscription bookkeeping, dual URLs | ⚠️ only if needed | drop otherwise |

### 11.4 Concrete porting order (suggested plan)

1. Define `CanonicalOrder`, `CanonicalMenu`, `CanonicalStatus` DTOs + Decimal money.
2. Build `OrderService.ingest` + idempotency (DB unique + lock + `WebhookEvent`).
3. Implement **one** adapter fully (pick the aggregator the target needs most) end-to-end:
   verify → parse → ingest → forward → status transitions.
4. Add the outbound menu path for that same aggregator (only if target owns the menu).
5. Extract the shared modifier-expansion + tax engine once you have the second adapter to compare.
6. Add bidirectional status push + settlement reconciliation (the two biggest gaps vs Omni).
7. Contract tests with recorded payload fixtures per aggregator + version.

---

## 12. Key files to read first (for the porting agent, in order)

1. `ordering_system/apps/orders/models.py:2297` — `AggregatorMetadata` + the status enum (the model).
2. `ordering_system/api/food/views.py` — the three auth strategies.
3. `libraries/grabfood/orders.py` — the fullest inbound example (create/update/state machine/modifiers).
4. `libraries/gofood/orders.py` — compare/contrast + outbound "mark food ready".
5. `libraries/shopeefood/__init__.py` — the class-based variant (menu upload + order create in one class).
6. `ordering_system/store_connect/orders.py` — forwarding to POS + resilience.
7. `libraries/gofood/utils.py` (`get_catalog_payload`, `upload_menus`) — outbound menu serialization.
8. `ordering_system/apps/merchants/models.py:880` — the behaviour flags that drive everything.
9. `ordering_system/apps/stores/models.py:1223` + `ordering_system/apps/inventories/models.py:872` —
   store/item aggregator mapping + per-channel price.

---

*End of guide. When adapting, prefer the normalization boundary and the idempotency/state-machine
patterns; rebuild the money handling, the flat status enum, and the duplicated per-aggregator logic.*
