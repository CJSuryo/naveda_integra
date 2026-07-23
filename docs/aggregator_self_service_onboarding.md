# Self-Service Aggregator Onboarding — Design & Runbook

> **Goal.** Turn today's devops-heavy, confirmation-gated aggregator setup (GrabFood, GoFood,
> ShopeeFood) into a **guided wizard** any low-skill employee — or the client themselves — can run
> safely, from creating the aggregator merchant account to seeing live orders flow into Omni.
> Robust, idempotent, reversible, auditable.
>
> This doc has two halves: **(A) the system design** to build, and **(B) the human runbooks** the
> operator follows. It is written to be actioned by another Claude Code agent; file refs are
> `stamps/ordering_system`-relative. Adapt the bracketed choices to the target project.

---

## 1. Why onboarding is slow today (grounded in the code)

| Step | Who does it now | Where | Why it's painful |
|---|---|---|---|
| Create Grab/Gojek/Shopee merchant + request API access | Client + devops (Slack back-and-forth) | Partner portals (external) | Manual, out-of-band, no tracking inside Omni |
| Enter merchant-level credentials (`client_id`, `client_secret`, `enterprise_id`, `notification_secret_key`, `base_url`, `auth_url`, API version) | **Devops only** | **Django admin** (`GrabFoodSettings`, `GoFoodSettings`, `ShopeeFoodSettings`) | Secrets + raw URLs typed by hand; easy to fumble; `old_url` vs `v1` version trap |
| Create OAuth2 Application (token issuance for Grab/Shopee) | Devops | Django admin (`oauth2_provider`) | Manual, no link to the aggregator record |
| Register GoFood webhook subscriptions (**7 events**) | Devops (script/shell) | `create_notification_subscription()` per `EVENT` (`libraries/gofood/utils.py`) | 7 API calls, each stores a `*_notification_id`; error-prone, no UI |
| Link store ↔ outlet id (`grab_food_store_id`, `gofood_store_id`, `shopeefood_store_id`) | Grab: self-service; Go/Shopee: manual | `AggregatorSettings` (backoffice edit) | Only Grab is automated (activation URL callback) |
| Upload menu + verify sync | Client (backoffice button) → RQ jobs | `backoffices/aggregators/...` bulk sync | Works, but no pre-flight validation; failures surface late |

**Key insight:** one aggregator (Grab) already has the *right* pattern —
`get_activation_url` → client redirected to Grab → Grab calls `pushIntegrationStatus` →
`grab_food_store_id` auto-populated (`api/food/grab/forms.py` `StoreIntegrationForm`). The whole
project should be **"make every aggregator feel like Grab's activation flow."**

**Already reusable, don't rebuild:** backoffice RBAC (`@has_permission(STORE_MANAGE)`), bulk menu
sync (RQ fan-out), `ApiLog`/`Log` audit trail, FCM realtime order push (`publish_new_order` →
Firebase topic = `store.pubsub_key`), and the new unified `FoodAggregatorSettings` model (already
stores `access_token` + refresh + expiry — the seed of a clean credential vault).

---

## 2. Target experience (what the operator sees)

A single **"Connect a delivery channel"** wizard in the client backoffice. Per aggregator, a linear
stepper with one clear action per screen and a live status badge:

```
[ Choose channel ]  →  [ Prerequisites ]  →  [ Connect account ]  →  [ Link stores ]
                                                                            ↓
[ Go live ✅ ]  ←  [ Verify (pre-flight) ]  ←  [ Push menu ]  ←  [ Set channel pricing/tax ]
```

Principles:
- **One decision per screen.** Operator never sees a raw URL or a secret they must know.
- **Region-templated config.** Operator picks *Country/Environment* (e.g. "Indonesia / Production");
  Omni fills `base_url`, `auth_url`, API version, scopes from a **template registry** (no typing).
- **Delegate identity to the aggregator.** OAuth/activation redirect where possible (Grab-style), so
  the client authorizes on the aggregator's own site and Omni receives credentials/ids via callback.
- **Everything idempotent + resumable.** Close the tab, come back, continue from the same step.
- **Nothing goes live until pre-flight passes.** Green checks required before "Go live" unlocks.
- **One-click disconnect / rollback** at any time.

---

## 3. System design

### 3.1 Onboarding state machine (the backbone)

Add an `OnboardingSession` (or extend `FoodAggregatorSettings`) with an explicit status, so the wizard
is a resumable server-side workflow, not UI state:

```
NOT_STARTED
  → PREREQ_CONFIRMED          # operator ticked "account + API access exist"
  → CREDENTIALS_SET           # creds captured (via OAuth callback or template form)
  → ACCOUNT_CONNECTED         # token obtained + auth ping OK
  → WEBHOOKS_REGISTERED       # subscriptions created (GoFood 7 events) / OAuth app made
  → STORES_LINKED             # outlet ids mapped for ≥1 store
  → MENU_SYNCED               # catalog upload succeeded (sync-status callback OK)
  → PREFLIGHT_PASSED          # all health checks green
  → LIVE
  ↺ FAILED_<step> (with actionable error) / DISCONNECTED
```

Each transition is an **idempotent service function** (retry-safe). The UI only ever calls
"advance to next step"; the backend decides what that means per aggregator. This replaces the
scattered admin+shell steps with one audited pipeline.

### 3.2 Per-aggregator adapter for onboarding (mirror the order adapter)

Reuse the adapter idea from the integration guide. Each aggregator implements:

```python
class OnboardingAdapter(Protocol):
    def config_template(self, region, env) -> ConfigTemplate: ...   # URLs/scopes/version, no user typing
    def begin_connect(self, session) -> ConnectAction: ...          # returns redirect URL OR form schema
    def complete_connect(self, session, callback_payload) -> None: ...  # store creds/token
    def register_webhooks(self, session) -> None: ...               # GoFood: loop 7 EVENTs; others: no-op/OAuth app
    def link_store(self, session, store) -> LinkAction: ...         # Grab: activation URL; Go/Shopee: fetch/enter outlet id
    def preflight(self, session) -> list[Check]: ...                # auth ping, menu dry-run, webhook echo
    def push_menu(self, store) -> JobRef: ...                       # existing bulk upload
    def disconnect(self, session) -> None: ...                      # revoke tokens, delete subscriptions, unlink
```

- **Grab** `begin_connect` = OAuth redirect; `link_store` = existing `get_self_activation_url`.
- **GoFood** `register_webhooks` = wrap the existing `create_notification_subscription` loop over all
  `EVENT`s into **one idempotent call** (already exists, just needs a UI trigger + "re-sync webhooks"
  button that reconciles stored `*_notification_id`s).
- **ShopeeFood** `complete_connect` = OAuth token exchange; auto-create the OAuth2 Application.

### 3.3 Credential vault (safety-critical)

- **Encrypt secrets at rest** (`client_secret`, `notification_secret_key`, tokens). Today they're
  plain `CharField`s. Use field-level encryption / a KMS / `django-fernet-fields`-style wrapper.
- **Operator never reads secrets back.** Show masked (`••••1234`) + "rotate" action only.
- **Templated URLs, not free text.** A `ConfigTemplate` registry keyed by
  `(aggregator, country, environment, api_version)` supplies `base_url`/`auth_url`/scopes. Kills the
  `old_url`/`v1` mistakes and typo'd endpoints.
- **Auto token refresh** using the `access_token_expiration` / `refresh_token` fields already on
  `FoodAggregatorSettings`; a scheduled job refreshes before expiry so integrations don't silently die.

### 3.4 Pre-flight health checks (the trust gate)

Before "Go live" unlocks, run and display a checklist (each ✅/❌ with a fix hint):

1. **Auth** — obtain/validate token (Grab/Shopee) or sign a test payload (GoFood HMAC).
2. **Store link** — outlet id present + resolvable on aggregator (`get_store_open_status` for Grab).
3. **Webhook reachability** — send a signed **test event** to Omni's own webhook and confirm 2xx +
   correct ack code (Grab wants 204, Shopee its envelope). Catches signature/routing misconfig *before*
   real orders.
4. **Menu dry-run** — build the catalog payload and validate it (no unmapped items, prices > 0, images
   present) **without** publishing. Surfaces the `save_items`/mapping gaps early.
5. **Clock/version** — confirm API version + tax percentage set for the channel.

Store results on the session; re-runnable. This is what makes it safe for a low-skill operator — the
system, not the human, decides readiness.

### 3.5 Store sync + menu push

Already implemented (bulk RQ jobs). Wizard just triggers `push_menu` per store and watches the
sync-status callback (`menu/sync-status` for Grab, notification result for Shopee, sync callback for
Go), showing a progress badge. Add **menu diffing** later to push only changes (see integration guide §9).

### 3.6 Order intake in real time — FCM today, WebSocket option

**What exists:** new orders are pushed to the POS app via **Firebase Cloud Messaging topics**
(`publish_new_order(order, store.pubsub_key)`, `apps/stores/notifications.py`). This already gives
near-real-time delivery to devices and survives app restarts (FCM handles reconnection/queueing).

**Do you need WebSockets?** Decision guide:

| Use case | Recommendation |
|---|---|
| Native POS/mobile app receiving orders in background | **Keep FCM.** Battery/reconnect/delivery handled for you; websockets are worse here. |
| Backoffice **live order board** in the browser (web dashboard, no native push) | **Add WebSocket** (or SSE) — browsers can't use FCM topics cleanly; a socket gives instant in-page updates. |
| Two-way, low-latency (KDS acknowledging, live status) | **WebSocket** ([Django Channels] + Redis channel layer). |
| Simple one-way "new order" toast in web | **SSE** is enough and far simpler than Channels. |

**Recommended shape if adding sockets (Django):**
- `[Django Channels]` with the **Redis channel layer** (Redis already present for RQ/cache).
- One group per store: `store_<pubsub_key>`. On order create, the same hook that calls
  `publish_new_order` also does `channel_layer.group_send("store_<key>", {...})`.
- Auth the socket with the existing session/OAuth; authorize the store via the employee's `can_access`.
- **Keep FCM as the source of truth / fallback**; the socket is an enhancement for connected web
  clients, not a replacement. Don't make order delivery *depend* on a live socket.

> If the target project is **not** Django, use the platform-native equivalent (ASGI + `websockets`,
> Socket.IO, Phoenix Channels, ActionCable, or a managed service like Ably/Pusher). Same rule:
> socket = enhancement for connected clients; durable push (FCM/APNs) = the guarantee.

### 3.7 Safety rails for a low-skill operator

- **RBAC split**: client self-serve steps (link store, set price, push menu) vs restricted steps
  (rotate secret, change base URL/version) gated to a higher permission / devops. Reuse
  `employee_permissions.Permission`.
- **Guarded, reversible actions**: every step has a matching undo (disconnect deletes GoFood
  subscriptions, revokes tokens, clears outlet ids). No dead-ends.
- **Idempotent retries**: re-clicking "Connect" or "Register webhooks" reconciles instead of
  duplicating (check existing `*_notification_id` before creating).
- **Plain-language errors**: map aggregator error codes → operator-friendly messages + "what to do".
- **Full audit**: keep writing `ApiLog`/`Log` per action with the acting user (already the pattern).
- **Rate-limit + lock** onboarding actions per merchant (reuse the Redis `lock`) so double-clicks and
  concurrent operators don't corrupt state.
- **Dry-run everything that mutates the aggregator** before the live push.

---

## 4. Runbooks (the human step-by-step, per aggregator)

> These are the guided-wizard scripts. Each "Omni does X" is an automated wizard action; each
> "You do X" is an operator/client action. Times are indicative.

### 4.1 GrabFood

**Prerequisites (client, on Grab)**
1. Create/So have a **GrabFood Merchant** account at the Grab Merchant Portal.
2. Request **GrabFood Partner API** access for the merchant; obtain `client_id` + `client_secret`
   (or authorize Omni as a connected app — preferred).

**In Omni (wizard)**
3. Choose channel → **GrabFood**. Pick *Country / Environment* → Omni fills URLs, scopes, version.
4. **Connect account**: click *Authorize on Grab* → redirected to Grab → approve → back to Omni
   (`ACCOUNT_CONNECTED`). Omni auto-creates the OAuth2 Application for token issuance.
5. **Link store**: click *Activate* per store → Omni calls `get_self_activation_url` → redirect to
   Grab → approve → Grab calls `pushIntegrationStatus` → `grab_food_store_id` auto-set
   (`STORES_LINKED`).
6. **Channel pricing/tax**: set `grab_tax_percentage` + per-item Grab prices (or reuse base).
7. **Push menu**: click → Grab pulls Omni's menu, reports via `menu/sync-status` (`MENU_SYNCED`).
8. **Verify** → pre-flight checks → **Go live**. First real order arrives on `orders` webhook (ack 204).

### 4.2 GoFood (Gojek)

**Prerequisites (client, on Gojek)**
1. Create **GoBiz / GoFood Merchant** account; request GoFood Integration API access.
2. Obtain `enterprise_id`, `client_id`, `client_secret`, and the outlet ids for each store.

**In Omni (wizard)**
3. Choose channel → **GoFood**. Pick region/env → URLs + API version (`v1`) auto-filled.
4. **Connect account**: enter/confirm `enterprise_id` (+ Omni generates the
   `notification_secret_key`); Omni fetches a token and pings (`ACCOUNT_CONNECTED`).
5. **Register webhooks (one click)**: Omni loops all 7 `EVENT`s calling
   `create_notification_subscription` with Omni's `food-panda`-style webhook URLs, storing each
   `*_notification_id` (`WEBHOOKS_REGISTERED`). "Re-sync webhooks" reconciles if any drift.
6. **Link store**: enter/confirm `gofood_store_id` per store (or fetch via Go outlet API if available).
7. Set `shopee_food_tax_percentage`/Go tax + POS-trigger events (delivery/takeout/complete).
8. **Push menu** → sync callback → **Verify** (includes a signed test webhook) → **Go live**.

### 4.3 ShopeeFood

**Prerequisites (client, on Shopee)**
1. Create **ShopeeFood Merchant** account; request Partner/Open API access; obtain `client_id`
   (vendor id) + `client_secret`.

**In Omni (wizard)**
2. Choose channel → **ShopeeFood**. Pick region/env → URLs/scopes auto-filled.
3. **Connect account**: OAuth authorize → token stored; Omni auto-creates OAuth2 Application; decide
   `signature_verification` on/off (recommend **on**) (`ACCOUNT_CONNECTED`).
4. **Link store**: map `shopeefood_store_id` per store.
5. Set `shopee_food_tax_percentage`.
6. **Push menu** (`upload_menu`) → menu notification result callback → **Verify** → **Go live**.

---

## 5. Implementation plan (mapped to this codebase)

1. **Add `OnboardingSession` status + service pipeline.** New app `apps/aggregator_onboarding/` with
   `services.py` holding the idempotent transition functions. (Respect the Service-Layer rule the repo
   already mandates in `CLAUDE.md`.)
2. **Define `OnboardingAdapter` per aggregator**, wrapping the *existing* functions
   (`get_self_activation_url`, `create_notification_subscription`, `upload_menus`,
   `get_store_open_status`) — mostly orchestration, little new integration code.
3. **Config template registry** keyed by `(aggregator, country, env, version)` to eliminate manual
   URL/version entry; back it with `default_configs/`.
4. **Encrypt credential fields** on `*FoodSettings` / `FoodAggregatorSettings`; add masked-display +
   rotate; move secret-changing behind a devops-only permission.
5. **Pre-flight checks module** (auth ping, store resolve, signed test-webhook echo, menu dry-run).
6. **Wizard UI** in `backoffices/aggregators/` (stepper template) driving the pipeline via one
   "advance" endpoint per aggregator; show live badges from `ApiLog`/sync callbacks.
7. **One-click GoFood webhook registration + reconcile**, and **auto OAuth2 Application creation** for
   Grab/Shopee, replacing the admin/shell steps.
8. **Disconnect/rollback** path per adapter.
9. *(Optional)* **WebSocket live order board**: add `[Django Channels]` + Redis channel layer, emit
   `group_send` alongside the existing `publish_new_order`; keep FCM as the durable guarantee.
10. **Runbook content** (this doc §4) rendered inline in each wizard step as contextual help.

**Sequencing:** 1→2→5 give a safe, resumable, self-validating pipeline even before the polished UI.
The UI (6) and websocket board (9) are enhancements on top.

---

## 6. Adapting to a different target project

- **Not Django?** Keep the state machine + adapter + pre-flight + credential-vault concepts; swap the
  framework primitives (ASGI/Socket.IO/Ably for sockets; your KMS for secrets; your queue for the async
  webhook/menu jobs).
- **Target already owns menus?** Keep §3.5/§4 menu steps. **Aggregator owns the menu?** Drop menu push;
  onboarding shrinks to connect + link + webhook + verify.
- **Fewer aggregators / single region?** Collapse the config-template registry to constants, but keep
  the "operator never types a URL/secret" rule.
- **No native app, web-only POS?** Then the WebSocket/SSE board (§3.6) becomes primary, not optional —
  but still pair it with a durable store (DB poll fallback) so a dropped socket never loses an order.
- **Golden rule to carry over:** *make every aggregator feel like a single "Authorize → auto-configure
  → verify → go live" flow, with the system (not the human) gating readiness.*

---

*End. Build the state machine + adapters + pre-flight first; that alone removes most devops toil and
makes the flow safe for a low-skill operator. UI polish and WebSockets are the finishing layer.*
