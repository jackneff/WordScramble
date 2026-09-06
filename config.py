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

# Named so the startup checks in app.py can recognise it, rather than repeating
# the literal in three places.
DEV_SECRET_KEY = "dev-only-not-for-production"

# Authentication modes. "none" leaves the app open, which is what local
# development wants; "cloudflare" requires a signed Cloudflare Access assertion
# on every request. See auth.py.
AUTH_NONE = "none"
AUTH_CLOUDFLARE = "cloudflare"


def _bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
    DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "wordscramble.db"))
    WORDS_DIR = os.environ.get("WORDS_DIR", os.path.join(BASE_DIR, "static", "words"))

    # Parent-supplied vocabulary lists ("this week's spelling words"). Any .txt
    # file dropped here becomes a playable list, no restart needed.
    LISTS_DIR = os.environ.get(
        "LISTS_DIR", os.path.join(BASE_DIR, "static", "words", "lists")
    )
    DEBUG = _bool("FLASK_DEBUG", False)

    # Who is allowed in. Unset means nobody is asked, which is the right default
    # for a laptop and a refused startup in production (see app.py).
    AUTH_MODE = (os.environ.get("AUTH_MODE") or AUTH_NONE).strip().lower()

    # Cloudflare Access team name (the <team> in <team>.cloudflareaccess.com)
    # and the Application Audience tag of this specific app. Both required when
    # AUTH_MODE=cloudflare; the audience check is what stops a token issued for
    # another app in the same team from working here.
    CF_ACCESS_TEAM = os.environ.get("CF_ACCESS_TEAM") or None
    CF_ACCESS_AUD = os.environ.get("CF_ACCESS_AUD") or None

    # Round configuration
    ROUND_SIZES = (5, 10, 15)
    DEFAULT_ROUND_SIZE = 10

    # A word list is a small text file; anything larger is a mistake or an
    # attack. Flask turns an oversized body into a 413 before we read it.
    MAX_CONTENT_LENGTH = 256 * 1024

    # Session cookie hardening. Sessions now carry only flash messages -
    # Cloudflare Access holds the identity - but they are still signed with
    # SECRET_KEY, so the key still has to be a real one in production.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test"
    AUTH_MODE = AUTH_NONE
