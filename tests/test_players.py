"""Player profiles: isolation between players, the picker, and the v3->v4
migration that attributes pre-profile history to a default profile.
"""
import sqlite3

import pytest

import database as db
from config import Config


# --- isolation: the actual concurrency fix ----------------------------------

def test_player_b_cannot_read_or_resume_player_as_round(make_client, player_id, other_player_id):
    client_a = make_client(player_id)
    round_id = client_a.post("/api/start", json={"round_size": 2}).get_json()["round_id"]
    round_word_id = db.get_round_words(round_id)[0]["id"]

    client_b = make_client(other_player_id)

    assert client_b.get(f"/game/{round_id}").status_code == 302
    assert client_b.get(f"/api/round/{round_id}").status_code == 404
    assert client_b.post(
        "/api/check", json={"round_word_id": round_word_id, "answer": "x"}
    ).status_code == 404
    assert client_b.post(
        "/api/skip", json={"round_word_id": round_word_id}
    ).status_code == 404
    assert client_b.post(
        "/api/hint", json={"round_word_id": round_word_id}
    ).status_code == 404

    # And A's round is untouched by any of B's attempts.
    assert db.get_round_word(round_word_id)["solved"] == 0


def test_player_a_can_still_play_their_own_round(make_client, player_id):
    client_a = make_client(player_id)
    round_id = client_a.post("/api/start", json={"round_size": 2}).get_json()["round_id"]

    assert client_a.get(f"/game/{round_id}").status_code == 200
    assert client_a.get(f"/api/round/{round_id}").status_code == 200


# --- the picker --------------------------------------------------------------

def test_creating_and_selecting_a_profile(client):
    res = client.post("/players", data={"name": "New Kid"})
    assert res.status_code == 302

    profile = db.get_player_by_name("New Kid")
    assert profile is not None

    res = client.get("/")
    assert res.status_code == 200


def test_a_duplicate_name_is_rejected(client, player_id):
    existing = db.get_player(player_id)
    res = client.post("/players", data={"name": existing["name"]})

    assert res.status_code == 302
    body = client.get("/players").get_data(as_text=True)
    assert "already exists" in body


def test_max_players_is_enforced(client, app):
    app.config["MAX_PLAYERS"] = 1  # one already exists from the `app` fixture
    res = client.post("/players", data={"name": "One Too Many"})

    assert res.status_code == 302
    assert db.get_player_by_name("One Too Many") is None


def test_deleting_a_profile_keeps_its_scores(client, player_id):
    round_id = db.create_round(1, ["cat"], player_id)

    res = client.post(f"/players/{player_id}/delete")

    assert res.status_code == 302
    assert db.get_player(player_id) is None
    assert db.get_round(round_id) is not None  # history survives


def test_deleting_the_active_profile_signs_it_out(client, player_id):
    client.post(f"/players/{player_id}/delete")

    # No active profile any more, so a game route bounces to the picker.
    assert client.get("/").status_code == 302


def test_picker_posts_need_a_csrf_token(raw_client):
    assert raw_client.post("/players", data={"name": "No Token"}).status_code == 400


# --- read-only parent dashboard ----------------------------------------------

def test_progress_view_never_changes_the_active_player(client, player_id, other_player_id):
    client.get(f"/progress/{other_player_id}")

    # Still logged in as the original player, not the one just viewed.
    res = client.get("/")
    assert res.status_code == 200
    with client.session_transaction() as session:
        assert session["player_id"] == player_id


def test_progress_view_does_not_disturb_an_in_progress_round(make_client, player_id, other_player_id):
    client_a = make_client(player_id)
    round_id = client_a.post("/api/start", json={"round_size": 2}).get_json()["round_id"]

    client_b = make_client(other_player_id)
    client_b.get("/progress")
    client_b.get(f"/progress/{player_id}")

    # A's round is still exactly where they left it.
    state = client_a.get(f"/api/round/{round_id}").get_json()
    assert state["words_completed"] == 0


# --- v3 -> v4 migration -------------------------------------------------------

_V3_SCHEMA = """
CREATE TABLE rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    round_size INTEGER NOT NULL,
    total_score INTEGER DEFAULT 0,
    words_completed INTEGER DEFAULT 0,
    hints_used INTEGER DEFAULT 0,
    word_list TEXT
);

CREATE TABLE round_words (
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

CREATE TABLE word_stats (
    word TEXT PRIMARY KEY,
    miss_count INTEGER DEFAULT 0,
    consecutive_correct INTEGER DEFAULT 0,
    last_seen TIMESTAMP
);
"""


@pytest.fixture
def v3_db(tmp_path):
    """A database file shaped exactly like a pre-profile install."""
    path = str(tmp_path / "v3.db")
    conn = sqlite3.connect(path)
    conn.executescript(_V3_SCHEMA)
    conn.execute(
        "INSERT INTO rounds (id, round_size, total_score, finished_at) VALUES (1, 2, 30, 'now')"
    )
    conn.execute(
        "INSERT INTO round_words (round_id, word, word_length, solved, score, word_order)"
        " VALUES (1, 'cat', 3, 1, 30, 1)"
    )
    conn.execute(
        "INSERT INTO word_stats (word, miss_count, consecutive_correct) VALUES ('cat', 2, 0)"
    )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    return path


def test_migration_attributes_existing_rows_to_one_default_profile(v3_db):
    db.configure(v3_db)
    try:
        db.init_db()

        profiles = db.list_players()
        assert len(profiles) == 1
        assert profiles[0]["name"] == Config.DEFAULT_PLAYER_NAME

        default_id = profiles[0]["id"]
        assert db.get_round(1)["player_id"] == default_id
        assert db.get_history(default_id) != []
        assert db.get_challenge_words(default_id)[0]["word"] == "cat"

        # Nothing was lost in the word_stats rebuild.
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM word_stats WHERE player_id = ? AND word = 'cat'", (default_id,)
            ).fetchone()
        assert row["miss_count"] == 2
    finally:
        db.configure(Config.DB_PATH)


def test_migration_is_idempotent(v3_db):
    db.configure(v3_db)
    try:
        db.init_db()
        db.init_db()  # running it again must not duplicate the default profile

        assert len(db.list_players()) == 1
    finally:
        db.configure(Config.DB_PATH)
