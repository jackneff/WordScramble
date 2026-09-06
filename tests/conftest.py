import os
import sys

import pytest
from flask import Flask
from flask.testing import FlaskClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402
import players  # noqa: E402
import security  # noqa: E402
from config import TestConfig  # noqa: E402

CSRF_TOKEN = "test-csrf-token"


class CsrfClient(FlaskClient):
    """Test client that carries a CSRF token and an active profile, the way a
    real browser does once someone has picked one.

    Every state-changing request needs a CSRF token now, and every game route
    needs an active player. Without this, each existing test would grow
    boilerplate about something none of them are testing. The CSRF machinery
    itself is exercised directly in test_security.py, which uses `raw_client`
    to get a client without a token; the picker itself is exercised in
    test_players.py using `make_client` to log in as a specific profile.
    """

    _seeded = False

    def open(self, *args, **kwargs):
        if not self._seeded:
            self._seeded = True
            with self.session_transaction() as session:
                session[security.SESSION_KEY] = CSRF_TOKEN
                player_id = self.application.config.get("TEST_PLAYER_ID")
                if player_id is not None:
                    session[players.SESSION_KEY] = player_id

        headers = kwargs.setdefault("headers", {})
        if isinstance(headers, dict):
            headers.setdefault(security.HEADER_NAME, CSRF_TOKEN)
        return super().open(*args, **kwargs)


# Applies to ad-hoc clients built inside a test with create_app(...), not just
# to the `client` fixture.
Flask.test_client_class = CsrfClient


@pytest.fixture
def app(tmp_path):
    """A fresh app backed by a throwaway database file, with one profile."""
    from app import create_app

    class Config(TestConfig):
        DB_PATH = str(tmp_path / "test.db")

    application = create_app(Config)
    application.config["TEST_PLAYER_ID"] = db.create_player("Test Player")
    yield application
    db.configure(TestConfig.DB_PATH)


@pytest.fixture
def player_id(app):
    """The default profile `client` is logged in as."""
    return app.config["TEST_PLAYER_ID"]


@pytest.fixture
def other_player_id(app):
    """A second profile, for tests that check players stay isolated."""
    return db.create_player("Other Player")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_client(app):
    """Build a client already signed in as a specific profile."""
    def _make(as_player_id):
        client = app.test_client()
        with client.session_transaction() as session:
            session[security.SESSION_KEY] = CSRF_TOKEN
            session[players.SESSION_KEY] = as_player_id
        client._seeded = True
        return client
    return _make


@pytest.fixture
def raw_client(app):
    """A client with no CSRF token, for testing the rejection path.

    It still has an active profile - CSRF is what this client is testing the
    absence of, not the player picker.
    """
    client = FlaskClient(app, response_wrapper=app.response_class)
    with client.session_transaction() as session:
        session[players.SESSION_KEY] = app.config["TEST_PLAYER_ID"]
    return client


@pytest.fixture
def round_words(app):
    """Create a round for the default profile and return (round_id, [round_word rows])."""
    round_id = db.create_round(2, ["cat", "house"], app.config["TEST_PLAYER_ID"])
    return round_id, db.get_round_words(round_id)
