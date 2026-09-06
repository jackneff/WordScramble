"""The "who's playing?" profile picker.

No passwords: Cloudflare Access already decided who is allowed to reach this
app at all. Profiles just keep the people it lets in from playing on top of
each other. See players.py for the session-scoped active-profile helpers.
"""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)

import database as db
import players

bp = Blueprint("players", __name__, url_prefix="/players")

MAX_NAME_LENGTH = 20


def _clean_name(raw):
    name = (raw or "").strip()
    return name[:MAX_NAME_LENGTH] if name else ""


@bp.get("")
def picker():
    return render_template("players.html", profiles=db.list_players())


@bp.post("/select")
def select():
    try:
        player_id = int(request.form.get("player_id"))
    except (TypeError, ValueError):
        return redirect(url_for("players.picker"))

    if db.get_player(player_id) is None:
        flash("That profile no longer exists.", "error")
        return redirect(url_for("players.picker"))

    players.set_current_player(player_id)
    return redirect(url_for("pages.home"))


@bp.post("")
def create():
    name = _clean_name(request.form.get("name"))
    if not name:
        flash("Give the profile a name.", "error")
        return redirect(url_for("players.picker"))

    if len(db.list_players()) >= current_app.config["MAX_PLAYERS"]:
        flash("That's as many profiles as this game supports.", "error")
        return redirect(url_for("players.picker"))

    player_id = db.create_player(name)
    if player_id is None:
        flash("A profile with that name already exists.", "error")
        return redirect(url_for("players.picker"))

    players.set_current_player(player_id)
    return redirect(url_for("pages.home"))


@bp.post("/<int:player_id>/delete")
def delete(player_id):
    db.delete_player(player_id)
    if players.current_player_id() == player_id:
        players.clear_current_player()
    flash("Profile deleted. Their scores are kept.", "success")
    return redirect(url_for("players.picker"))
