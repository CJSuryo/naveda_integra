# Aggregator Self-Service Onboarding — Capability Answer, Build Plan & Operator Tutorial

> **Question answered:** *Can GoFood and ShopeeFood really feel like Grab's activation flow?*
> **Short answer: GoFood — yes (and Omni is on the wrong integration model today). ShopeeFood — no,
> not with publicly available APIs; it stays a guided manual step.**
>
> This doc contains: **§1** the honest capability verdict, **§2** the revised build plan,
> **§3** the operator tutorial (written so a careful 12-year-old with admin access can follow it),
> **§4** what must be verified before the tutorial ships.

---

## 1. Capability verdict — can each aggregator do a Grab-style flow?

| Aggregator | Merchant-consent redirect? | Outlet auto-discovery? | Verdict |
|---|---|---|---|
| **GrabFood** | ✅ Yes — already built | ✅ Yes, via `pushIntegrationStatus` callback | **Already self-service.** Keep as the reference pattern. |
| **GoFood** | ✅ **Yes** — OAuth2 *Authorization Code* in the **Facilitator Model** (phone → OTP → consent page → Allow → redirect with `code`) | ✅ **Yes** — `GET /integrations/partner/v1/token-info` returns each outlet's id, name, address, phone, email | **Supported, but Omni doesn't use it.** Omni is on the older *Direct Integration* model. Migration required — see §2.1. |
| **ShopeeFood** | ❌ No public evidence | ❌ No | **Not available.** ShopeeFood POS partner APIs are gated/not openly documented; access is granted case-by-case. Keep credentials pre-provisioned + **one guided copy-paste step** for the store id. |

### 1.1 The GoFood finding (the important one)

GoBiz supports two models. Omni is on the wrong one for self-service:

| | **Direct Integration** (what Omni uses today) | **Facilitator** (what enables Grab-style flow) |
|---|---|---|
| Grant type | `client_credentials` | `authorization_code` (+ refresh token) |
| Who authorizes | Nobody — enterprise-level creds issued out-of-band | **The merchant**, via phone + OTP + consent screen |
| Scoping | `enterprise_id` (a whole chain) | Per-merchant token |
| Outlet ids | Typed in by hand | **Discovered** via `token-info` |
| Outlet linking | Manual mapping in Omni | `PUT /integrations/partner/outlets/{outlet_id}/v1/link/gofood` |

**Evidence in Omni's own code that this migration is small:**
- `libraries/gofood/utils.py:69` `get_bearer_token()` posts `grant_type: 'client_credentials'` — the
  thing to change.
- Default scopes there **already include** `partner:outlet:write partner:outlet:read` — the facilitator
  outlet scopes.
- `GoFoodSettings.CreateNotificationUrl.v1` is already `/integrations/partner/v1/notification-subscriptions`
  — i.e. Omni is **already calling the facilitator URL namespace**, just authenticating the old way.
- `FoodAggregatorSettings` already has `access_token`, `access_token_expiration`, `refresh_token`,
  `refresh_token_expiration` — the storage for authorization-code tokens already exists.

So the GoFood work is: **swap the grant, add consent redirect + callback, add token-info + link/unlink.**
Everything downstream (catalog upload, notification subscriptions, mark-food-ready, order webhooks)
stays as-is.

### 1.2 What this means for the operator experience

```
GrabFood    : Authorize → auto-link stores → push menu → verify → LIVE      (0 manual values)
GoFood      : Authorize → PICK outlets from a list → push menu → verify → LIVE  (0 typed values)
ShopeeFood  : [Omni devops one-time partner setup] → paste 1 store id → push menu → verify → LIVE
```

ShopeeFood never reaches zero manual steps, but it reduces to **one copy-paste of one value**, with a
guided screen showing exactly what that value looks like. That is achievable for a low-skill operator.

---

## 2. Revised build plan

Ordered by value. Items 1–3 remove most devops toil.

### 2.1 Migrate GoFood to the Facilitator (authorization-code) model — **highest value**

Scope:
1. Add `authorization_code` support to GoFood auth. Keep `client_credentials` behind a flag so existing
   enterprise merchants keep working during rollout (do **not** big-bang this).
2. Build consent redirect: send merchant to GoBiz authorize URL with `client_id`, `redirect_uri`,
   `scope`, and a **`state`** value.
3. Build callback endpoint: **verify `state` matches** what was sent, exchange `code` → access +
   refresh token (**code is one-time-use and expires in ~2 minutes** — exchange immediately), store
   encrypted on `FoodAggregatorSettings`.
4. Add scheduled **refresh-token job** before `access_token_expiration`.
5. Add `GET /integrations/partner/v1/token-info` → render the merchant's outlets as a **pick-list** in
   the wizard (name + address so the operator recognises their own store).
6. On selection: `PUT /integrations/partner/outlets/{outlet_id}/v1/link/gofood`, then write
   `AggregatorSettings.gofood_store_id`. Linking also sets Auto-Accept on GoBiz's side.
7. Disconnect path: `DELETE /integrations/partner/outlets/{outlet_id}/v1/link/gofood` + revoke tokens +
   delete the 7 notification subscriptions.

**Prerequisite:** Omni must be registered as a **GoBiz Partner** (facilitator) and be issued facilitator
credentials by the GoBiz team. This is a **one-time company-level action**, not per client.

### 2.2 One-click webhook registration + reconcile (GoFood)

Wrap the existing `create_notification_subscription()` loop over all 7 `EVENT` values into a single
idempotent service call. Before creating, check the stored `*_notification_id`; if present, `PUT`
(update) instead of `POST` (create). Expose as **"Register / Re-sync webhooks"** with a per-event
status list. Replaces today's manual/scripted step.

### 2.3 Onboarding state machine + pre-flight gate

As designed previously: resumable `OnboardingSession` status pipeline, per-aggregator
`OnboardingAdapter`, and a **pre-flight check** that must go green before **Go live** unlocks:
auth ping · outlet resolves · **signed test webhook echoes back with the correct ack code** ·
menu dry-run (no unmapped items, prices > 0) · tax + API version set.

### 2.4 Credential vault + config templates

Encrypt `client_secret` / `notification_secret_key` / tokens at rest; masked display + rotate only;
operator **never types a URL** — a `(aggregator, country, environment, api_version)` template registry
supplies `base_url` / `auth_url` / scopes. Kills the `old_url` vs `v1` class of bugs.

### 2.5 ShopeeFood: minimise, don't automate

Can't automate consent. Instead: Omni devops does the **one-time** partner credential setup per
merchant; the wizard then asks for exactly **one** value per store (`shopeefood_store_id`) on a screen
that shows a worked example and validates the format before accepting it.

### 2.6 Realtime order intake

Keep **FCM** (`publish_new_order` → topic `store.pubsub_key`) as the durable guarantee for native POS
apps. **Add WebSocket only for the browser live-order board** (Django Channels + Redis channel layer,
group per store, `group_send` emitted alongside the existing FCM call). Never let order delivery depend
on a live socket.

---

## 3. Operator tutorial

> **How to read this.** Each step says **who** does it, **where**, **what you're looking for**, **what
> it looks like**, and **how you know it worked**. If a step fails, the "If it goes wrong" line tells you
> what to do. Never invent values. Never share secrets in chat — paste them only into Omni's wizard.
>
> ⚠️ **Screens marked `[VERIFY]` need one screenshot pass against the live portal before this guide is
> handed to staff** — portal layouts change and are not publicly documented. See §4. Everything **not**
> marked `[VERIFY]` is confirmed from official API docs or Omni's code.

### 3.0 Before you start — the universal checklist

You need, for every aggregator:
- **Admin access** to the client's aggregator merchant account (not a staff/cashier login).
- **Admin (STORE_MANAGE) access** in Omni's backoffice for that client's merchant.
- The client's **store list** in Omni already created, each with a **store code**.
- The client's menu already correct in Omni (products, variants, prices). **The wizard publishes what
  Omni has — if the menu is wrong in Omni, it will be wrong on the aggregator.**

**Golden rules**
1. Do **one store at a time** for the first store; batch the rest only after the first goes live cleanly.
2. Never press **Go live** while any pre-flight check is red.
3. If you're unsure what a value is — stop and ask. Do not guess an ID.

---

### 3.1 GrabFood — fully self-service

**Time:** ~15 min per merchant + ~2 min per store.

#### Part A — On Grab (client's account)

**A1. Confirm the merchant account exists.**
Log in to the **Grab Merchant Portal**. You should see the client's restaurant name and their outlets.
- ✅ Success: you can see the outlet list.
- ❌ If there's no account: the client must register as a GrabFood merchant first. Stop here — that is
  a Grab sales process, not something you can do.

**A2. Confirm GrabFood Partner API access is enabled.** `[VERIFY]`
Look for the integrations/API section of the portal.
- ✅ Success: the merchant is eligible to connect a POS partner.
- ❌ If missing: the client (or your account manager) must request **GrabFood Partner API** access from
  Grab. Wait for Grab to confirm before continuing.

#### Part B — In Omni

**B1.** Log in to Omni backoffice as the client's merchant → **Aggregators → GrabFood**.

**B2.** Click **Connect**. Choose **Country = Indonesia** and **Environment = Production**.
- You should **not** be asked to type any web address. If a screen asks you to type a URL, **stop** —
  that's the old admin screen; escalate to devops.

**B3.** Click **Authorize on Grab**. Your browser goes to Grab's site.
- Log in with the client's **admin** Grab account and press **Allow / Approve**. `[VERIFY: exact button label]`
- ✅ Success: you're bounced back to Omni and the badge reads **Account connected**.
- ❌ "Something went wrong": press Authorize again (safe to retry — it's idempotent). If it fails twice,
  screenshot the error and escalate.

**B4. Link a store.** In the store list, find the store → press **Activate**.
- You're redirected to Grab, approve, and are returned to Omni.
- ✅ Success: the store row shows a **Grab Merchant ID** filled in automatically (a code from Grab), and
  the badge reads **Linked**. *You never type this ID — Omni receives it from Grab.*
- ⏳ If it says **Syncing**: Grab is still processing. **Wait — do not press Activate again.** Omni blocks
  re-activation for up to 24 hours on purpose. Come back later.
- ❌ "Store is already registered to grabfood": it's already linked. Move on — nothing to do.

**B5. Set channel tax.** Enter the **Grab tax percentage** for the store (e.g. `10` for 10%).
- ⚠️ Getting this wrong makes every order's tax and revenue wrong. If you don't know it, ask the client's
  finance contact. Do not guess.

**B6. Push the menu.** Press **Push menu**. Grab pulls the menu from Omni.
- ✅ Success: within a few minutes the status becomes **Menu synced** (Grab reports back automatically).
- ❌ **Failed** with a list of errors: the errors name the items at fault (e.g. missing photo, zero price).
  Fix those items in Omni's menu, then press **Push menu** again. Repeat until green.

**B7. Verify.** Press **Run checks**. All five must be green:
`Auth` · `Store found` · `Test order received` · `Menu valid` · `Tax & version set`.
- ❌ **Test order received** red = Grab can't reach Omni or the reply was wrong. **Escalate to devops** —
  this is not fixable from the portal.

**B8. Go live.** The button only unlocks when all checks are green. Press it.
- ✅ Final proof: place a **real test order** on the Grab consumer app from that outlet. It should appear
  in Omni's order list **and** on the store's POS within seconds. Then cancel/refund it per the client's
  policy.

---

### 3.2 GoFood — self-service *after* the Facilitator migration (§2.1)

> **Until §2.1 ships, GoFood onboarding still needs devops.** Do not hand this section to staff before
> then. Written here as the target state.

**One-time, company-level (devops, done once ever — not per client):**
Omni must be a registered **GoBiz Partner (Facilitator)**. Apply via the GoBiz Developer Portal
contact form; GoBiz assesses, then issues facilitator credentials. Devops stores them once in Omni.

**Time:** ~10 min per merchant.

#### Part A — On Gojek (client's account)

**A1. Confirm every outlet exists in GoBiz.**
Log in to **GoBiz** with the client's admin account. Check every branch the client wants connected
appears in their outlet list.
- ✅ Success: all outlets listed.
- ❌ Missing outlet: it must be registered in GoBiz **first**. An outlet that isn't in GoBiz cannot be
  linked, and won't appear in the pick-list in step B3.

**A2. Have the admin's phone ready.** The consent step sends an **OTP by SMS** to the account owner's
phone. Make sure the person holding that phone is available *now* — the code expires quickly.

#### Part B — In Omni

**B1.** Omni backoffice → **Aggregators → GoFood** → **Connect**. Choose **Indonesia / Production**.

**B2. Authorize.** Press **Authorize on GoBiz**. You're taken to Gojek's page:
1. Enter the **merchant admin's phone number**.
2. Gojek sends an **OTP** to that phone — type it in.
3. A **consent screen** lists what Omni will be allowed to access. Read it, press **Allow**.
- ✅ Success: back in Omni, badge reads **Account connected**.
- ❌ OTP didn't arrive: check the phone number is the account owner's. Request a new code. Do not retry
  more than a couple of times or the number may be temporarily blocked.
- ❌ "Code expired": just press **Authorize on GoBiz** again — the code is only valid ~2 minutes, so a
  slow OTP entry causes this. Retrying is safe.

**B3. Pick your outlets — no typing.** Omni now shows the **list of outlets on the client's GoBiz
account**, each with its **name and address** (Omni reads these from GoBiz automatically).
- Tick the outlet(s) to connect, and match each to the matching Omni store from the dropdown.
- 🔎 **Match by address, not by name.** Branch names are often near-identical ("Cabang 1", "Cabang 2");
  the address is what tells them apart. Matching the wrong outlet sends one store's orders to another
  store's kitchen.
- ✅ Success: each row shows **Linked**, and Omni fills the **GoFood outlet ID** by itself.
- ❌ Your outlet isn't in the list: it isn't registered in GoBiz (go back to A1), or the admin account
  you authorized with doesn't own it.

**B4. Register webhooks.** Press **Register / Re-sync webhooks**. This tells GoFood where to send
orders. Omni registers **7 events** in one press.
- ✅ Success: all 7 rows show green (order created, merchant accepted, driver on the way, driver arrived,
  cancelled, completed, menu mapping updated).
- ❌ Some rows red: press **Re-sync** once more — it repairs only the missing ones and won't duplicate the
  good ones. Still red after two tries → escalate.

**B5. Set tax + when the kitchen sees the order.**
- **Tax percentage** for GoFood.
- **Send to POS when:** choose per the client's preference — *Order created* (kitchen starts immediately)
  or *Driver arrived* (kitchen starts later, less waste if cancelled). **If unsure, choose Order created**
  — it's the safe default and matches most clients.

**B6. Push menu** → wait for **Menu synced**. Same fix-and-retry loop as Grab (B6 above).

**B7. Run checks** → **B8. Go live** → place a **real test order** on the GoFood app to confirm end-to-end.

---

### 3.3 ShopeeFood — guided, one value to copy

> ShopeeFood has **no merchant-consent flow available**. Access is granted by Shopee case-by-case, so
> credentials are set up once by Omni devops, and the operator does one copy-paste per store.

**One-time per merchant (devops):** Shopee issues the partner credentials (a **client/vendor ID** and a
**client secret**). Devops enters them into Omni once, encrypted. **Operators never see or handle these.**

**Time:** ~5 min per store.

#### Part A — On Shopee (client's account)

**A1. Confirm ShopeeFood API access is approved.** `[VERIFY]`
The client must have been approved by Shopee for POS/partner integration. If they haven't, **stop** —
no amount of clicking in Omni will work until Shopee approves. That's a Shopee commercial process.

**A2. Find the store's ShopeeFood store ID.** `[VERIFY: exact portal screen and label]`
In the Shopee merchant/partner portal, open the outlet and locate its **store identifier**.
- 🔎 **What you're looking for:** a short identifier belonging to that **one outlet** — not the account
  ID, not the shop name.
- ⚠️ **Do not guess and do not reuse another store's ID.** A wrong ID means that store's orders will be
  attached to the wrong store in Omni — wrong kitchen, wrong sales figures. If you can't find it with
  certainty, stop and ask.

#### Part B — In Omni

**B1.** Omni backoffice → **Aggregators → ShopeeFood**. If it says **Credentials missing**, stop and ask
devops to complete the one-time setup. You cannot proceed without it.

**B2.** Pick the store → **Link store** → paste the store ID from A2 → **Save**.
- Omni checks the format as you type. If it says the format looks wrong, **you probably copied the wrong
  value** — go back to A2 rather than forcing it.
- ✅ Success: badge reads **Linked**.

**B3.** Set the **ShopeeFood tax percentage**.

**B4. Push menu.** Press **Push menu**.
- ✅ Success: Shopee confirms back and status becomes **Menu synced**.
- ❌ Failed: the message names the problem items. Fix in Omni's menu, push again.

**B5. Run checks** → **B6. Go live** → place a **real test order** on the ShopeeFood app.

---

### 3.4 When something goes wrong — operator triage

| What you see | What it means | What to do |
|---|---|---|
| **Menu synced** never arrives (stuck >30 min) | Aggregator is still processing, or the callback didn't reach Omni | Wait 30 min, press **Push menu** once more. Still stuck → escalate |
| Menu failed, errors name items | Menu data problem in **Omni** | Fix those items in Omni's menu, push again |
| **Test order received** check is red | Aggregator can't reach Omni, or signature/reply mismatch | **Escalate to devops.** Not fixable from a portal |
| Orders arrive in Omni but not on the POS | POS delivery problem, unrelated to the aggregator | Escalate — check POS connectivity |
| Duplicate orders | Usually the aggregator retrying | Report it; do **not** cancel either copy yourself |
| Store shows **Syncing** for hours (Grab) | Grab activation still processing; Omni blocks retry for 24h | **Wait.** Do not press Activate again |
| Wrong prices on the aggregator app | Channel pricing or tax % wrong in Omni | Fix channel price/tax in Omni, push menu again |

**Escalate immediately (don't experiment) if:** any credential/secret needs changing, a pre-flight check
stays red after two tries, orders are landing on the wrong store, or money figures look wrong.

---

## 4. Before this tutorial ships — required verification pass

The API-level content above is confirmed from official documentation and Omni's source. **The portal
UI navigation is not** — layouts are private and change often. Assigning someone to do this once
converts every `[VERIFY]` into exact instructions:

For each of Grab Merchant Portal, GoBiz, and Shopee merchant portal, capture:
1. Screenshot of the **login screen** and the **landing page after login**.
2. The exact **menu path** to the integrations/API section (e.g. *Sidebar → Settings → Integrations*).
3. Screenshot of the **consent/authorize screen** and the **exact label** of the approve button.
4. For ShopeeFood: the exact screen and **field label** where the store ID appears, plus a **redacted
   example** of the value's shape (mask real digits).
5. Any wording differences between **English** and **Bahasa Indonesia** portal settings.

Then: **have one person who has never done the setup follow the guide end-to-end on a test merchant.**
Every place they hesitate is a place the guide needs another sentence. That dry run is what makes the
"a 12-year-old could follow it" claim actually true — not the writing.

---

## 5. Summary for decision-makers

- **GrabFood** is already self-service. Nothing to build; wrap it in the wizard.
- **GoFood** *can* be fully self-service — better than Grab, since outlets are auto-discovered — but only
  after migrating from Direct Integration to the **Facilitator (authorization-code)** model. Omni is
  already calling the right URL namespace with the right scopes, so this is a focused change, not a
  rewrite. **This is the single highest-value item.**
- **ShopeeFood** cannot be automated with available APIs. Reduce it to one guided copy-paste and accept it.
- Real elimination of devops toil comes from **pre-flight checks + idempotent one-click actions**, not
  from UI polish. Build those first.

---

**Sources:**
- [Facilitator Model — GoBiz Developer Portal](https://developer.gobiz.com/docs/docs/food-integration/facilitator/)
- [Steps on Linking Outlets — GoBiz Developer Portal](https://developer.gobiz.com/docs/docs/food-integration/steps-on-linking-outlets/index.html)
- [Authorization Code — GoBiz Developer Portal](https://developer.gobiz.com/docs/api/auth/facilitator/authorization-code/index.html)
- [Food Integration — GoBiz Developer Portal](https://developer.gobiz.com/docs/api/food-integration/)
- [GoBiz API Reference](https://developer.gobiz.com/docs/api/intro/)
- [Shopee API Essentials — Rollout](https://rollout.com/integration-guides/shopee/api-essentials)
- [Shopee Partner app listing](https://apps.apple.com/id/app/shopee-partner-grow-business/id1522810441)
