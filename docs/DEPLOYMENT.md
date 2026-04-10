# Deployment Guide — Naveda Integra

Production deployment steps for a Linux server (Ubuntu 22.04 / 24.04 LTS recommended).

---

## Server Requirements

- Ubuntu 22.04+ or Debian 12+
- Python 3.12+
- PostgreSQL 16+
- Nginx (reverse proxy)
- Gunicorn (WSGI server)
- Git

---

## 1. Server Preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx postgresql postgresql-contrib
```

---

## 2. Create a System User

```bash
sudo adduser --system --group --home /opt/naveda naveda
```

---

## 3. Clone the Repository

```bash
sudo -u naveda git clone https://github.com/ChristianJehoshaphatS/naveda_integra.git /opt/naveda/app
cd /opt/naveda/app
```

---

## 4. Virtual Environment and Dependencies

```bash
sudo -u naveda python3 -m venv /opt/naveda/venv
sudo -u naveda /opt/naveda/venv/bin/pip install --upgrade pip
sudo -u naveda /opt/naveda/venv/bin/pip install -r /opt/naveda/app/requirements.txt
sudo -u naveda /opt/naveda/venv/bin/pip install gunicorn
```

---

## 5. Set Up PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE naveda_integra;
CREATE USER naveda_user WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
ALTER ROLE naveda_user SET client_encoding TO 'utf8';
ALTER ROLE naveda_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE naveda_user SET timezone TO 'Asia/Jakarta';
GRANT ALL PRIVILEGES ON DATABASE naveda_integra TO naveda_user;
\c naveda_integra
GRANT ALL ON SCHEMA public TO naveda_user;
SQL
```

---

## 6. Configure Environment Variables

```bash
sudo -u naveda tee /opt/naveda/app/.env > /dev/null <<'EOF'
SECRET_KEY=GENERATE_A_REAL_SECRET_KEY_HERE
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,server-ip
DJANGO_SETTINGS_MODULE=naveda_integra.settings.production

DB_ENGINE=django.db.backends.postgresql
DB_NAME=naveda_integra
DB_USER=naveda_user
DB_PASSWORD=CHANGE_ME_STRONG_PASSWORD
DB_HOST=localhost
DB_PORT=5432
EOF
```

Generate a strong secret key:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 7. Run Migrations and Collect Static Files

```bash
cd /opt/naveda/app
sudo -u naveda /opt/naveda/venv/bin/python manage.py migrate --settings=naveda_integra.settings.production
sudo -u naveda /opt/naveda/venv/bin/python manage.py collectstatic --noinput --settings=naveda_integra.settings.production
sudo -u naveda /opt/naveda/venv/bin/python manage.py createsuperuser --settings=naveda_integra.settings.production
```

---

## 8. Create Gunicorn Systemd Service

```bash
sudo tee /etc/systemd/system/naveda.service > /dev/null <<'EOF'
[Unit]
Description=Naveda Integra Gunicorn Daemon
After=network.target postgresql.service

[Service]
User=naveda
Group=naveda
WorkingDirectory=/opt/naveda/app
EnvironmentFile=/opt/naveda/app/.env
ExecStart=/opt/naveda/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/opt/naveda/naveda.sock \
    --access-logfile /var/log/naveda/access.log \
    --error-logfile /var/log/naveda/error.log \
    naveda_integra.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo mkdir -p /var/log/naveda
sudo chown naveda:naveda /var/log/naveda
sudo systemctl daemon-reload
sudo systemctl enable naveda
sudo systemctl start naveda
sudo systemctl status naveda
```

---

## 9. Configure Nginx

```bash
sudo tee /etc/nginx/sites-available/naveda > /dev/null <<'EOF'
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /opt/naveda/app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/naveda/app/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://unix:/opt/naveda/naveda.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

```bash
sudo ln -sf /etc/nginx/sites-available/naveda /etc/nginx/sites-enabled/naveda
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 10. Enable HTTPS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Auto-renewal is configured automatically by certbot.

---

## 11. Firewall Setup

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## Updating the Application

```bash
cd /opt/naveda/app
sudo -u naveda git pull origin main
sudo -u naveda /opt/naveda/venv/bin/pip install -r requirements.txt
sudo -u naveda /opt/naveda/venv/bin/python manage.py migrate --settings=naveda_integra.settings.production
sudo -u naveda /opt/naveda/venv/bin/python manage.py collectstatic --noinput --settings=naveda_integra.settings.production
sudo systemctl restart naveda
```

---

## Checking Logs

```bash
# Gunicorn logs
sudo tail -f /var/log/naveda/error.log
sudo tail -f /var/log/naveda/access.log

# Nginx logs
sudo tail -f /var/log/nginx/error.log

# Systemd service status
sudo systemctl status naveda
sudo journalctl -u naveda -f
```

---

## Database Backup (Cron)

```bash
sudo tee /etc/cron.d/naveda-backup > /dev/null <<'EOF'
0 2 * * * naveda pg_dump -U naveda_user -h localhost -Fc naveda_integra > /opt/naveda/backups/naveda_$(date +\%Y\%m\%d).dump
EOF

sudo -u naveda mkdir -p /opt/naveda/backups
```
