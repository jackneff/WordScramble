import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db  # noqa: E402
from app import create_app  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture
def app(tmp_path):
    """A fresh app backed by a throwaway database file."""

    class Config(TestConfig):
        DB_PATH = str(tmp_path / "test.db")

    application = create_app(Config)
    yield application
    db.configure(TestConfig.DB_PATH)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def round_words(app):
    """Create a round and return (round_id, [round_word rows])."""
    round_id = db.create_round(2, ["cat", "house"])
    return round_id, db.get_round_words(round_id)
