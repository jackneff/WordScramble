# Word Scramble

A word-scramble spelling game for early readers. Drag the scrambled letter tiles
into place to spell the word, earn stars for the round — and the app quietly
tracks which words keep causing trouble so it can serve them back later.

Built for my daughter to practise her weekly spelling list. The mascot is her
drawing; I vectorised it.

![Gameplay](screenshots/gameplay.png)

**Python 3.10+ · Flask · SQLite · Alpine.js · Tailwind CSS · pytest**

```bash
./scripts/setup.sh && ./scripts/run.sh     # Windows: .\scripts\setup.ps1
```

Then open <http://localhost:5000>. No build step, no bundler, no Node.

---

## The interesting part

Most spelling apps for kids are drill-and-repeat: the same words in the same
order, regardless of what the child actually finds hard. This one adapts.

**It measures hesitation, not just correctness.** A solve that takes longer than
roughly two seconds per letter counts as a partial miss, and more than four
seconds per letter counts double — a long pause usually means guessing, even
when the final answer is right. Wrong attempts and skips weigh in too. Words
accumulate misses, surface on a **Challenge Words** page, and only graduate off
it after three clean solves.

**It looks for patterns.** When several practice words share an ending (`-ing`,
`-tion`, `-ould`), the app points that out — words a child struggles with tend
to cluster around a spelling rule rather than being independently hard, and
that's the more useful thing to practise.

A Challenge Round then builds a game entirely from the current practice list,
topping up with ordinary words when it's short.

## Features

- Drag-and-drop **or** tap-to-place letter tiles; the first letter is given
- Hints reveal the next correct letter for 15 points
- 1–3 star ratings based on the round's share of a perfect score
- Automatic challenge-word tracking with a dedicated round mode
- History of every completed round
- Rounds resume where you left off if the page is reloaded
- Optional PIN gate for hosting somewhere public

## Architecture

```
app.py        create_app() factory; wsgi.py is the production entry point
config.py     Config / TestConfig, every value from an environment variable
routes/       pages.py (HTML) and api.py (JSON) blueprints
game.py       Game rules: start, check, hint, skip, summarise
scoring.py    Points, hint cost, star thresholds
words.py      Word list loading, weighted selection, scrambling
database.py   All SQL, behind a connection() context manager
auth.py       Optional shared-PIN gate
```

Three decisions shape it:

**The client never sees the answer.** `/api/round/<id>` returns the scrambled
letters, the length and the first letter — never the word. Answers are checked
and scored server-side, so a score can't be forged from the browser console. A
test fails if a field ever leaks into that payload.

**The rules live in exactly one place.** Points, hint costs and star thresholds
are all in `scoring.py`. They used to be scattered, and the summary and history
pages disagreed about the same round as a result; a regression test now asserts
the two agree.

**Routes stay thin.** They validate input and hand off to `game.py`, which has
no idea HTTP exists — so the rules are tested directly, without a request.

### Scoring

| | |
|---|---|
| Base score | word length × 10 |
| Hint | −15 points each, never below 0 |
| Skip | 0 points, counts as 3 misses against the word |
| Stars | ≥80% of the round maximum = 3★, ≥50% = 2★, else 1★ |

### Why SQLite

Deliberate, not a default. The workload is one child at a time and a few hundred
writes a week, which SQLite handles with enormous headroom. In exchange the
whole database is a single file: backup is one command, there's no second
service to run on boot, no connection pool to tune, and no ~200 MB of resident
memory spent on a database server for a single-user game. Postgres would be
operational overhead with nothing to show for it at this scale.

## Tests

```bash
./scripts/test.sh          # Windows: .\scripts\test.ps1
```

47 tests covering the scoring rules, word selection, the hint and skip flows,
challenge-word graduation, and the HTTP layer including the PIN gate. Each test
runs against its own throwaway SQLite file.

## Documentation

- **[DEVELOPMENT.md](DEVELOPMENT.md)** — setup, running, testing, and how to
  change words, scoring or the schema
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — gunicorn, systemd, nginx, HTTPS and
  backups on a DigitalOcean droplet

## Credits

- Character design and original drawings — my daughter
- Vectorisation and code — me
- Word lists — [k5learning.com](https://www.k5learning.com)
- Sound effects — [Pixabay](https://pixabay.com)
