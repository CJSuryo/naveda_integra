# Deployment Guide — Naveda Integra

Free, permanent cloud hosting using **Render.com** (web service) + **Neon.tech** (serverless PostgreSQL).

> **Why this stack?** Render provides seamless Git-push deploys with a generous free tier.
> Neon gives you a permanent, serverless PostgreSQL database (no 30-day expiry).
> Splitting the stack avoids Render's free-DB time limit while keeping everything free.

---

## Architecture Overview

```
┌────────────┐     HTTPS      ┌──────────────────┐    SSL/TCP     ┌──────────────┐
│  Browser   │ ──────────────▶ │  Render.com      │ ─────────────▶ │  Neon.tech   │
│            │                 │  (Gunicorn +     │                │  (Serverless │
│            │ ◀────────────── │   WhiteNoise)    │ ◀───────────── │   Postgres)  │
└────────────┘   static files  └──────────────────┘   query results └──────────────┘
```

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| GitHub account | Source code hosting + CI/CD trigger |
| [Neon.tech](https://neon.tech) account | Free serverless PostgreSQL (sign in with GitHub) |
| [Render.com](https://render.com) account | Free web service + cron jobs (sign in with GitHub) |
| Python 3.12+ | Local development |

---

## Phase 1 — Prepare Your Django Project (Local)

### 1.1 Install production dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` already includes:

```
psycopg2-binary>=2.9,<3.0    # PostgreSQL adapter
dj-database-url>=2.3,<3.0    # parse DATABASE_URL into Django DATABASES dict
gunicorn>=23.0,<24.0          # production WSGI server
whitenoise>=6.8,<7.0          # serve static files without Nginx
```

### 1.2 Verify settings are ready

The project settings already support `DATABASE_URL`:

- `base.py` — uses `dj_database_url.config()` with fallback to individual `DB_*` vars
- `production.py` — enforces `SSL`, strips `debug_toolbar`, enables HSTS + secure cookies
- `development.py` — defaults to SQLite when no database env vars are set

### 1.3 Push your code to GitHub

```bash
git add -A
git commit -m "Prepare for Render + Neon deployment"
git push origin main
```

---

## Phase 2 — Create Your Free Neon Database

### 2.1 Create the project

1. Go to [neon.tech](https://neon.tech) → **Sign in with GitHub**.
2. Click **Create Project**.
3. Configure:
   - **Project name:** `naveda-integra`
   - **Region:** `ap-southeast-1` (Singapore) — **must match your Render region**
   - **Postgres version:** 16 (recommended)
4. Click **Create Project**.

### 2.2 Copy your connection string

After creation, you'll see a **Connection Details** panel. Copy the connection string:

```
postgresql://neondb_owner:AbCdEf123456@ep-cool-cloud-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

> ⚠️ **Treat this URL like a password.** Never commit it to Git.

### 2.3 Recommended Neon settings

| Setting | Value | Reason |
|---------|-------|--------|
| Autoscaling | 0.25–1 CU | Stays within free tier |
| Auto-suspend | 5 minutes | Saves compute when idle |
| Branch | `main` | Use Neon branches for staging later |

### 2.4 Edge case: Neon cold starts

Neon's free tier suspends after 5 minutes of inactivity. The first request after a cold start
takes 1-3 seconds. Mitigations:

- **`conn_max_age=600`** in our settings keeps connections alive within Gunicorn workers.
- **`conn_health_checks=True`** automatically discards broken connections.
- For production apps with paying users, upgrade to Neon's paid tier to disable auto-suspend.

---

## Phase 3 — Deploy on Render

### Option A: One-Click Blueprint (recommended)

The repo includes a `render.yaml` Blueprint. To use it:

1. Go to [dashboard.render.com/blueprints](https://dashboard.render.com/blueprints).
2. Click **New Blueprint Instance**.
3. Select your `naveda_integra` GitHub repo.
4. Render will auto-detect `render.yaml` and create:
   - **Web Service** (`naveda-integra`)
   - **Cron Job** (`naveda-nightly-backup`)
5. Set the required environment variables when prompted (see Phase 3B step 5).
6. Click **Apply**.

### Option B: Manual Setup

#### 3B.1 Create a Web Service

1. Go to [render.com](https://render.com) → **New +** → **Web Service**.
2. Connect your GitHub repo (`ChristianJehoshaphatS/naveda_integra`).

#### 3B.2 Configure the service

| Field | Value |
|-------|-------|
| **Name** | `naveda-integra` |
| **Region** | Singapore (match Neon region!) |
| **Branch** | `main` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput` |
| **Start Command** | `gunicorn naveda_integra.wsgi:application` |
| **Instance Type** | Free |

#### 3B.3 Set Environment Variables

| Key | Value | Notes |
|-----|-------|-------|
| `DATABASE_URL` | `postgresql://...@...neon.tech/...?sslmode=require` | Paste your Neon URL |
| `SECRET_KEY` | *(generate one — see below)* | Production secret |
| `DJANGO_SETTINGS_MODULE` | `naveda_integra.settings.production` | Required |
| `PYTHON_VERSION` | `3.12` | Match your local version |
| `ALLOWED_HOSTS` | `naveda-integra.onrender.com` | Your Render domain |
| `CSRF_TRUSTED_ORIGINS` | `https://naveda-integra.onrender.com` | Required for POST forms |
| `WEB_CONCURRENCY` | `4` | Optimizes free-tier memory |
| `LOG_LEVEL` | `WARNING` | Reduce noise (use `INFO` for debugging) |

**Generate a SECRET_KEY:**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

#### 3B.4 Create a Superuser

After the first deploy completes, open the **Shell** tab in Render's dashboard:

```bash
python manage.py createsuperuser
```

#### 3B.5 Set up the Nightly Backup Cron Job

1. In Render → **New +** → **Cron Job**.
2. Connect the same GitHub repo.
3. Configure:

| Field | Value |
|-------|-------|
| **Name** | `naveda-nightly-backup` |
| **Schedule** | `0 18 * * *` (18:00 UTC = 01:00 WIB) |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python manage.py backup_db --keep 7` |
| **Region** | Singapore |

4. Add the same `DATABASE_URL`, `SECRET_KEY`, and `DJANGO_SETTINGS_MODULE` env vars.

> **Note:** On Render's free tier, cron job output goes to the Render log stream.
> The backup is stored at `/tmp/backups/` on the ephemeral container.
> For durable storage, upgrade to a paid tier or pipe `pg_dump` to an S3 bucket.

---

## Phase 4 — Automated Logging

### How it works

- **Production:** All logs go to `stdout` via Python's `logging` module → Render captures them automatically in its **Log Stream**.
- **Log format:** `{timestamp} {level} {logger} {module}:{line} {message}`
- **Default level:** `WARNING` (set `LOG_LEVEL=INFO` for more detail).

### Viewing logs on Render

1. Go to your **Web Service** → **Logs** tab.
2. Logs are searchable and filterable in real time.
3. For persistent log storage, connect Render's Log Streams to:
   - [Datadog](https://render.com/docs/log-streams#datadog)
   - [Papertrail](https://render.com/docs/log-streams#papertrail)
   - [Logtail / Better Stack](https://render.com/docs/log-streams#logtail)

### Custom application logging (for your views/models)

```python
import logging
logger = logging.getLogger('apps.jurnal')

logger.info('Journal entry %s created', header.id)
logger.warning('Unbalanced entry detected: debit=%s kredit=%s', total_debit, total_kredit)
```

---

## Phase 5 — Automated Nightly Backup (1 AM WIB)

### Backup command

```bash
# Run manually (for testing):
python manage.py backup_db

# Custom output directory + retention:
python manage.py backup_db --output-dir /tmp/backups --keep 14
```

### What it does

1. Calls `pg_dump` in custom format (`-Fc`) for compressed, restorable backups.
2. Automatically detects Neon SSL (`sslmode=require`).
3. Prunes backups older than `--keep` days (default: 7).
4. Logs all operations to the `apps.jurnal` logger.

### Restoring from backup

```bash
# Download the .dump file from your backup location, then:
pg_restore -h <neon-host> -U <neon-user> -d <neon-db> --clean --if-exists naveda_integra_20260410_010000.dump
```

### Edge case: Render cron on free tier

Render's free cron runs on an ephemeral container — files are lost after the job finishes.
**Durable backup options:**

| Approach | Cost | Difficulty |
|----------|------|-----------|
| Neon built-in point-in-time recovery | Free (7 days on free tier) | None — automatic |
| Pipe `pg_dump` to S3/R2 via `awscli` | ~$0.02/GB/month | Low |
| Neon branch snapshots | Free | `neonctl branch create --name backup-YYYYMMDD` |
| Manual export via Neon dashboard | Free | Manual click |

> **Recommendation:** Rely on Neon's built-in PITR for day-to-day recovery. Use the `backup_db`
> cron as a secondary "belt and suspenders" backup piped to S3 for disaster recovery.

---

## Edge Cases & Troubleshooting

### Neon connection errors after cold start

**Symptom:** `connection to server ... failed: server closed the connection unexpectedly`

**Fix:** Already handled by `conn_health_checks=True` in settings. Django will retry with a fresh connection automatically.

### Render free tier spin-down

Render free web services sleep after 15 minutes of inactivity. First request after wake-up takes ~30 seconds.

**Mitigations:**
- Use a free uptime monitor (e.g., UptimeRobot with 5-minute interval) to keep it warm.
- Or accept the cold-start delay for hobby projects.

### Static files return 404

**Fix:** Make sure `collectstatic` runs in the build command. WhiteNoise serves them directly from the Gunicorn process.

```bash
python manage.py collectstatic --noinput
```

### `DisallowedHost` error

**Fix:** Add your Render domain to `ALLOWED_HOSTS`:

```
ALLOWED_HOSTS=naveda-integra.onrender.com
```

### CSRF verification failed on form POST

**Fix:** Add your full origin to `CSRF_TRUSTED_ORIGINS`:

```
CSRF_TRUSTED_ORIGINS=https://naveda-integra.onrender.com
```

### Migrations fail on deploy

**Possible causes:**
1. **Schema conflict** — run `python manage.py showmigrations` in Render Shell.
2. **Neon suspended** — the first connection attempt may time out; redeploy.
3. **Missing DATABASE_URL** — check Render env vars.

### Database connection pool exhaustion

**Symptom:** `too many connections for role` (Neon free tier allows ~100 connections).

**Fix:** Our settings use `conn_max_age=600` (connection pooling). If still an issue:
- Reduce `WEB_CONCURRENCY` from 4 to 2.
- Enable Neon's built-in connection pooler (PgBouncer) in the Neon dashboard.

---

## Custom Domain (Optional)

1. In Render → your web service → **Settings** → **Custom Domains**.
2. Add your domain (e.g., `app.naveda.id`).
3. Follow Render's DNS instructions (CNAME to `naveda-integra.onrender.com`).
4. Update env vars:

```
ALLOWED_HOSTS=app.naveda.id,naveda-integra.onrender.com
CSRF_TRUSTED_ORIGINS=https://app.naveda.id,https://naveda-integra.onrender.com
```

Render provisions a free Let's Encrypt SSL certificate automatically.

---

## Updating the Application

Simply push to `main` — Render auto-deploys:

```bash
git add -A
git commit -m "feat: new feature"
git push origin main
```

Render will:
1. Pull the latest code.
2. Run `pip install -r requirements.txt`.
3. Run `python manage.py collectstatic --noinput`.
4. Run `python manage.py migrate --noinput`.
5. Restart Gunicorn with zero-downtime deploy.

---

## Security Best Practices Checklist

- [x] `SECRET_KEY` generated per environment, never committed to Git
- [x] `DEBUG=False` in production
- [x] HTTPS enforced via `SECURE_SSL_REDIRECT`
- [x] HSTS enabled (1-year max-age, preload)
- [x] Secure cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`)
- [x] `debug_toolbar` removed in production
- [x] `DATABASE_URL` stored as Render env var, never in code
- [x] WhiteNoise serves compressed, hashed static files
- [x] Connection pooling enabled (`conn_max_age=600`)
- [x] Neon SSL enforced (`sslmode=require`)
- [ ] Set up UptimeRobot for availability monitoring
- [ ] Configure Render Log Streams for persistent log storage
- [ ] Enable Neon connection pooler (PgBouncer) if >50 concurrent users
