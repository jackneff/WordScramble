# WordScramble — CLAUDE.md

## Project Overview

A kid-friendly word-scramble spelling game, built for my daughter to practise
her spelling list and kept clean enough to show as a portfolio project. Python/
Flask backend, SQLite, and a vanilla JS + Alpine.js + Tailwind CSS frontend.
No build step — everything runs directly.

**Do not put family members' names in the repo** (code, comments, docs, commit
messages, or asset filenames). The art credit is deliberately anonymous:
"my daughter".

## Stack

- **Backend:** Python 3.10+, Flask, application factory in `app.py`
- **Database:** SQLite via `sqlite3` (`database.py`)
- **Frontend:** Jinja2 (`templates/`), Alpine.js + Tailwind (CDN), plain JS in `static/js/`
- **Tests:** pytest (`tests/`)

## Running

```bash
./scripts/setup.sh    # Windows: .\scripts\setup.ps1
./scripts/run.sh      # Windows: .\scripts\run.ps1    -> http://localhost:5000
./scripts/test.sh     # Windows: .\scripts\test.ps1
```

Scripts live in `scripts/`, paired `.sh` and `.ps1`. Keep both in step when
changing one.

Full guides: `docs/DEVELOPMENT.md` (setup, testing, common changes) and
`docs/DEPLOYMENT.md` (droplet, gunicorn, systemd, Cloudflare Access, tunnel,
backups). Update them when the workflow changes.

## Architecture

```
app.py        create_app() factory; wsgi.py is the production entry point
config.py     Config/TestConfig, all values from environment variables
routes/       pages.py (HTML), api.py (JSON), lists.py (list management),
              players.py (the profile picker: create/select/delete)
game.py       Game rules: start/check/hint/skip/summarise
scoring.py    Points, hint cost, star thresholds
words.py      Built-in word pool: loading, weighted selection, scrambling
wordlists.py  Parent-supplied vocabulary lists (static/words/lists/*.txt)
database.py   All SQL; connection() context manager commits/rolls back/closes
auth.py       Cloudflare Access gate, enabled by AUTH_MODE=cloudflare
players.py    session['player_id']: the active profile, not an identity
security.py   CSRF tokens on every state-changing request
```

Layering rule: **routes → game → database**. Routes never contain SQL or game
rules; `game.py` never touches `request` or `render_template`.

## Player profiles

Every player shares one Cloudflare Access login but plays under their own
profile — a `players` row, selected via the "Who's Playing?" picker and held
in `session['player_id']` (`players.py`). This is attribution and isolation,
**not** a second authentication layer: `auth.py` and Cloudflare Access remain
the only security boundary, and `players.py` is deliberately a separate
module so that distinction doesn't blur.

- Every query touching `rounds`, `round_words` or `word_stats` takes a
  `player_id` and filters or attributes by it, all the way down to
  `database.py`. A query that forgets the filter leaks one player's data to
  another, not just a wrong result.
- Every route that takes a `round_id` or `round_word_id` from the URL or a
  request body must check it belongs to the active player before touching it
  — `game.player_owns_round()` / `game.player_owns_round_word()` — and 404 if
  not. This check, not the schema, is what actually stops one player from
  reading or resuming another's in-progress round.
- `/progress` and `/progress/<player_id>` are the parent-facing dashboard:
  read-only, and they must never call `players.set_current_player()`.
  Looking at a profile's progress must never sign into it or touch whatever
  round it currently has open.

## Key Conventions

- No build step — keep the CDN imports, don't introduce a bundler
- All SQL lives in `database.py`, always parameterised, always via `connection()`
- Scoring constants live only in `scoring.py`; never re-derive them in a route
  or template (the summary and history pages disagreed when they did)
- The API must never return the answer word for an unsolved word — see
  `game._presented()` and the test that guards it
- JS lives in `static/js/`, not inline in templates
- CSS variables in `theme.css` for all colors — `var(--name)`, not literals
- Word files: `static/words/words_<length>.txt`, one word per line
- Custom lists: any `static/words/lists/<slug>.txt`; read fresh on every request
  so a parent can add one without a restart - do not add caching there
- Never build a path from a user-supplied list slug or an uploaded filename;
  slugify the parent's chosen name and match against `available_lists()`
- Uploaded list text is parsed into words only - never executed or rendered raw
- Sound via `playSfx(name)`; register files with `loadSounds()` in `base.html`
- Config comes from environment variables via `config.py` — never hardcode
  paths, secrets, or debug flags
- Every new POST/PUT/PATCH/DELETE needs a CSRF token: a hidden `csrf_token`
  field in the form, or `jsonHeaders()` from `static/js/csrf.js` for fetch
- Never exempt a route from the auth guard in `auth.py` without a written
  reason; `/static` is gated too, because `LISTS_DIR` can live under it

## Testing

`pytest` — tests use a temporary SQLite file per test via the `app` fixture in
`tests/conftest.py`, which also creates one default profile (`player_id`
fixture); `other_player_id` and `make_client` exist for tests that need a
second profile. When changing game rules, update `tests/test_game.py`; when
changing the challenge-word logic, `tests/test_word_stats.py`; when changing
anything about profiles, isolation or the schema migration,
`tests/test_players.py`.

## Deployment Notes

See `docs/DEPLOYMENT.md` for the full procedure. The essentials:

- `FLASK_DEBUG` must stay off in production (Werkzeug debugger = RCE)
- Set `SECRET_KEY`, `AUTH_MODE=cloudflare`, `CF_ACCESS_TEAM` and `CF_ACCESS_AUD`
  in `.env` (never committed); `create_app` refuses to boot without them
- Point `DB_PATH` outside the app directory so redeploys don't wipe scores
- SQLite is a deliberate choice for this workload - see the README. Enable WAL
  and run gunicorn with one worker and several threads
- `docs/` is gitignored for local scratch notes; tracked documentation lives at
  the repo root and the screenshot in `screenshots/`
