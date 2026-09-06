"""SQLite persistence layer.

All database access goes through this module. Connections are short-lived and
opened per operation via the `connection()` context manager, which commits on
success, rolls back on error, and always closes.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import Config

SCHEMA_VERSION = 4

_db_path = Config.DB_PATH


def configure(db_path):
    """Point the module at a database file. Called by the app factory."""
    global _db_path
    _db_path = db_path


def get_db_path():
    return _db_path


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    """Yield a connection that commits on success and always closes."""
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    avatar TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    round_size INTEGER NOT NULL,
    total_score INTEGER DEFAULT 0,
    words_completed INTEGER DEFAULT 0,
    hints_used INTEGER DEFAULT 0,
    word_list TEXT
);

CREATE TABLE IF NOT EXISTS round_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES rounds(id),
    word TEXT NOT NULL,
    word_length INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    hints_used INTEGER DEFAULT 0,
    wrong_attempts INTEGER DEFAULT 0,
    solved INTEGER DEFAULT 0,
    solved_at TIMESTAMP,
    word_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS word_stats (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    miss_count INTEGER DEFAULT 0,
    consecutive_correct INTEGER DEFAULT 0,
    last_seen TIMESTAMP,
    PRIMARY KEY (player_id, word)
);

CREATE INDEX IF NOT EXISTS idx_round_words_round ON round_words(round_id);
CREATE INDEX IF NOT EXISTS idx_rounds_finished ON rounds(finished_at);
"""

# idx_rounds_player is created after the migrations below, not in _SCHEMA:
# on an upgrade, rounds.player_id does not exist yet when _SCHEMA runs, since
# CREATE TABLE IF NOT EXISTS is a no-op against the table that is already
# there. Indexing it has to wait until the ALTER TABLE has run.


def _column_names(conn, table):
    return {r["name"] for r in conn.execute("PRAGMA table_info(" + table + ")")}


def _default_player_id(conn):
    """The id of the migration's default profile, creating it if needed.

    Only ever called when pre-profile rows exist that need somewhere to land.
    """
    row = conn.execute(
        "SELECT id FROM players WHERE name = ?", (Config.DEFAULT_PLAYER_NAME,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO players (name) VALUES (?)", (Config.DEFAULT_PLAYER_NAME,)
    )
    return cur.lastrowid


def init_db():
    """Create the schema if absent and apply any pending migrations."""
    directory = os.path.dirname(_db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with connection() as conn:
        conn.executescript(_SCHEMA)

        # Databases created before wrong_attempts existed predate user_version
        # tracking, so detect the column directly rather than trusting the
        # version pragma alone.
        if "wrong_attempts" not in _column_names(conn, "round_words"):
            conn.execute(
                "ALTER TABLE round_words ADD COLUMN wrong_attempts INTEGER DEFAULT 0"
            )

        # v3: which vocabulary list a round was drawn from (NULL = all words).
        if "word_list" not in _column_names(conn, "rounds"):
            conn.execute("ALTER TABLE rounds ADD COLUMN word_list TEXT")

        # v4: player profiles. rounds.player_id may already exist (fresh
        # install, the CREATE TABLE above) or need adding (upgrade). Either
        # way, any round left with no player belongs to the one profile that
        # existed before profiles did.
        if "player_id" not in _column_names(conn, "rounds"):
            conn.execute(
                "ALTER TABLE rounds ADD COLUMN player_id INTEGER REFERENCES players(id) ON DELETE SET NULL"
            )

        orphaned = conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE player_id IS NULL"
        ).fetchone()[0]
        if orphaned:
            default_id = _default_player_id(conn)
            conn.execute(
                "UPDATE rounds SET player_id = ? WHERE player_id IS NULL", (default_id,)
            )

        # word_stats gained a player_id and a composite primary key in v4;
        # SQLite cannot ALTER a primary key, so a bare `word TEXT PRIMARY KEY`
        # table is rebuilt wholesale and every existing row is attributed to
        # the same default profile as the orphaned rounds above.
        if "player_id" not in _column_names(conn, "word_stats"):
            has_rows = conn.execute("SELECT COUNT(*) FROM word_stats").fetchone()[0] > 0
            default_id = _default_player_id(conn) if has_rows else None
            conn.execute(
                """CREATE TABLE word_stats_new (
                       player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                       word TEXT NOT NULL,
                       miss_count INTEGER DEFAULT 0,
                       consecutive_correct INTEGER DEFAULT 0,
                       last_seen TIMESTAMP,
                       PRIMARY KEY (player_id, word)
                   )"""
            )
            if has_rows:
                conn.execute(
                    """INSERT INTO word_stats_new
                           (player_id, word, miss_count, consecutive_correct, last_seen)
                       SELECT ?, word, miss_count, consecutive_correct, last_seen
                       FROM word_stats""",
                    (default_id,),
                )
            conn.execute("DROP TABLE word_stats")
            conn.execute("ALTER TABLE word_stats_new RENAME TO word_stats")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rounds_player ON rounds(player_id, finished_at)"
        )

        conn.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))


# --------------------------------------------------------------------------
# Players
# --------------------------------------------------------------------------

def create_player(name, avatar=None):
    """Create a profile. Returns its id, or None if the name is taken."""
    with connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO players (name, avatar) VALUES (?, ?)", (name, avatar)
            )
        except sqlite3.IntegrityError:
            return None
        return cur.lastrowid


def get_player(player_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()
    return dict(row) if row else None


def get_player_by_name(name):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE name = ?", (name,)
        ).fetchone()
    return dict(row) if row else None


def list_players():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM players ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def rename_player(player_id, name):
    """Returns False if the new name is already taken by another profile."""
    with connection() as conn:
        try:
            conn.execute("UPDATE players SET name = ? WHERE id = ?", (name, player_id))
        except sqlite3.IntegrityError:
            return False
        return True


def delete_player(player_id):
    """Delete a profile.

    Their round history is kept, orphaned (player_id set to NULL) rather than
    deleted - a profile going away should not erase score history. Their
    word_stats rows go with them: that table's primary key includes
    player_id, so an orphaned row cannot exist, and challenge words only ever
    make sense attached to a profile that's still there to practise them.
    """
    with connection() as conn:
        conn.execute("DELETE FROM players WHERE id = ?", (player_id,))


# --------------------------------------------------------------------------
# Rounds
# --------------------------------------------------------------------------

def create_round(round_size, words, player_id, word_list=None):
    """Create a round and its words. Returns the new round id."""
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO rounds (round_size, player_id, word_list) VALUES (?, ?, ?)",
            (round_size, player_id, word_list),
        )
        round_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO round_words (round_id, word, word_length, word_order)"
            " VALUES (?, ?, ?, ?)",
            [(round_id, w, len(w), i + 1) for i, w in enumerate(words)],
        )
    return round_id


def get_round(round_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    return dict(row) if row else None


def get_round_owner(round_id):
    """The player_id a round belongs to, or None if the round is unknown."""
    with connection() as conn:
        row = conn.execute(
            "SELECT player_id FROM rounds WHERE id = ?", (round_id,)
        ).fetchone()
    return row["player_id"] if row else None


def get_round_word_owner(round_word_id):
    """The player_id that owns a round word, or None if it is unknown."""
    with connection() as conn:
        row = conn.execute(
            """SELECT r.player_id FROM round_words rw
               JOIN rounds r ON r.id = rw.round_id
               WHERE rw.id = ?""",
            (round_word_id,),
        ).fetchone()
    return row["player_id"] if row else None


def get_round_words(round_id):
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM round_words WHERE round_id = ? ORDER BY word_order",
            (round_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_round_word(round_word_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM round_words WHERE id = ?", (round_word_id,)
        ).fetchone()
    return dict(row) if row else None


def solve_word(round_word_id, score):
    """Mark a word solved and roll its score up into the round total."""
    with connection() as conn:
        conn.execute(
            "UPDATE round_words SET solved = 1, score = ?, solved_at = ? WHERE id = ?",
            (score, _now(), round_word_id),
        )
        conn.execute(
            """UPDATE rounds
               SET total_score = total_score + ?,
                   words_completed = words_completed + 1
               WHERE id = (SELECT round_id FROM round_words WHERE id = ?)""",
            (score, round_word_id),
        )


def add_hint(round_word_id):
    """Increment the hint count on a word and on its round."""
    with connection() as conn:
        conn.execute(
            "UPDATE round_words SET hints_used = hints_used + 1 WHERE id = ?",
            (round_word_id,),
        )
        conn.execute(
            """UPDATE rounds SET hints_used = hints_used + 1
               WHERE id = (SELECT round_id FROM round_words WHERE id = ?)""",
            (round_word_id,),
        )


def increment_wrong_attempts(round_word_id):
    with connection() as conn:
        conn.execute(
            "UPDATE round_words SET wrong_attempts = wrong_attempts + 1 WHERE id = ?",
            (round_word_id,),
        )


def finish_round(round_id):
    with connection() as conn:
        conn.execute(
            "UPDATE rounds SET finished_at = ? WHERE id = ? AND finished_at IS NULL",
            (_now(), round_id),
        )


def get_history(player_id, limit=20, offset=0):
    """One page of a player's completed rounds, newest first.

    `total_letters` is derived from the actual word lengths in each round, so
    history and the round summary always agree on the star rating.
    """
    with connection() as conn:
        rows = conn.execute(
            """SELECT r.id, r.started_at, r.finished_at, r.round_size,
                      r.total_score, r.hints_used, r.words_completed, r.word_list,
                      COALESCE(SUM(rw.word_length), 0) AS total_letters
               FROM rounds r
               LEFT JOIN round_words rw ON rw.round_id = r.id
               WHERE r.finished_at IS NOT NULL AND r.player_id = ?
               GROUP BY r.id
               ORDER BY r.started_at DESC, r.id DESC
               LIMIT ? OFFSET ?""",
            (player_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def count_finished_rounds(player_id):
    with connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE finished_at IS NOT NULL AND player_id = ?",
            (player_id,),
        ).fetchone()[0]


def get_round_scores(player_id):
    """Score and letter count for every one of a player's finished rounds.

    Two small columns per round, so this stays cheap; computing the star
    average in Python keeps the thresholds in scoring.py rather than
    duplicating them in SQL.
    """
    with connection() as conn:
        rows = conn.execute(
            """SELECT r.id, r.total_score,
                      COALESCE(SUM(rw.word_length), 0) AS total_letters
               FROM rounds r
               LEFT JOIN round_words rw ON rw.round_id = r.id
               WHERE r.finished_at IS NOT NULL AND r.player_id = ?
               GROUP BY r.id""",
            (player_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Word statistics ("challenge words")
# --------------------------------------------------------------------------

SKIP_MISS_WEIGHT = 3
GRADUATION_STREAK = 3


def _bump_stats(conn, player_id, word, miss_events):
    """Apply one result to a word's stats. Misses reset the correct streak."""
    now = _now()
    if miss_events > 0:
        conn.execute(
            """INSERT INTO word_stats (player_id, word, miss_count, consecutive_correct, last_seen)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(player_id, word) DO UPDATE SET
                   miss_count = miss_count + excluded.miss_count,
                   consecutive_correct = 0,
                   last_seen = excluded.last_seen""",
            (player_id, word, miss_events, now),
        )
    else:
        conn.execute(
            """INSERT INTO word_stats (player_id, word, miss_count, consecutive_correct, last_seen)
               VALUES (?, ?, 0, 1, ?)
               ON CONFLICT(player_id, word) DO UPDATE SET
                   consecutive_correct = consecutive_correct + 1,
                   last_seen = excluded.last_seen""",
            (player_id, word, now),
        )


def miss_events_for(word, elapsed_seconds, wrong_attempts):
    """How many misses a solve is worth.

    Each wrong attempt counts once. Taking longer than roughly two seconds per
    letter adds one; longer than four seconds per letter adds two, on the
    assumption that a long pause means the speller was unsure.
    """
    events = wrong_attempts
    mild = len(word) * 2
    hard = len(word) * 4
    if elapsed_seconds > hard:
        events += 2
    elif elapsed_seconds > mild:
        events += 1
    return events


def record_word_result(player_id, word, elapsed_seconds, wrong_attempts):
    with connection() as conn:
        _bump_stats(
            conn, player_id, word, miss_events_for(word, elapsed_seconds, wrong_attempts)
        )


def record_word_skipped(player_id, word):
    with connection() as conn:
        _bump_stats(conn, player_id, word, SKIP_MISS_WEIGHT)


def get_challenge_words(player_id):
    """A player's words still being practised: missed at least once, not yet graduated."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT word, miss_count, consecutive_correct, last_seen
               FROM word_stats
               WHERE player_id = ? AND miss_count > 0 AND consecutive_correct < ?
               ORDER BY miss_count DESC, last_seen DESC""",
            (player_id, GRADUATION_STREAK),
        ).fetchall()
    return [dict(r) for r in rows]
