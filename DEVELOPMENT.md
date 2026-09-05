# Development Guide

How to set up, run, test and extend Word Scramble.

## Requirements

- **Python 3.10 or newer** (`py --version` on Windows, `python3 --version` elsewhere)
- A browser. That's it — there is no Node toolchain, no bundler, no build step.

Alpine.js and Tailwind load from a CDN, so the first run needs an internet
connection. Everything else works offline.

## Setup

**Windows (PowerShell)**

```powershell
.\scripts\setup.ps1
```

**macOS / Linux**

```bash
./scripts/setup.sh
```

The script creates `.venv`, installs the app and test dependencies, and copies
`.env.example` to `.env` if you don't have one. Every setting has a working
default, so the fresh `.env` needs no edits for local work.

<details>
<summary>Doing it by hand</summary>

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```
</details>

If PowerShell refuses to run the scripts, allow local scripts for your user
once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Running

```powershell
.\scripts\run.ps1                  # http://127.0.0.1:5000
.\scripts\run.ps1 -Port 8000
```

```bash
./scripts/run.sh
PORT=8000 ./scripts/run.sh
```

Both set `FLASK_DEBUG=1`, which gives auto-reload on save and full tracebacks
in the browser. The SQLite database is created on first run.

## Testing

```powershell
.\scripts\test.ps1                 # all 47 tests
.\scripts\test.ps1 -- -k scoring   # just the scoring tests
.\scripts\test.ps1 -- -v           # verbose
```

```bash
./scripts/test.sh
./scripts/test.sh -k scoring -v
```

Each test gets a fresh SQLite file in a pytest `tmp_path`, so tests never touch
your development database and never depend on each other's data. The fixtures
live in `tests/conftest.py`:

| Fixture | What it gives you |
|---|---|
| `app` | A configured app on a throwaway database |
| `client` | Flask test client for HTTP-level tests |
| `round_words` | A ready-made round of `cat` and `house` |

## How the code is arranged

```
app.py        create_app() factory; wsgi.py is the production entry point
config.py     Config / TestConfig, every value from an environment variable
routes/
  pages.py    HTML pages
  api.py      JSON API — parses and validates input, nothing else
game.py       Game rules: start, check, hint, skip, summarise
scoring.py    Points, hint cost, star thresholds
words.py      Word list loading, weighted selection, scrambling
database.py   All SQL, behind a connection() context manager
auth.py       Optional shared-PIN gate
templates/    Jinja2
static/js/    game.js, sfx.js, sparkles.js, start-round.js
static/words/ words_3.txt ... words_8.txt
tests/        pytest suite
```

The dependency direction is **routes → game → database**, and it only goes that
way. A route never contains SQL or a scoring rule; `game.py` never imports
`request` or `render_template`. That's what lets the rules be tested without
spinning up HTTP.

## Common changes

### Add or change words

Edit the file matching the word's length — `static/words/words_6.txt` for a
six-letter word — one lowercase word per line. Adding a new length is just
creating `words_9.txt`; the loader picks up any `words_<n>.txt` it finds.

To have nine-letter words actually appear in rounds, add a weight in
`words.py`:

```python
LENGTH_WEIGHTS = {3: 0.10, 4: 0.25, 5: 0.30, 6: 0.20, 7: 0.10, 8: 0.05}
```

The weights are shares of a round and should sum to 1.0. They are proportional,
not guaranteed: a 5-word round won't include every length.

### Change the scoring

Everything lives in `scoring.py`:

```python
POINTS_PER_LETTER = 10
HINT_PENALTY = 15
THREE_STAR_PCT = 80
TWO_STAR_PCT = 50
```

Change it there and the game, summary and history pages all follow. Don't
recompute a score in a route or a template — the summary and history pages used
to do exactly that and disagreed about the same round. `tests/test_scoring.py`
and the `test_history_and_summary_agree_on_stars` regression test guard this.

### Change how words become "challenge words"

In `database.py`:

- `miss_events_for()` — how many misses a solve is worth. A solve slower than
  ~2 seconds per letter counts as one miss, slower than ~4 seconds counts as
  two, on the theory that a long pause means guessing.
- `SKIP_MISS_WEIGHT` — how heavily skipping a word counts (currently 3)
- `GRADUATION_STREAK` — clean solves needed to leave the list (currently 3)

Tests for all of this are in `tests/test_word_stats.py`.

### Change the schema

Add the table or column to `_SCHEMA` in `database.py` (everything uses
`IF NOT EXISTS`), bump `SCHEMA_VERSION`, and add the `ALTER TABLE` for existing
databases next to the `wrong_attempts` migration in `init_db()`. There is no
migration framework — at this size, that's a feature.

### Add a page

1. A route in `routes/pages.py`
2. A template extending `base.html`
3. A nav link in `base.html`, using `url_for('pages.<name>')` rather than a
   hardcoded path

### Add an API endpoint

Put the rule in `game.py` and a thin wrapper in `routes/api.py` that validates
input and returns JSON. Two rules:

- **Never return an unsolved word's answer.** `game._presented()` controls the
  shape sent to the client, and `test_round_state_does_not_leak_the_answer`
  fails if a field sneaks in.
- **Never trust a number from the client.** Ids and sizes go through the
  validation helpers in `routes/api.py`.

## Frontend notes

Alpine.js drives the game screen; everything else is plain JS and server-
rendered HTML. Scripts are loaded normally (not deferred) in `base.html` so
their globals exist before Alpine boots and evaluates `x-data`.

`static/js/game.js` holds the whole game screen as one Alpine component. It
tracks which tile sits in which blank and asks the server to judge the word once
every blank is filled — it never knows the answer.

Two constants must stay in step with the CSS animations in `theme.css`:

```js
SUCCESS_MS: 2200,   // success overlay
SHAKE_MS: 500,      // wrong-answer shake
```

Use `x-cloak` on anything Alpine hides, so it isn't visible for a frame before
Alpine initialises.

### Sound

Register a file with `loadSounds()` in `base.html`, then call `playSfx('name')`.
Playback goes through the Web Audio API, not `<audio>` elements: replaying an
`<audio>` element for a rapid effect like a letter placement is audibly laggy
because each play seeks and restarts it. Buffers decode once on load, with an
`<audio>` fallback for the window before decoding completes.

### Colours

All colours are CSS variables in `static/css/theme.css`. Use
`var(--glow-blue)`, never a hex literal.

## Troubleshooting

**`No .venv found`** — run the setup script first.

**PowerShell says running scripts is disabled** — see the `Set-ExecutionPolicy`
line under Setup.

**Sounds don't play until you click** — expected. Browsers block audio until the
page gets a user gesture; `playSfx` resumes the audio context on the first one.

**Port already in use** — `.\scripts\run.ps1 -Port 8000`, or stop the stray
server. On Windows: `Get-Process python | Stop-Process`.

**Changing the schema did nothing** — `CREATE TABLE IF NOT EXISTS` won't alter
an existing table. Delete `wordscramble.db` (it's gitignored, and only holds
practice scores) or add an explicit `ALTER TABLE`.

**Tests pass but the browser is stale** — hard-reload to bypass the cached JS:
Ctrl+F5.

## Before committing

```powershell
.\scripts\test.ps1
```

And check that no family names appear in the diff — the repo is public and the
art credit is deliberately anonymous.
