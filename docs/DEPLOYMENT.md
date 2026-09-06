# Deployment Guide

Deploying Word Scramble to a DigitalOcean droplet (or any Ubuntu/Debian host),
served by gunicorn, reached through a Cloudflare tunnel, and gated by
Cloudflare Access.

Assumes a non-root user with sudo, and a domain on Cloudflare's nameservers.

**What protects what.** Cloudflare Access authenticates the person, at
Cloudflare's edge, before any request reaches the droplet. The tunnel means the
droplet has no open ports at all, so there is no origin to attack around
Cloudflare. The app then re-checks the signed assertion itself (`auth.py`) --
including its audience, which is what stops a token issued for some other app
in the same Cloudflare team from working here. `SECRET_KEY` signs the session
cookie, which now carries only flash messages. CSRF tokens protect `/lists`,
where files are written and deleted.

There is no nginx and no certbot in this setup: Cloudflare terminates TLS, and
gunicorn serves `/static/` itself. That is a small performance cost and one
less public service to patch.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git sqlite3
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

Cloudflare terminates TLS, so `SESSION_COOKIE_SECURE=1` is correct from the
start.

Create `.env`. Leave `CF_ACCESS_TEAM` and `CF_ACCESS_AUD` blank for now and
fill them in during step 6 — the app will refuse to start until you do:

```bash
cat > /srv/wordscramble/.env <<EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DB_PATH=/var/lib/wordscramble/wordscramble.db
LISTS_DIR=/var/lib/wordscramble/lists
AUTH_MODE=cloudflare
CF_ACCESS_TEAM=
CF_ACCESS_AUD=
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
EOF

chmod 600 /srv/wordscramble/.env
```

Four settings matter:

- **`FLASK_DEBUG` must be 0.** The Werkzeug debugger is an interactive Python
  console exposed to anyone who triggers an error — remote code execution on a
  public host. This is the single most important line in this file.
- **`AUTH_MODE=cloudflare`** makes the app reject any request that does not
  carry a valid Cloudflare Access assertion. The alternative, `none`, leaves
  the app wide open: anyone who finds the URL can play, read the score history,
  and add or delete word lists.
- **`CF_ACCESS_TEAM` and `CF_ACCESS_AUD`** identify your Zero Trust team and
  this specific application. The audience tag is the important half — it is
  what makes a token minted for a different app in the same team useless here.
- **`SECRET_KEY`** signs the session cookie. It no longer holds identity, but a
  predictable key would still let someone forge flash messages and CSRF tokens.

These are checked at startup, not merely documented: `_check_deployment()` in
`app.py` raises on a missing audience tag, on the placeholder `SECRET_KEY`, and
on the dangerous combination of `SESSION_COOKIE_SECURE=1` with `AUTH_MODE=none`.
A misconfigured deployment fails to boot rather than coming up unprotected.

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
the tunnel process on this host can talk to it.

## 6. Cloudflare Access

This is the login. Everything before it was plumbing.

In the [Zero Trust dashboard](https://one.dash.cloudflare.com):

1. **Settings > Custom Pages** — note your team name (the `<team>` in
   `<team>.cloudflareaccess.com`). That is `CF_ACCESS_TEAM`.
2. **Settings > Authentication** — add login methods. Google and
   **One-time PIN** (Cloudflare emails a code) are enough; one-time PIN means a
   family member needs no account anywhere.
3. **Access > Applications > Add an application > Self-hosted.** Set the domain
   to `words.example.com`. Session duration of 1 month keeps a tablet signed in.
4. Add a policy: action **Allow**, rule **Emails**, and list the specific
   addresses. Use `Emails`, not `Everyone` and not `Any Google account` — the
   allowlist is the whole access-control model.
5. On the application's **Overview** tab, copy the **Application Audience (AUD)
   Tag**. That is `CF_ACCESS_AUD`.

Put both values in `.env` and restart:

```bash
sudo systemctl restart wordscramble
sudo systemctl status wordscramble     # a bad value shows up here as a RuntimeError
```

The free Zero Trust plan covers 50 users, which is roughly 47 more than this
needs.

## 7. The tunnel

`cloudflared` dials out to Cloudflare and receives traffic over that
connection, so the droplet needs no inbound ports at all:

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg     | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main"     | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared

cloudflared tunnel login
cloudflared tunnel create wordscramble
cloudflared tunnel route dns wordscramble words.example.com
```

`/etc/cloudflared/config.yml`:

```yaml
tunnel: wordscramble
credentials-file: /root/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: words.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

gunicorn is already bound to `127.0.0.1:8000` from step 5, so nothing else
changes.

## 8. Firewall

No inbound HTTP at all — the tunnel is outbound-only:

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

Then confirm from somewhere else that the droplet itself serves nothing:

```bash
curl -m 5 -I http://YOUR.DROPLET.IP/        # should time out or refuse
```

Visiting `https://words.example.com` should now bounce you to a Cloudflare
sign-in, and an address outside the policy should be refused there — without
the request ever reaching the droplet.

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
sudo systemctl status cloudflared          # is the tunnel connected
sudo journalctl -u wordscramble | grep 'Access denied'   # refused requests
```

`Access denied` lines carry the method and path, and successful requests are
attributed to the signed-in email address. A steady trickle of denials is
normal — it is mostly crawlers hitting the hostname and being turned away.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Cloudflare error 1033 | The tunnel is down — `systemctl status cloudflared` |
| 502 from Cloudflare | gunicorn isn't running — `journalctl -u wordscramble -n 50` |
| Service won't start | A startup check failed; the `RuntimeError` in `journalctl` names the setting |
| "Not signed in" after signing in | `CF_ACCESS_AUD` doesn't match the app's Audience tag |
| Everyone is refused | The Access policy allowlist doesn't include the address, or `CF_ACCESS_TEAM` is wrong |
| `database is locked` | WAL not enabled (step 4), or more than one worker |
| `unable to open database file` | `DB_PATH` directory missing, or not owned by the service user |
| "Invalid CSRF token" on every form | `SECRET_KEY` changing between restarts — make sure it's in `.env`, not generated at boot |
| Styles missing | The CDN is unreachable |
| Changes not showing | Forgot `systemctl restart` — there's no auto-reload in production |
| Uploading a list fails | `LISTS_DIR` missing or not writable by the service user |
| Upload says "too big" | Body over 256 KB (`MAX_CONTENT_LENGTH`); a word list should be a few KB |
