# Deployment Guide

Deploying Word Scramble to a DigitalOcean droplet (or any Ubuntu/Debian host)
behind nginx, served by gunicorn, over HTTPS.

Assumes a non-root user with sudo, and a domain pointed at the droplet.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git sqlite3
```

## 2. Get the code

```bash
sudo mkdir -p /srv/wordscramble
sudo chown "$USER" /srv/wordscramble
git clone <your-repo-url> /srv/wordscramble
cd /srv/wordscramble

./scripts/setup.sh --prod
```

## 3. Configure

The database goes **outside** the application directory, so pulling a new
version can never overwrite the scores:

```bash
sudo mkdir -p /var/lib/wordscramble/lists
sudo chown -R "$USER" /var/lib/wordscramble
```

Word lists uploaded through `/lists` are written to `LISTS_DIR`, so put that
outside the app directory too - otherwise a `git pull` can clobber the lists a
parent added. The service user needs write access to it; nothing else does.

Set `SESSION_COOKIE_SECURE=1` once HTTPS is in place (step 7) so the session
cookie is never sent over plain HTTP.

Create `.env`:

```bash
cat > /srv/wordscramble/.env <<EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DB_PATH=/var/lib/wordscramble/wordscramble.db
LISTS_DIR=/var/lib/wordscramble/lists
ACCESS_PIN=1234
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
EOF

chmod 600 /srv/wordscramble/.env
```

Three settings matter:

- **`FLASK_DEBUG` must be 0.** The Werkzeug debugger is an interactive Python
  console exposed to anyone who triggers an error — remote code execution on a
  public host. This is the single most important line in this file.
- **`ACCESS_PIN`** gates the whole app behind a shared PIN. The app has no user
  accounts by design; without a PIN, anyone who finds the URL can play, read
  the score history, and add or delete word lists through `/lists`. Pick
  something a child can type but isn't `0000`.
- **`SECRET_KEY`** signs the session cookie that remembers an unlocked browser.
  With a guessable key, the PIN can be bypassed by forging a cookie.

## 4. Enable WAL mode

SQLite's default rollback journal makes concurrent readers and writers block
each other, which shows up as `database is locked`. Write-ahead logging fixes
that. It is a persistent property of the database file, so this is a one-time
command:

```bash
cd /srv/wordscramble
.venv/bin/python -c "from app import create_app; create_app()"   # create the file
sqlite3 /var/lib/wordscramble/wordscramble.db "PRAGMA journal_mode=WAL;"
```

It should print `wal`. You'll now see `.db-wal` and `.db-shm` files alongside
the database — that's normal.

## 5. Run it under systemd

`/etc/systemd/system/wordscramble.service`:

```ini
[Unit]
Description=Word Scramble
After=network.target

[Service]
User=YOUR_USER
Group=www-data
WorkingDirectory=/srv/wordscramble
EnvironmentFile=/srv/wordscramble/.env
ExecStart=/srv/wordscramble/.venv/bin/gunicorn \
    --workers 1 --threads 4 \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    wsgi:app
Restart=always
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/var/lib/wordscramble

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wordscramble
sudo systemctl status wordscramble
```

**On `--workers 1 --threads 4`:** with SQLite, separate worker *processes*
contend for the write lock. One worker with threads removes that contention
entirely, and for a single-family app it's far more capacity than you need.
Don't raise the worker count without a reason.

Binding to `127.0.0.1` means gunicorn is unreachable from the internet — only
nginx can talk to it.

## 6. nginx

`/etc/nginx/sites-available/wordscramble`:

```nginx
server {
    listen 80;
    server_name words.example.com;

    location /static/ {
        alias /srv/wordscramble/static/;
        expires 30d;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/wordscramble /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

nginx serves `/static/` directly, so gunicorn never handles sound files or
images.

## 7. HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d words.example.com
```

Certbot edits the nginx config and installs a renewal timer. Worth doing even
for a family app: the PIN is submitted in a form, and over plain HTTP it travels
in cleartext.

## 8. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## Backups

The whole database is one file, which is the nicest thing about this stack.
Use SQLite's `.backup` rather than `cp` — it's safe while the app is running:

```bash
sudo tee /usr/local/bin/wordscramble-backup >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /var/backups/wordscramble
sqlite3 /var/lib/wordscramble/wordscramble.db \
    ".backup /var/backups/wordscramble/scores-$(date +%F).db"
find /var/backups/wordscramble -name 'scores-*.db' -mtime +30 -delete
EOF
sudo chmod +x /usr/local/bin/wordscramble-backup
```

Daily at 03:00, via `sudo crontab -e`:

```
0 3 * * * /usr/local/bin/wordscramble-backup
```

## Updating

```bash
cd /srv/wordscramble
git pull
.venv/bin/pip install -r requirements.txt --quiet
sudo systemctl restart wordscramble
```

Schema changes apply themselves on startup — `init_db()` runs from the app
factory. Take a backup first if the release touches the schema.

## Checking on it

```bash
sudo systemctl status wordscramble         # is it running
sudo journalctl -u wordscramble -f         # live logs
sudo journalctl -u wordscramble --since today | grep -i error
curl -I http://127.0.0.1:8000/             # bypass nginx
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| 502 from nginx | gunicorn isn't running — `journalctl -u wordscramble -n 50` |
| `database is locked` | WAL not enabled (step 4), or more than one worker |
| `unable to open database file` | `DB_PATH` directory missing, or not owned by the service user |
| Login loop | `SECRET_KEY` changing between restarts — make sure it's in `.env`, not generated at boot |
| Styles missing | The CDN is unreachable, or the `/static/` alias path is wrong |
| Changes not showing | Forgot `systemctl restart` — there's no auto-reload in production |
| Uploading a list fails | `LISTS_DIR` missing or not writable by the service user |
| Upload says "too big" | Body over 256 KB (`MAX_CONTENT_LENGTH`); a word list should be a few KB |
