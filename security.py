"""CSRF protection for state-changing requests.

Cloudflare Access authenticates the *person*, not the *request*: once a family
member is signed in, their browser attaches the Cloudflare cookie to any request
it makes to this site, including one triggered by a form on somebody else's
page. So the two endpoints that write and delete files - and the API the game
posts to - still need a token that only our own pages know.

Flask-WTF would do this, but it is a large dependency for three forms and one
fetch helper. This module is the same idea in one screen of code.
"""
import hmac
import secrets

from flask import jsonify, request, session

FIELD_NAME = "csrf_token"
HEADER_NAME = "X-CSRF-Token"
SESSION_KEY = "csrf_token"

# GET/HEAD/OPTIONS/TRACE are expected to be side-effect free, so they are not
# worth a token. Everything else is.
PROTECTED_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def token():
    """The session's CSRF token, minted on first use."""
    existing = session.get(SESSION_KEY)
    if not existing:
        existing = secrets.token_urlsafe(32)
        session[SESSION_KEY] = existing
    return existing


def _submitted():
    return request.form.get(FIELD_NAME) or request.headers.get(HEADER_NAME) or ""


def _valid():
    expected = session.get(SESSION_KEY)
    if not expected:
        return False
    # compare_digest wants bytes: on str it raises for any non-ASCII input,
    # which would turn a junk submission into a 500.
    return hmac.compare_digest(
        _submitted().encode("utf-8"), expected.encode("utf-8")
    )


def register_csrf(app):
    @app.before_request
    def check_csrf():
        if request.method not in PROTECTED_METHODS or _valid():
            return None

        app.logger.warning(
            "Rejected %s %s: bad or missing CSRF token", request.method, request.path
        )
        if request.path.startswith("/api/"):
            return jsonify({"error": "Invalid CSRF token"}), 400
        return "Invalid CSRF token. Please reload the page and try again.", 400

    @app.context_processor
    def inject_token():
        return {"csrf_token": token}
