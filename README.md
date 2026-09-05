# Word Scramble

A word-scramble spelling game for early readers. Drag the scrambled letter tiles
into place to spell the word, earn stars for the round — and the app quietly
tracks which words keep causing trouble so it can serve them back later.

Built for my daughter to practise her weekly spelling list. The mascot is her
drawing; I vectorised it.

![Choosing a word list](docs/screenshots/01-home.png)

<table>
<tr>
<td width="50%"><img src="docs/screenshots/02-gameplay.png" alt="Unscrambling a word"></td>
<td width="50%"><img src="docs/screenshots/03-correct.png" alt="Correct answer celebration"></td>
</tr>
<tr>
<td><img src="docs/screenshots/04-summary.png" alt="Round complete summary"></td>
<td><img src="docs/screenshots/05-challenge-words.png" alt="Challenge words tracking"></td>
</tr>
</table>

<p align="center"><img src="docs/screenshots/06-my-scores.png" width="70%" alt="Score history"></p>

**Python 3.10+ · Flask · SQLite · Alpine.js · Tailwind CSS · pytest**

```bash
./scripts/setup.sh && ./scripts/run.sh     # Windows: .\scripts\setup.ps1
```

Then open <http://localhost:5000>. No build step, no bundler, no Node.

---

## This week's spelling words

Drop a `.txt` file into `static/words/lists/` — one word per line — and it
appears in the picker on the home screen. No restart, no code change, no
naming convention: `week-12.txt` becomes "Week 12". A parent can put the
actual list from school into the game in about thirty seconds.

A list is played on its own terms. Ask for a 15-word round from a 10-word
list and you get a 10-word round, because padding it with unrelated words
would defeat the point of practising that list. Words from a list feed the
same challenge tracking as everything else, so the ones that keep going wrong
resurface later.

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

- **Custom word lists** — drop this week's spelling words in as a text file
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
words.py      Built-in word pool: loading, weighted selection, scrambling
wordlists.py  Parent-supplied vocabulary lists, read fresh on every request
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

82 tests covering the scoring rules, word selection, the hint and skip flows,
challenge-word graduation, custom word lists (including path-traversal
attempts), history paging, and the HTTP layer including the PIN gate. Each test
runs against its own throwaway SQLite file.

## Documentation

- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** — setup, running, testing, and how to
  change words, scoring or the schema
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — gunicorn, systemd, nginx, HTTPS and
  backups on a DigitalOcean droplet

## Credits

- Character design and original drawings — my daughter
- Vectorisation and code — me
- Word lists — [k5learning.com](https://www.k5learning.com)
- Sound effects — [Pixabay](https://pixabay.com)
