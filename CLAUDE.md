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

Full guides: `DEVELOPMENT.md` (setup, testing, common changes) and
`DEPLOYMENT.md` (droplet, gunicorn, systemd, nginx, backups). Update them when
the workflow changes.

## Architecture

```
app.py        create_app() factory; wsgi.py is the production entry point
config.py     Config/TestConfig, all values from environment variables
routes/       pages.py (HTML) and api.py (JSON) blueprints — validation only
game.py       Game rules: start/check/hint/skip/summarise
scoring.py    Points, hint cost, star thresholds
words.py      Word list loading, weighted selection, scrambling
database.py   All SQL; connection() context manager commits/rolls back/closes
auth.py       Optional shared-PIN gate, enabled by setting ACCESS_PIN
```

Layering rule: **routes → game → database**. Routes never contain SQL or game
rules; `game.py` never touches `request` or `render_template`.

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
- Sound via `playSfx(name)`; register files with `loadSounds()` in `base.html`
- Config comes from environment variables via `config.py` — never hardcode
  paths, secrets, or debug flags

## Testing

`pytest` — tests use a temporary SQLite file per test via the `app` fixture in
`tests/conftest.py`. When changing game rules, update `tests/test_game.py`;
when changing the challenge-word logic, `tests/test_word_stats.py`.

## Deployment Notes

See `DEPLOYMENT.md` for the full procedure. The essentials:

- `FLASK_DEBUG` must stay off in production (Werkzeug debugger = RCE)
- Set `SECRET_KEY` and `ACCESS_PIN` in `.env` (never committed)
- Point `DB_PATH` outside the app directory so redeploys don't wipe scores
- SQLite is a deliberate choice for this workload - see the README. Enable WAL
  and run gunicorn with one worker and several threads
- `docs/` is gitignored for local scratch notes; tracked documentation lives at
  the repo root and the screenshot in `screenshots/`
