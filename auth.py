"""Optional shared-PIN gate.

The app is intended for one family, so it does not carry user accounts. When
ACCESS_PIN is set, every page and API call requires a session cookie obtained
by entering that PIN once. When it is unset the app is open, which is the
right default for local development.
"""
import hmac

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request,
    session, url_for,
)

bp = Blueprint("auth", __name__)

SESSION_KEY = "authenticated"


def _pin():
    return current_app.config.get("ACCESS_PIN")


def is_unlocked():
    return not _pin() or session.get(SESSION_KEY) is True


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not _pin():
        return redirect(url_for("pages.home"))
    if is_unlocked():
        return redirect(url_for("pages.home"))

    error = None
    if request.method == "POST":
        submitted = (request.form.get("pin") or "").strip()
        if hmac.compare_digest(submitted, _pin()):
            session[SESSION_KEY] = True
            session.permanent = True
            return redirect(url_for("pages.home"))
        error = "That is not the right PIN."

    return render_template("login.html", error=error), (401 if error else 200)


@bp.post("/logout")
def logout():
    session.pop(SESSION_KEY, None)
    return redirect(url_for("auth.login"))


def register_guard(app):
    """Refuse every request outside the login flow until the PIN is entered."""
    exempt = {"auth.login", "auth.logout", "static"}

    @app.before_request
    def require_pin():
        if is_unlocked() or request.endpoint in exempt:
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("auth.login"))
