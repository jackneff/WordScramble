"""Rendered pages."""
from collections import Counter

from flask import Blueprint, redirect, render_template, request, url_for

import database as db
import game
import players
import wordlists

bp = Blueprint("pages", __name__)

# A suffix shared by at least this many practice words is worth pointing out.
PATTERN_MIN_WORDS = 3
PATTERN_SUFFIX_LEN = 3


@bp.route("/")
def home():
    redirect_response = players.require_player()
    if redirect_response:
        return redirect_response

    lists = wordlists.available_lists()
    return render_template(
        "home.html",
        word_lists=lists,
        list_counts={entry["slug"]: entry["count"] for entry in lists},
    )


@bp.route("/game/<int:round_id>")
def play(round_id):
    redirect_response = players.require_player()
    if redirect_response:
        return redirect_response

    if not game.player_owns_round(players.current_player_id(), round_id):
        return redirect(url_for("pages.home"))
    return render_template("game.html", round_id=round_id)


@bp.route("/summary/<int:round_id>")
def summary(round_id):
    redirect_response = players.require_player()
    if redirect_response:
        return redirect_response

    if not game.player_owns_round(players.current_player_id(), round_id):
        return redirect(url_for("pages.home"))

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
    redirect_response = players.require_player()
    if redirect_response:
        return redirect_response

    words = db.get_challenge_words(players.current_player_id())
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
    redirect_response = players.require_player()
    if redirect_response:
        return redirect_response

    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    player_id = players.current_player_id()
    return render_template(
        "history.html",
        stats=game.lifetime_stats(player_id),
        **game.history_page(player_id, page),
    )


@bp.route("/progress")
def progress():
    """Read-only summary of every profile. Never touches the active player."""
    cards = []
    for profile in db.list_players():
        stats = game.lifetime_stats(profile["id"])
        recent = db.get_history(profile["id"], limit=1)
        last_played = recent[0]["started_at"] if recent else None
        cards.append({"player": profile, "stats": stats, "last_played": last_played})
    return render_template("progress.html", cards=cards)


@bp.route("/progress/<int:player_id>")
def progress_detail(player_id):
    """One player's history and challenge words, read-only.

    This never calls players.set_current_player - looking at someone's
    progress must never resume or interrupt their in-progress round.
    """
    profile = db.get_player(player_id)
    if not profile:
        return redirect(url_for("pages.progress"))

    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    return render_template(
        "progress_detail.html",
        profile=profile,
        stats=game.lifetime_stats(player_id),
        words=db.get_challenge_words(player_id),
        graduation_streak=db.GRADUATION_STREAK,
        **game.history_page(player_id, page),
    )
