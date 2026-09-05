"""HTTP layer: pages render, the API validates its input, the PIN gate works."""
import pytest

import database as db
from app import create_app
from config import TestConfig


def test_pages_render(client):
    for path in ("/", "/history", "/challenge"):
        assert client.get(path).status_code == 200


def test_start_returns_a_playable_round(client):
    res = client.post("/api/start", json={"round_size": 5})

    assert res.status_code == 200
    body = res.get_json()
    assert len(body["words"]) == 5
    for word in body["words"]:
        assert word["scrambled"]
        assert word["first_letter"].isupper()


def test_start_rejects_an_unsupported_round_size(client):
    body = client.post("/api/start", json={"round_size": 500}).get_json()
    assert len(body["words"]) == TestConfig.DEFAULT_ROUND_SIZE


def test_start_survives_junk_input(client):
    for payload in ({}, {"round_size": "many"}, {"round_size": None}):
        assert client.post("/api/start", json=payload).status_code == 200


def test_an_unknown_round_redirects_home(client):
    assert client.get("/game/9999").status_code == 302
    assert client.get("/summary/9999").status_code == 302


def test_api_rejects_unknown_and_malformed_word_ids(client):
    for payload in ({"round_word_id": 9999}, {"round_word_id": "abc"}, {}):
        assert client.post("/api/check", json=payload).status_code == 404
        assert client.post("/api/skip", json=payload).status_code == 404
        assert client.post("/api/hint", json=payload).status_code == 404


def test_playing_a_round_end_to_end(client, app):
    round_id = client.post("/api/start", json={"round_size": 5}).get_json()["round_id"]

    for row in db.get_round_words(round_id):
        res = client.post("/api/check", json={
            "round_word_id": row["id"],
            "answer": row["word"],
            "elapsed_seconds": 1,
        })
        assert res.get_json()["correct"] is True

    assert db.get_round(round_id)["finished_at"] is not None
    assert client.get(f"/summary/{round_id}").status_code == 200
    assert len(db.get_history()) == 1


# --- optional PIN gate ----------------------------------------------------

@pytest.fixture
def locked_client(tmp_path):
    class Locked(TestConfig):
        DB_PATH = str(tmp_path / "locked.db")
        ACCESS_PIN = "1234"

    return create_app(Locked).test_client()


def test_pin_gate_redirects_pages_and_401s_the_api(locked_client):
    assert locked_client.get("/").status_code == 302
    assert locked_client.post("/api/start", json={}).status_code == 401


def test_the_right_pin_unlocks_the_app(locked_client):
    assert locked_client.post("/login", data={"pin": "1234"}).status_code == 302
    assert locked_client.get("/").status_code == 200


def test_the_wrong_pin_does_not(locked_client):
    assert locked_client.post("/login", data={"pin": "0000"}).status_code == 401
    assert locked_client.get("/").status_code == 302
