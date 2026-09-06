import os
import sys

import pytest
from flask import Flask
from flask.testing import FlaskClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402
import security  # noqa: E402
from config import TestConfig  # noqa: E402

CSRF_TOKEN = "test-csrf-token"


class CsrfClient(FlaskClient):
    """Test client that carries a CSRF token, the way a real browser does.

    Every state-changing request needs one now. Without this, each existing
    POST test would grow boilerplate about something none of them are testing.
    The CSRF machinery itself is exercised directly in test_security.py, which
    uses `raw_client` to get a client without a token.
    """

    _seeded = False

    def open(self, *args, **kwargs):
        if not self._seeded:
            self._seeded = True
            with self.session_transaction() as session:
                session[security.SESSION_KEY] = CSRF_TOKEN

        headers = kwargs.setdefault("headers", {})
        if isinstance(headers, dict):
            headers.setdefault(security.HEADER_NAME, CSRF_TOKEN)
        return super().open(*args, **kwargs)


# Applies to ad-hoc clients built inside a test with create_app(...), not just
# to the `client` fixture.
Flask.test_client_class = CsrfClient


@pytest.fixture
def app(tmp_path):
    """A fresh app backed by a throwaway database file."""
    from app import create_app

    class Config(TestConfig):
        DB_PATH = str(tmp_path / "test.db")

    application = create_app(Config)
    yield application
    db.configure(TestConfig.DB_PATH)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def raw_client(app):
    """A client with no CSRF token, for testing the rejection path."""
    return FlaskClient(app, response_wrapper=app.response_class)


@pytest.fixture
def round_words(app):
    """Create a round and return (round_id, [round_word rows])."""
    round_id = db.create_round(2, ["cat", "house"])
    return round_id, db.get_round_words(round_id)
