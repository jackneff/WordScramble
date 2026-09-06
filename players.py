"""The active player profile.

Deliberately separate from auth.py: Cloudflare Access answers "who is allowed
in" and stays the only security boundary. This module only answers "which
profile is this browser currently playing as" - an attribution and isolation
mechanism *inside* that boundary, not a second one. Nothing here should ever
be asked to keep one family member out of another's data against their will.
"""
from flask import redirect, session, url_for

import database as db

SESSION_KEY = "player_id"


def current_player_id():
    """The active player's id, or None if nobody is picked yet or the
    profile has since been deleted."""
    player_id = session.get(SESSION_KEY)
    if player_id is None:
        return None
    if db.get_player(player_id) is None:
        clear_current_player()
        return None
    return player_id


def set_current_player(player_id):
    session[SESSION_KEY] = player_id


def clear_current_player():
    session.pop(SESSION_KEY, None)


def require_player():
    """None if a profile is active; otherwise a redirect to the picker.

    A route calls this first and returns its result if it isn't None, the
    same shape as auth.py's before_request checks.
    """
    if current_player_id() is not None:
        return None
    return redirect(url_for("players.picker"))


def register_context(app):
    """Make the active profile available to every template, for the nav bar."""
    @app.context_processor
    def inject_active_player():
        player_id = current_player_id()
        return {"active_player": db.get_player(player_id) if player_id else None}
