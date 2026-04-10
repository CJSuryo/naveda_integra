# Installation Guide — Naveda Integra

Complete steps to clone, set up, and run the project on **Windows 11** (or any OS with Python 3.12+).

---

## Prerequisites

### 1. Python 3.12+

Download from <https://www.python.org/downloads/>. During installation, check **"Add Python to PATH"**.

```powershell
python --version
# Expected: Python 3.12.x or newer
```

### 2. Git

Download from <https://git-scm.com/download/win>. Install with default options.

```powershell
git --version
```

### 3. PostgreSQL 16+ (for production / staging)

See [`DATABASE.md`](DATABASE.md) for full PostgreSQL installation instructions.

> **Note:** For quick local development you can skip PostgreSQL entirely — the development settings default to SQLite.

---

## Step 1 — Clone the Repository

```powershell
git clone https://github.com/ChristianJehoshaphatS/naveda_integra.git
cd naveda_integra
```

---

## Step 2 — Create a Virtual Environment

```powershell
python -m venv venv
```

**Activate it:**

```powershell
# PowerShell
.\venv\Scripts\Activate.ps1

# OR Command Prompt
venv\Scripts\activate.bat
```

> If PowerShell blocks script execution, run once:
>
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

You should see `(venv)` at the start of your prompt.

---

## Step 3 — Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs Django 6.x, django-extensions, django-debug-toolbar, ipython, psycopg2-binary, dj-database-url, gunicorn, and whitenoise.

---

## Step 4 — Configure Environment Variables

Copy the example file and edit it:

```powershell
copy .env.example .env
```

For **local development with SQLite** (zero-setup), the defaults work as-is — no changes needed.

For **PostgreSQL**, edit `.env`:

```dotenv
DJANGO_SETTINGS_MODULE=naveda_integra.settings.development
DB_ENGINE=django.db.backends.postgresql
DB_NAME=naveda_integra
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
```

---

## Step 5 — Run Database Migrations

```powershell
python manage.py migrate
```

---

## Step 6 — Create a Superuser

```powershell
python manage.py createsuperuser
```

Enter your **email**, **name**, and **password** when prompted.

---

## Step 7 — Run the Development Server

```powershell
python manage.py runserver
```

Open your browser:

| URL | Description |
|-----|-------------|
| <http://127.0.0.1:8000/> | Home page |
| <http://127.0.0.1:8000/admin/> | Django admin |

---

## Quick Copy-Paste — Full Setup Sequence

```powershell
git clone https://github.com/ChristianJehoshaphatS/naveda_integra.git
cd naveda_integra
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Optional Commands

### Run Tests

```powershell
python manage.py test
```

All 89 tests should pass.

### Open Enhanced Shell (IPython)

```powershell
python manage.py shell_plus
```

### Collect Static Files (for production)

```powershell
python manage.py collectstatic --noinput
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python` not found | Reinstall Python with "Add to PATH" checked |
| `Activate.ps1` blocked | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `psycopg2` build fails | `pip install psycopg2-binary` (pre-built wheel) |
| Port 8000 in use | `python manage.py runserver 8080` |
| `ModuleNotFoundError` | Activate your virtual environment first |
| PostgreSQL connection refused | Make sure the PostgreSQL service is running |
