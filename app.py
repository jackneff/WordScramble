"""Application factory.

Run locally with `python app.py`; serve in production through `wsgi.py`.
"""
import os

from flask import Flask, flash, redirect, url_for

import auth
import database as db
import security
from config import AUTH_CLOUDFLARE, DEV_SECRET_KEY, Config
from routes import api_bp, lists_bp, pages_bp


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    _check_deployment(app)

    db.configure(app.config["DB_PATH"])
    db.init_db()

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(lists_bp)

    # Order matters: before_request hooks run in registration order, so an
    # unauthenticated request should be turned away as unauthenticated rather
    # than told its CSRF token is missing.
    auth.register_guard(app)
    security.register_csrf(app)
    _register_error_handlers(app)

    return app


def _check_deployment(app):
    """Refuse to start in a configuration that looks deployed but unprotected.

    Every one of these used to be a silent downgrade - the app would come up
    happily with a published signing key or with no authentication at all. A
    misconfigured deployment should fail loudly at boot instead.
    """
    exposed = app.config["SESSION_COOKIE_SECURE"]
    cloudflare = app.config["AUTH_MODE"] == AUTH_CLOUDFLARE

    if app.config["SECRET_KEY"] == DEV_SECRET_KEY and (exposed or cloudflare):
        raise RuntimeError(
            "SECRET_KEY is still the development default. Set it in .env:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
        )

    if cloudflare:
        missing = [
            name
            for name in ("CF_ACCESS_TEAM", "CF_ACCESS_AUD")
            if not app.config.get(name)
        ]
        if missing:
            raise RuntimeError(
                "AUTH_MODE=cloudflare requires {}. Find them in the Cloudflare "
                "Zero Trust dashboard under Access > Applications.".format(
                    " and ".join(missing)
                )
            )
    elif exposed:
        raise RuntimeError(
            "SESSION_COOKIE_SECURE is on but AUTH_MODE is 'none', which would "
            "publish the app with no authentication. Set AUTH_MODE=cloudflare."
        )


def _register_error_handlers(app):
    @app.errorhandler(413)
    def too_large(_error):
        """An oversized upload should read as a friendly message, not a crash."""
        flash("That file is too big for a word list.", "error")
        return redirect(url_for("lists.manage")), 302


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config["DEBUG"],
    )
