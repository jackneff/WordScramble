"""Application configuration, driven by environment variables.

Defaults are safe for local development; production overrides everything
through the environment (see .env.example).
"""
import os

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional; the environment can be set directly
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-production")
    DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "wordscramble.db"))
    WORDS_DIR = os.environ.get("WORDS_DIR", os.path.join(BASE_DIR, "static", "words"))

    # Parent-supplied vocabulary lists ("this week's spelling words"). Any .txt
    # file dropped here becomes a playable list, no restart needed.
    LISTS_DIR = os.environ.get(
        "LISTS_DIR", os.path.join(BASE_DIR, "static", "words", "lists")
    )
    DEBUG = _bool("FLASK_DEBUG", False)

    # Optional shared-PIN gate. Unset (the default) leaves the app open.
    ACCESS_PIN = os.environ.get("ACCESS_PIN") or None

    # Round configuration
    ROUND_SIZES = (5, 10, 15)
    DEFAULT_ROUND_SIZE = 10


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test"
    ACCESS_PIN = None
