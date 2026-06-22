# Rate Limiting — Operations & Hardening

## Tuning limits
All limits live in `RATELIMIT_RATES` in `naveda_integra/settings/base.py`.
Change values there; no code changes needed. Format is django-ratelimit
"count/period" (e.g. `5/h`, `120/m`); the global ceiling is an int (req/min).

## Components
- **django-axes** — login lockout (5 fails / 15 min per username+IP). Unlock a
  user manually: `python manage.py axes_reset` (all) or
  `python manage.py axes_reset_username <name>`.
- **django-ratelimit** — per-view decorators (login coarse, register,
  password-change-request, exports, POS api, push).
- **GlobalThrottleMiddleware** — 300 req/min/IP catch-all. Toggle with env
  `GLOBAL_THROTTLE_ENABLE`.

## Client IP trust (IMPORTANT)
Real client IP is read from `CF-Connecting-IP` (Cloudflare). This is only
trustworthy if the Render origin is reachable **exclusively** through
Cloudflare. Hardening: restrict the Render service to Cloudflare's published
IP ranges (https://www.cloudflare.com/ips/). Without this, an attacker hitting
the origin directly and spoofing `CF-Connecting-IP` could evade IP-based limits.

## Redis failure behavior
If Redis is unavailable, ratelimit + global throttle **fail open** (requests
allowed, warnings logged). Axes uses the database, so login lockout still
enforces during a Redis outage.

## Future infra layer
Enable Cloudflare WAF / rate-limiting rules at the edge for a third defense
layer in front of the application.
