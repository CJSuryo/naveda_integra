# Database Guide — PostgreSQL Setup

This project uses **PostgreSQL** for production-ready, scalable data storage. SQLite is available as a zero-setup fallback for quick local development only.

## Why PostgreSQL over SQLite?

| Feature | SQLite | PostgreSQL |
|---------|--------|-----------|
| Concurrent writes | ❌ File-level lock | ✅ Row-level locking |
| Scalability | Single-user / small apps | Enterprise-grade |
| Full-text search | Basic | ✅ Built-in `tsvector` |
| JSON support | Limited | ✅ Native `jsonb` |
| Replication | ❌ | ✅ Streaming / logical |
| Backup tooling | File copy only | ✅ `pg_dump`, `pg_basebackup` |
| Production deployment | Not recommended | ✅ Industry standard |

**Recommendation:** Always use PostgreSQL for staging and production environments.

---

## Install PostgreSQL on Windows 11

### Option A — Official Installer (recommended)

1. Download from <https://www.postgresql.org/download/windows/>.
2. Run the installer. Keep the defaults:
   - **Port:** `5432`
   - **Superuser:** `postgres`
   - Set a **password** you'll remember.
3. When prompted to launch **Stack Builder**, you can skip it.
4. Verify the installation:

```powershell
psql --version
# Expected: psql (PostgreSQL) 16.x
```

> If `psql` is not found, add PostgreSQL's `bin` directory to your PATH:
>
> ```powershell
> # Typical path — adjust version number as needed
> $env:Path += ";C:\Program Files\PostgreSQL\16\bin"
> ```

### Option B — Chocolatey

```powershell
choco install postgresql16
```

### Option C — Docker

```powershell
docker run --name naveda-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
```

---

## Install PostgreSQL on Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

---

## Install PostgreSQL on macOS

```bash
brew install postgresql@16
brew services start postgresql@16
```

---

## Create the Database and User

Connect to PostgreSQL as the `postgres` superuser:

```powershell
# Windows (PowerShell)
psql -U postgres
```

```bash
# Linux / macOS
sudo -u postgres psql
```

Run these SQL commands:

```sql
CREATE DATABASE naveda_integra;
CREATE USER naveda_user WITH PASSWORD 'your-secure-password';
ALTER ROLE naveda_user SET client_encoding TO 'utf8';
ALTER ROLE naveda_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE naveda_user SET timezone TO 'Asia/Jakarta';
GRANT ALL PRIVILEGES ON DATABASE naveda_integra TO naveda_user;

-- For PostgreSQL 15+ you also need:
\c naveda_integra
GRANT ALL ON SCHEMA public TO naveda_user;

\q
```

---

## Configure Django to Use PostgreSQL

Edit your `.env` file:

```dotenv
DB_ENGINE=django.db.backends.postgresql
DB_NAME=naveda_integra
DB_USER=naveda_user
DB_PASSWORD=your-secure-password
DB_HOST=localhost
DB_PORT=5432
```

Or, if using Docker:

```dotenv
DB_ENGINE=django.db.backends.postgresql
DB_NAME=naveda_integra
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

---

## Run Migrations

```powershell
python manage.py migrate
python manage.py createsuperuser
```

---

## Backup and Restore

### Create a Backup

```powershell
pg_dump -U naveda_user -h localhost -Fc naveda_integra > backup.dump
```

### Restore from Backup

```powershell
pg_restore -U naveda_user -h localhost -d naveda_integra --clean --if-exists backup.dump
```

---

## Common PostgreSQL Commands

```sql
-- List databases
\l

-- Connect to database
\c naveda_integra

-- List tables
\dt

-- Describe a table
\d entitas_bisnis_entitasbisnis

-- Show running queries
SELECT pid, query, state FROM pg_stat_activity WHERE datname = 'naveda_integra';

-- Quit
\q
```
