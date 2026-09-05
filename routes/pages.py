"""Rendered pages."""
from collections import Counter

from flask import Blueprint, redirect, render_template, request, url_for

import database as db
import game

bp = Blueprint("pages", __name__)

# A suffix shared by at least this many practice words is worth pointing out.
PATTERN_MIN_WORDS = 3
PATTERN_SUFFIX_LEN = 3


@bp.route("/")
def home():
    return render_template("home.html")


@bp.route("/game/<int:round_id>")
def play(round_id):
    if not db.get_round(round_id):
        return redirect(url_for("pages.home"))
    return render_template("game.html", round_id=round_id)


@bp.route("/summary/<int:round_id>")
def summary(round_id):
    result = game.summarise_round(round_id)
    if not result:
        return redirect(url_for("pages.home"))
    return render_template(
        "summary.html",
        rnd=result["round"],
        words=result["words"],
        stars=result["stars"],
        pct=result["pct"],
    )


@bp.route("/challenge")
def challenge():
    words = db.get_challenge_words()
    suffixes = Counter(
        w["word"][-PATTERN_SUFFIX_LEN:]
        for w in words
        if len(w["word"]) >= PATTERN_SUFFIX_LEN
    )
    patterns = {s: n for s, n in suffixes.items() if n >= PATTERN_MIN_WORDS}
    return render_template(
        "challenge.html",
        words=words,
        patterns=patterns,
        graduation_streak=db.GRADUATION_STREAK,
    )


@bp.route("/history")
def history():
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    return render_template(
        "history.html",
        stats=game.lifetime_stats(),
        **game.history_page(page),
    )
