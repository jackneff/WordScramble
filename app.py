"""Application factory.

Run locally with `python app.py`; serve in production through `wsgi.py`.
"""
import os
from datetime import timedelta

from flask import Flask

import auth
import database as db
from config import Config
from routes import api_bp, pages_bp


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.permanent_session_lifetime = timedelta(days=30)

    db.configure(app.config["DB_PATH"])
    db.init_db()

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth.bp)
    auth.register_guard(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config["DEBUG"],
    )
