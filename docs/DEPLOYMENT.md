# Deployment on AWS EC2

Target: one existing EC2 instance (Ubuntu 22.04/24.04 LTS assumed), nginx, gunicorn, SQLite.

```
Internet → nginx :443 (TLS) → gunicorn 127.0.0.1:8000 → Flask → SQLite (/var/lib/vrioscu)
```

## 0. AWS prerequisites

- **Security group inbound:** 443/tcp and 80/tcp from `0.0.0.0/0` (80 only redirects and serves ACME).
  SSH 22/tcp from your admin IP only, or use SSM Session Manager and close 22 entirely. Nothing else.
  Port 8000 must **not** be open.
- **Elastic IP** attached; DNS `A` records for `vrioscu.com` and `www.vrioscu.com` point to it.
- **EBS:** encryption enabled; consider a Data Lifecycle Manager snapshot policy as an extra layer.
- **IAM:** the instance needs no credentials to run the site. Only add a narrowly scoped role if you
  ship backups to S3 (see BACKUP_RESTORE.md). Never put AWS keys in `.env` or code.

## 1. System packages and user

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv nginx certbot python3-certbot-nginx sqlite3 unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

sudo useradd --system --home /opt/vrioscu --shell /usr/sbin/nologin vrioscu
sudo install -d -o vrioscu -g vrioscu -m 0755 /opt/vrioscu
sudo install -d -o vrioscu -g vrioscu -m 0700 /var/lib/vrioscu /var/backups/vrioscu
sudo install -d -o root -g vrioscu -m 0750 /etc/vrioscu
```

## 2. Code and virtualenv

```bash
sudo -u vrioscu git clone <your-repo-url> /opt/vrioscu/app     # or upload a release archive
sudo -u vrioscu python3 -m venv /opt/vrioscu/venv
sudo -u vrioscu /opt/vrioscu/venv/bin/pip install --upgrade pip
sudo -u vrioscu /opt/vrioscu/venv/bin/pip install -r /opt/vrioscu/app/requirements.txt
```

Add the font files to `app/static/fonts/` (see the README there).

## 3. Configuration

```bash
sudo cp /opt/vrioscu/app/.env.example /etc/vrioscu/vrioscu.env
sudo chown root:vrioscu /etc/vrioscu/vrioscu.env && sudo chmod 0640 /etc/vrioscu/vrioscu.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as SECRET_KEY
sudo nano /etc/vrioscu/vrioscu.env
```

Minimum production values:

```
APP_ENV=production
SECRET_KEY=<generated>
BASE_URL=https://vrioscu.com
DATABASE_PATH=/var/lib/vrioscu/vrioscu.db
TRUSTED_PROXY_COUNT=1
DOWNLOAD_ALLOWED_HOSTS=<host serving the installer>
WINDOWS_COMPATIBILITY=<confirmed platforms>
INSTALLER_SIGNED=false
```

The app refuses to start in production with a weak secret, a non-HTTPS `BASE_URL`
or a database path inside `app/static`.

## 4. Database and first administrator

```bash
cd /opt/vrioscu/app
sudo -u vrioscu bash -c 'set -a; . /etc/vrioscu/vrioscu.env; set +a; /opt/vrioscu/venv/bin/flask --app wsgi init-db'
sudo -u vrioscu bash -c 'set -a; . /etc/vrioscu/vrioscu.env; set +a; /opt/vrioscu/venv/bin/flask --app wsgi create-admin'
ls -l /var/lib/vrioscu     # expect -rw------- vrioscu vrioscu vrioscu.db
```

## 5. systemd

```bash
sudo cp deploy/systemd/vrioscu.service deploy/systemd/vrioscu-backup.service deploy/systemd/vrioscu-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vrioscu vrioscu-backup.timer
systemctl status vrioscu
curl -s http://127.0.0.1:8000/api/v1/health      # {"status":"ok"}
```

`vrioscu.service` runs gunicorn bound to loopback with systemd sandboxing
(`ProtectSystem=strict`, `NoNewPrivileges`, write access only to `/var/lib/vrioscu`, `UMask=0077`).
Check its exposure score with `systemd-analyze security vrioscu`. If the service fails to start
after a dependency upgrade, check `journalctl -u vrioscu`; a library needing writable+executable
memory would require removing `MemoryDenyWriteExecute=true` (none of the current dependencies do).

## 6. nginx and TLS

```bash
sudo cp deploy/nginx/vrioscu-proxy.conf /etc/nginx/snippets/
sudo install -d /var/www/certbot
# First obtain certificates using a temporary HTTP-only server block, or:
sudo certbot certonly --nginx -d vrioscu.com -d www.vrioscu.com
sudo cp deploy/nginx/vrioscu.conf /etc/nginx/sites-available/vrioscu.conf
sudo ln -s /etc/nginx/sites-available/vrioscu.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl list-timers | grep certbot     # auto-renewal
```

nginx serves `/static/`, denies dotfiles and database/backup/source extensions,
caps request bodies at 64 KB, overwrites `X-Forwarded-For` and rate-limits auth pages.

## 7. Verify

```bash
curl -sI https://vrioscu.com | grep -Ei 'strict-transport|content-security|x-frame|x-content-type|referrer'
curl -s  https://vrioscu.com/api/v1/health
curl -sI https://vrioscu.com/static/../instance/vrioscu.db     # 404
curl -sI http://vrioscu.com                                      # 301 to https
```

Then walk through `PRODUCTION_READINESS.md`.

## 8. Updating

```bash
sudo systemctl start vrioscu-backup.service          # fresh backup first
cd /opt/vrioscu/app && sudo -u vrioscu git pull       # or unpack the new release
sudo -u vrioscu /opt/vrioscu/venv/bin/pip install -r requirements.txt
sudo -u vrioscu bash -c 'set -a; . /etc/vrioscu/vrioscu.env; set +a; /opt/vrioscu/venv/bin/python -m unittest discover -s tests -t .'
sudo systemctl restart vrioscu                        # ExecStartPre applies migrations
```

Rollback: restore the previous code, and if a migration ran, restore the pre-update
backup (`BACKUP_RESTORE.md`).

## 9. Logs

```bash
journalctl -u vrioscu -f          # structured JSON, one line per event/request
journalctl -u vrioscu -o cat | grep '"level": "ERROR"'
```

Set journald retention (`/etc/systemd/journald.conf`, e.g. `MaxRetentionSec=30day`).
Logs never contain passwords, session tokens, CSRF tokens or secrets.
