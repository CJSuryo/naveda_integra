# Rate Limiting — Design

**Date:** 2026-06-22
**Status:** Approved, pending implementation plan

## Goal

Prevent credential brute-force, email/account spam, heavy-process DoS, and
bot crawling against the Naveda Integra Django app. Defense in depth across
application and (future) infrastructure layers.

## Context

- Django 6, plain function-based views, **no DRF**.
- Redis available via `REDIS_URL` (already used by Channels).
- No `CACHES` configured today → default per-process LocMemCache, which does
  **not** share counters across `WEB_CONCURRENCY=4` gunicorn workers.
- Deployed on Render (free plan), with **Cloudflare in front** (chosen topology).
- Settings split: `naveda_integra/settings/{base,development,production,test}.py`.

## Decisions

| Decision | Choice |
|---|---|
| Scope | Full: auth + email + POS + heavy exports + push + global per-IP ceiling |
| Libraries | `django-ratelimit` (per-view) + `django-axes` (login lockout/audit) |
| Backend store | Redis via `django-redis` (reuse `REDIS_URL`) |
| Proxy/IP source | Cloudflare → Render; trust `CF-Connecting-IP` |
| 429 UX | Smart per-endpoint: HTML page for browser, JSON for AJAX/api |

## Architecture — 5 isolated components

### 1. Redis cache backend
`naveda_integra/settings/base.py`: add `CACHES` using `django-redis` pointing at
`REDIS_URL`. Shared across all gunicorn workers. Dev/test fall back to LocMem
when no Redis is present.

### 2. Real-IP extraction — `naveda_integra/ratelimit_utils.py`
Single function `get_client_ip(request)` — the one source of truth, used by both
the ratelimit `key` callables and the global throttle middleware.

- Primary: `CF-Connecting-IP` header. Cloudflare overwrites this on every request,
  so it is not client-spoofable **provided the Render origin is only reachable
  through Cloudflare** (see Hardening).
- Fallback (CF header absent): rightmost hop of `X-Forwarded-For`; log a warning
  (indicates possible Cloudflare bypass / direct origin hit).
- Missing/garbage: bucket as `unknown`, still rate-limited.

### 3. django-axes — login brute-force lockout
Hooks `authenticate()`. Lockout keyed on `username + IP` after N failed attempts
within a window, with a cooloff. Audit log persisted in DB (Redis-independent).
Admin/CLI unlock via `python manage.py axes_reset`.

### 4. django-ratelimit — per-view decorators
Applied to register, password-change-request, heavy exports, POS api, push, and a
coarse layer on login (belt + suspenders over axes). `block=True` raises
`Ratelimited`, caught by the smart 429 handler. Rates read from a settings dict.

### 5. Global per-IP ceiling — `naveda_integra/middleware/throttle.py`
Catch-all Redis `INCR` + 60s TTL per IP. Blocks crawlers hammering many
endpoints. Exempts staff/superusers and static/health paths.

### Smart 429 handler
One `ratelimited` handler shared by decorators and middleware:
- AJAX/api → `JsonResponse({"error":"rate_limited","retry_after":N}, status=429)`.
  Detect via `/api/` in path OR `X-Requested-With: XMLHttpRequest` OR
  `Accept: application/json`.
- Browser → render `templates/429.html` (styled, **external CSS only** per the
  project no-inline-styles rule), status 429, with `Retry-After` header.

## Rate values & keys (starting points, tunable via `RATELIMIT_RATES` in settings)

| Surface | Limit | Key | Mechanism | Block |
|---|---|---|---|---|
| Login (lockout) | 5 fails / 15 min | username + IP | django-axes | cooloff lockout |
| Login (coarse) | 20 POST / 5 min | IP | ratelimit | 429 |
| Register | 5 / hour | IP | ratelimit | 429 |
| Password-change-request | 3 / hour per IP **and** 3 / hour per target email | IP; email | ratelimit (2 decorators) | 429 |
| Excel/PDF export (`export/`, `export/pdf/`) | 10 / min | user | ratelimit | 429 |
| POS api (`/api/orders/*`) | 120 / min | user | ratelimit | 429 (JSON) |
| Push subscribe | 10 / min | user | ratelimit | 429 (JSON) |
| Global ceiling | 300 req / min | IP | middleware | 429 |

Notes:
- Authed surfaces key on `user` (not IP) so shared office NAT does not collide;
  fall back to IP when anonymous.
- Staff/superuser exempt from global ceiling and POS limits (still subject to
  login lockout).
- All numbers live in a settings dict — tune without code changes.

Affected export endpoints (non-exhaustive, by `export/` URL scan): `aset_lainnya`,
`aset_tetap`, `ekuitas`, `entitas_bisnis`, and others — apply via shared decorator.

## Request flow

```
Cloudflare → Render → gunicorn worker
  → SecurityMiddleware
  → GlobalThrottleMiddleware   (INCR ip:{cf-ip}:min, TTL 60s; exempt staff/static/health)
  → Session / Common / CSRF / Auth middleware
  → AxesMiddleware             (login POST lockout check)
  → view (@ratelimit decorators)
  → Ratelimited? → smart 429 handler
```

## Error handling / failure modes

- **Redis down** → throttle middleware and ratelimit cache **fail open** (allow,
  log warning). Availability prioritized over strict limiting. Axes uses DB → still
  enforces login lockout. Documented tradeoff.
- **Dev/test** → no Redis required (LocMem); axes toggleable via setting; global
  middleware disabled in test settings; low deterministic limits in `test.py`.
- **Cloudflare bypass** (direct origin hit) → `CF-Connecting-IP` absent → XFF
  rightmost fallback + warning log.

## Hardening (documented, not coded in this work)

- Restrict Render origin to Cloudflare IP ranges so `CF-Connecting-IP` cannot be
  bypassed. Infra task.
- Optional: enable Cloudflare WAF / rate rules at the edge for a third layer.

## Edge cases

- Missing/garbage IP header → single `unknown` bucket, still limited.
- Legit bulk-export user hitting 10/min → 429 with `Retry-After`; rate tunable.
- Superuser locked out by axes → `python manage.py axes_reset`.

## Testing

- Unit: `get_client_ip` — CF header, XFF fallback, spoofed XFF, missing header.
- Unit: global middleware — under/over limit, staff exempt, Redis-down fail-open
  (mocked).
- Integration: login lockout after 5 fails; register 6th blocked; export 11th
  blocked; 429 JSON vs HTML branch selection.
- `test.py` overrides limits low for determinism; axes/middleware controllable.

## Out of scope

- Cloudflare WAF rule configuration (infra, future).
- Origin IP allowlisting (infra, future).
- Per-EB or per-tenant custom limits beyond user/IP keys.
