#!/usr/bin/env bash
# Update a running deployment: back up, pull, install, restart, verify.
#
# Run this ON the droplet, from anywhere:
#
#   /srv/wordscramble/scripts/deploy.sh              # deploy origin/main
#   /srv/wordscramble/scripts/deploy.sh --check      # report only, change nothing
#   /srv/wordscramble/scripts/deploy.sh --ref v1.2   # deploy a tag or branch
#
# Overridable: APP_DIR, SERVICE, DB_PATH, BACKUP_DIR, REF.
#
# Needs sudo for systemctl only; it will prompt if your session has no ticket.
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/wordscramble}"
SERVICE="${SERVICE:-wordscramble}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/wordscramble}"
REF="${REF:-origin/main}"
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK_ONLY=1; shift ;;
        --ref)   REF="${2:?--ref needs a branch, tag or commit}"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

cd "$APP_DIR" || fail "$APP_DIR does not exist"
[[ -f wsgi.py ]] || fail "$APP_DIR does not look like the app (no wsgi.py)"
[[ -x .venv/bin/python ]] || fail "no virtualenv at $APP_DIR/.venv - run ./scripts/setup.sh --prod"

# The health check hits whatever address the unit actually binds, so this keeps
# working if the port ever changes.
BIND=$(systemctl cat "$SERVICE" 2>/dev/null | sed -n 's/.*--bind[= ]\+\([0-9.]\+:[0-9]\+\).*/\1/p' | head -1)
BIND="${BIND:-127.0.0.1:8000}"

# DB_PATH comes from .env unless the caller overrides it. Tolerates `export`,
# surrounding quotes, stray whitespace and CRLF endings, and reports why it came
# up empty rather than quietly skipping the backup.
DB_SOURCE="the DB_PATH environment variable"
if [[ -z "${DB_PATH:-}" ]]; then
    DB_SOURCE="$APP_DIR/.env"
    if [[ ! -e .env ]]; then
        DB_NOTE="no .env file in $APP_DIR"
    elif [[ ! -r .env ]]; then
        DB_NOTE=".env is not readable by $(id -un)"
    else
        DB_PATH=$(sed -n 's/\r$//; s/^[[:space:]]*//; s/^export[[:space:]]\{1,\}//; s/^DB_PATH[[:space:]]*=[[:space:]]*//p' .env | tail -1)
        DB_PATH="${DB_PATH%\"}"; DB_PATH="${DB_PATH#\"}"
        DB_PATH="${DB_PATH%\'}"; DB_PATH="${DB_PATH#\'}"
        [[ -z "$DB_PATH" ]] && DB_NOTE="no DB_PATH= line in .env"
    fi
fi

say "Current state"
echo "  app       $APP_DIR"
echo "  service   $SERVICE ($(systemctl is-active "$SERVICE" 2>/dev/null || echo unknown), bound to $BIND)"
echo "  database  ${DB_PATH:-<unset> (${DB_NOTE:-unknown})}"
echo "  deployed  $(git rev-parse --short HEAD) $(git log -1 --format=%s)"

say "Fetching"
git fetch --all --prune --quiet
TARGET=$(git rev-parse --short "$REF") || fail "no such ref: $REF"

if [[ "$TARGET" == "$(git rev-parse --short HEAD)" ]]; then
    echo "  already at $TARGET ($REF) - nothing to deploy"
    [[ $CHECK_ONLY -eq 1 ]] && exit 0
    echo "  restarting anyway to pick up any .env change"
else
    echo "  incoming commits:"
    git --no-pager log --oneline HEAD.."$REF" | sed 's/^/    /'
fi

# A dirty tree means someone edited the server in place; stop rather than
# silently discarding it.
if [[ -n "$(git status --porcelain)" ]]; then
    echo
    git --no-pager status --short | sed 's/^/    /'
    echo
    echo "  M = a tracked file was edited on the server; ?? = an untracked stray."
    echo "  A deploy never touches untracked files, so if that is all you see:"
    echo "    git status --porcelain | grep -v '^??'   # empty means it is safe to ignore"
    fail "the working tree on the server has local changes - resolve them first"
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
    say "--check: stopping here, nothing was changed"
    exit 0
fi

say "Backing up the database"
if [[ -z "${DB_PATH:-}" ]]; then
    # Deploying with no backup is a real risk, not a detail - make it deliberate.
    echo "  cannot locate the database: ${DB_NOTE:-DB_PATH is unset} (looked in $DB_SOURCE)"
    read -r -p "  Deploy WITHOUT a backup? [y/N] " reply </dev/tty
    [[ "$reply" == [yY] ]] || fail "stopped - re-run as DB_PATH=/path/to/wordscramble.db $0"
elif [[ -f "$DB_PATH" ]]; then
    sudo mkdir -p "$BACKUP_DIR"
    STAMP=$(date +%F-%H%M%S)
    # .backup is safe on a live database; cp is not.
    sudo sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/pre-deploy-$STAMP.db'"
    echo "  $BACKUP_DIR/pre-deploy-$STAMP.db"
else
    echo "  $DB_PATH does not exist yet - nothing to back up"
fi

say "Updating the code to $TARGET"
# For a remote branch, stay on the local branch and fast-forward it, so the
# server keeps a sensible HEAD instead of drifting into a detached one.
if [[ "$REF" =~ ^origin/(.+)$ ]]; then
    git checkout --quiet "${BASH_REMATCH[1]}"
    git merge --ff-only --quiet "$REF" || fail "cannot fast-forward ${BASH_REMATCH[1]} to $REF"
else
    git -c advice.detachedHead=false checkout --quiet "$REF"
fi
git --no-pager log -1 --format='  %h %s (%an, %ar)'

say "Installing dependencies"
.venv/bin/python -m pip install -r requirements.txt --quiet
echo "  done"

say "Restarting $SERVICE"
sudo systemctl restart "$SERVICE"

# Startup checks in app.py raise on a bad .env, and gunicorn needs a moment to
# bind, so give it a few seconds before calling it a failure.
for _ in $(seq 15); do
    sleep 1
    systemctl is-active --quiet "$SERVICE" && break
done

if ! systemctl is-active --quiet "$SERVICE"; then
    echo
    sudo journalctl -u "$SERVICE" -n 30 --no-pager
    fail "$SERVICE did not come back up (log above; a RuntimeError names the bad setting)"
fi

say "Verifying"
CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://$BIND/" || echo 000)
case "$CODE" in
    403) echo "  http $CODE from $BIND - correct: no Cloudflare assertion, so the app refuses" ;;
    200) echo "  http $CODE from $BIND - responding, but unauthenticated requests are being served."
         echo "  Check AUTH_MODE=cloudflare in $APP_DIR/.env" ;;
    000) fail "no response from $BIND - check: journalctl -u $SERVICE -n 50" ;;
    *)   fail "unexpected http $CODE from $BIND - check: journalctl -u $SERVICE -n 50" ;;
esac

echo "  tunnel    $(systemctl is-active cloudflared 2>/dev/null || echo 'not installed here')"

say "Deployed $TARGET"
echo "Live logs:  sudo journalctl -u $SERVICE -f"
