# Aggregator Integration — Deployment & Operations

What must be true in the environment before GoFood / GrabFood / ShopeeFood can
deliver a single order.

---

## 1. Required environment variables

| Variable | Required | Why |
|---|---|---|
| `AGGREGATOR_PUBLIC_BASE_URL` | **Yes** | HTTPS origin aggregators call back into. Without it webhooks and OAuth redirects cannot be delivered; pre-flight fails closed. |
| `AGGREGATOR_ENCRYPTION_KEY` | **Yes in production** | Fernet key encrypting client secrets and OAuth tokens at rest. |
| `REDIS_URL` | **Yes** | Celery broker, channel layer, cache lock, rate limiting. |
| `CELERY_BROKER_URL` | No | Defaults to `REDIS_URL`. |
| `CELERY_RESULT_BACKEND` | No | Defaults to `REDIS_URL`. |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_CLAIM_EMAIL` | Recommended | Web push for new orders. Without these the order board still works, but nothing reaches a closed tab. |

Generate the encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Rotating `SECRET_KEY` without an explicit `AGGREGATOR_ENCRYPTION_KEY` makes every
> stored aggregator credential permanently unreadable**, because the fallback key is
> derived from `SECRET_KEY`. Set the explicit key before going to production.
> Pre-flight surfaces this as a failing "Keamanan kredensial" check.

Per-aggregator endpoints can each be overridden by environment variable
(`GOFOOD_API_BASE_URL`, `GRABFOOD_AUTH_URL`, …) so a vendor change never needs a
code deploy. See `apps/pos_aggregator/config_templates.py`.

---

## 2. Processes to run

Three, not one:

```bash
# 1. Web (ASGI — Channels needs ASGI, not WSGI, for the order board socket)
gunicorn naveda_integra.asgi:application -k uvicorn.workers.UvicornWorker

# 2. Celery worker — webhook processing, menu pushes, Sales posting
celery -A naveda_integra worker -l info

# 3. Celery beat — token refresh, dead-letter retry, stale-sync reconciliation
celery -A naveda_integra beat -l info
```

**Without the worker, orders are received and stored but never turned into orders or
sales.** They accumulate as `WebhookEvent` rows with status `RECEIVED` and are picked
up once a worker starts — nothing is lost, but nothing reaches the kitchen either.

**Without beat**, OAuth tokens eventually expire and orders silently stop arriving.
This is the failure mode that is hardest to diagnose after the fact.

Scheduled jobs:

| Task | Interval | Purpose |
|---|---|---|
| `refresh_expiring_tokens` | 15 min | Refresh OAuth tokens before expiry |
| `retry_failed_webhook_events` | 10 min | Replay events that failed transiently |
| `reconcile_stale_menu_syncs` | 30 min | Flip menu pushes that never reported back to FAILED |

---

## 3. Migration notes for this change

`pos_config` and `pos_catalog` migrations were **squashed and regenerated**, because
the EntitasBisnis binding changed:

| Model | Was | Now |
|---|---|---|
| `MerchantPOSConfig` | `EntitasBisnis` (lv1) | `EntitasBisnisLv2` |
| `StorePOSConfig` | `EntitasBisnisLv2` | `EntitasBisnisLv3` |
| `OutletPOSConfig` | `EntitasBisnisLv3` | **removed** — merged into `StorePOSConfig` |

> **This is not a forward migration.** An existing database still holds the old
> `pos_config`/`pos_catalog` tables and their `django_migrations` rows. On a database
> with POS data you care about, do **not** just run `migrate` — reconcile first.
>
> On a database whose POS tables are empty or disposable:
>
> ```bash
> python manage.py migrate pos_config zero --fake
> python manage.py migrate pos_catalog zero --fake
> python manage.py migrate
> ```
>
> Verify against a restored copy of production before running this anywhere real.

---

## 4. Webhook endpoints to give the aggregator

With `AGGREGATOR_PUBLIC_BASE_URL = https://app.example.com`:

```
Orders + status   POST  /pos/aggregator/webhook/<AGGREGATOR>/<credential_id>/
Grab activation   POST  /pos/aggregator/webhook/grab/<credential_id>/activation/
Grab menu pull    GET   /pos/aggregator/webhook/grab/<credential_id>/menu/<store_link_id>/
OAuth return      GET   /pos/aggregator/oauth/callback/
```

All are signature-authenticated and CSRF-exempt; the signature *is* the
authentication. An unsigned or wrongly-signed request is rejected with 401 and no
processing occurs.

Acknowledgement codes differ per aggregator and are enforced by the adapter
(`ack_status_code`) — GrabFood requires **204**, ShopeeFood expects its own JSON
envelope. Returning the wrong one causes infinite retries.

---

## 5. Security posture

- Client secrets, webhook secrets and OAuth tokens are **encrypted at rest** (Fernet)
  and never rendered back to a user — only masked, with a rotate action.
- The `Authorization` header is explicitly **excluded** from stored webhook headers.
- Signature comparison uses `hmac.compare_digest` (constant time).
- Every view scopes objects through `accessible_merchant_qs` / `accessible_store_qs`,
  so a user cannot reach another tenant's channel by guessing an id.
- The order-board WebSocket authorises the branch before accepting the connection.
- Entering or rotating secrets requires `pos_config_manage`; everyday operator steps
  require only `pos_aggregators_manage`.
- OAuth callbacks verify a `state` nonce with a 15-minute TTL.

---

## 6. Idempotency model

Four independent layers, because aggregators retry aggressively:

1. **Redis lock** per `(aggregator, external_order_id)` serialises concurrent deliveries.
2. **Event-id uniqueness** on `WebhookEvent` catches repeated deliveries.
3. **Existence check** on the order catches a retried create.
4. **Database unique constraint** on `(aggregator, external_order_id)` is the backstop
   that holds when Redis is degraded.

Plus the monotonic status guard: a transition is applied only when it moves the order
*forward*, so a late-arriving earlier callback cannot rewind an order. Cancellation is
the one permitted backward move.

---

## 7. Known gaps

- **Settlement / payout reconciliation is not implemented.** Commission, promo funding
  and net payout are not reconciled against aggregator settlement reports. This is the
  largest remaining gap and the place merchants most often lose money.
- **Outbound status is partial**: only GoFood accepts "food prepared" back. Grab and
  Shopee accept nothing.
- **Menu diffing** is not implemented — the whole catalog is republished each time.
- **Endpoint paths and signature schemes are marked `[VERIFY]` in the adapters.** They
  follow vendor documentation but have not been exercised against live credentials.
  Expect to correct specifics during the first sandbox run; they are isolated in the
  adapters and `config_templates.py` for exactly that reason.
