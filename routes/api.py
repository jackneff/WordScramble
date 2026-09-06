"""JSON API consumed by the game page."""
from flask import Blueprint, current_app, jsonify, request

import game
import players

bp = Blueprint("api", __name__, url_prefix="/api")


def _not_found(what):
    return jsonify({"error": what + " not found"}), 404


def _no_player():
    return jsonify({"error": "No active profile"}), 400


def _payload():
    return request.get_json(silent=True) or {}


def _round_word_id(data):
    """Pull a positive integer round_word_id out of a request body."""
    try:
        value = int(data.get("round_word_id"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@bp.post("/start")
def start():
    player_id = players.current_player_id()
    if player_id is None:
        return _no_player()

    data = _payload()
    sizes = current_app.config["ROUND_SIZES"]
    try:
        round_size = int(data.get("round_size"))
    except (TypeError, ValueError):
        round_size = current_app.config["DEFAULT_ROUND_SIZE"]
    if round_size not in sizes:
        round_size = current_app.config["DEFAULT_ROUND_SIZE"]

    mode = data.get("mode", game.NORMAL)
    if mode not in (game.NORMAL, game.CHALLENGE):
        mode = game.NORMAL

    word_list = data.get("word_list") or None

    round_id, words = game.start_round(round_size, player_id, mode, word_list)
    if round_id is None:
        return jsonify({"error": "That word list is no longer available"}), 404
    return jsonify({"round_id": round_id, "words": words})


@bp.get("/round/<int:round_id>")
def round_state(round_id):
    player_id = players.current_player_id()
    if player_id is None or not game.player_owns_round(player_id, round_id):
        return _not_found("Round")
    state = game.get_round_state(round_id)
    if not state:
        return _not_found("Round")
    return jsonify(state)


@bp.post("/check")
def check():
    data = _payload()
    round_word_id = _round_word_id(data)
    player_id = players.current_player_id()
    if round_word_id is None or player_id is None:
        return _not_found("Word")
    if not game.player_owns_round_word(player_id, round_word_id):
        return _not_found("Word")

    try:
        elapsed = max(0.0, float(data.get("elapsed_seconds", 0)))
    except (TypeError, ValueError):
        elapsed = 0.0

    result = game.check_answer(round_word_id, data.get("answer", ""), elapsed)
    if result is None:
        return _not_found("Word")
    return jsonify(result)


@bp.post("/skip")
def skip():
    round_word_id = _round_word_id(_payload())
    player_id = players.current_player_id()
    if round_word_id is None or player_id is None:
        return _not_found("Word")
    if not game.player_owns_round_word(player_id, round_word_id):
        return _not_found("Word")

    result = game.skip_word(round_word_id)
    if result is None:
        return _not_found("Word")
    return jsonify(result)


@bp.post("/hint")
def hint():
    data = _payload()
    round_word_id = _round_word_id(data)
    player_id = players.current_player_id()
    if round_word_id is None or player_id is None:
        return _not_found("Word")
    if not game.player_owns_round_word(player_id, round_word_id):
        return _not_found("Word")

    filled = data.get("filled_positions") or []
    if not isinstance(filled, list):
        filled = []

    result = game.reveal_hint(round_word_id, filled)
    if result is None:
        return _not_found("Word")
    return jsonify(result)
