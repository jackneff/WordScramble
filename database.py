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

SCHEMA_VERSION = 2

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
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    round_size INTEGER NOT NULL,
    total_score INTEGER DEFAULT 0,
    words_completed INTEGER DEFAULT 0,
    hints_used INTEGER DEFAULT 0
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
    word TEXT PRIMARY KEY,
    miss_count INTEGER DEFAULT 0,
    consecutive_correct INTEGER DEFAULT 0,
    last_seen TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_round_words_round ON round_words(round_id);
CREATE INDEX IF NOT EXISTS idx_rounds_finished ON rounds(finished_at);
"""


def _column_names(conn, table):
    return {r["name"] for r in conn.execute("PRAGMA table_info(" + table + ")")}


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

        conn.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))


# --------------------------------------------------------------------------
# Rounds
# --------------------------------------------------------------------------

def create_round(round_size, words):
    """Create a round and its words. Returns the new round id."""
    with connection() as conn:
        cur = conn.execute("INSERT INTO rounds (round_size) VALUES (?)", (round_size,))
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


def get_history(limit=20):
    """Completed rounds, newest first, with the true best-possible score.

    `total_letters` is derived from the actual word lengths in each round, so
    history and the round summary always agree on the star rating.
    """
    with connection() as conn:
        rows = conn.execute(
            """SELECT r.id, r.started_at, r.finished_at, r.round_size,
                      r.total_score, r.hints_used, r.words_completed,
                      COALESCE(SUM(rw.word_length), 0) AS total_letters
               FROM rounds r
               LEFT JOIN round_words rw ON rw.round_id = r.id
               WHERE r.finished_at IS NOT NULL
               GROUP BY r.id
               ORDER BY r.started_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Word statistics ("challenge words")
# --------------------------------------------------------------------------

SKIP_MISS_WEIGHT = 3
GRADUATION_STREAK = 3


def _bump_stats(conn, word, miss_events):
    """Apply one result to a word's stats. Misses reset the correct streak."""
    now = _now()
    if miss_events > 0:
        conn.execute(
            """INSERT INTO word_stats (word, miss_count, consecutive_correct, last_seen)
               VALUES (?, ?, 0, ?)
               ON CONFLICT(word) DO UPDATE SET
                   miss_count = miss_count + excluded.miss_count,
                   consecutive_correct = 0,
                   last_seen = excluded.last_seen""",
            (word, miss_events, now),
        )
    else:
        conn.execute(
            """INSERT INTO word_stats (word, miss_count, consecutive_correct, last_seen)
               VALUES (?, 0, 1, ?)
               ON CONFLICT(word) DO UPDATE SET
                   consecutive_correct = consecutive_correct + 1,
                   last_seen = excluded.last_seen""",
            (word, now),
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


def record_word_result(word, elapsed_seconds, wrong_attempts):
    with connection() as conn:
        _bump_stats(conn, word, miss_events_for(word, elapsed_seconds, wrong_attempts))


def record_word_skipped(word):
    with connection() as conn:
        _bump_stats(conn, word, SKIP_MISS_WEIGHT)


def get_challenge_words():
    """Words still being practised: missed at least once, not yet graduated."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT word, miss_count, consecutive_correct, last_seen
               FROM word_stats
               WHERE miss_count > 0 AND consecutive_correct < ?
               ORDER BY miss_count DESC, last_seen DESC""",
            (GRADUATION_STREAK,),
        ).fetchall()
    return [dict(r) for r in rows]
