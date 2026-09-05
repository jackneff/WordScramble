"""Game rules.

This module owns what happens during a round. It sits between the HTTP layer
and the database so the rules can be exercised without a request context.
"""
import random

import database as db
import scoring
from words import pick_words, scramble

NORMAL = "normal"
CHALLENGE = "challenge"


def _presented(row, include_progress=False):
    """Shape one round word for the client, never leaking the full answer."""
    word = row["word"]
    payload = {
        "id": row["id"],
        "scrambled": scramble(word),
        "length": row["word_length"],
        "first_letter": word[0].upper(),
    }
    if include_progress:
        payload.update(
            solved=bool(row["solved"]),
            score=row["score"],
            hints_used=row["hints_used"],
        )
    return payload


def choose_words(round_size, mode=NORMAL):
    """Pick the words for a new round.

    A challenge round is drawn from the practice list first and topped up with
    ordinary words when there are not enough of them yet.
    """
    if mode != CHALLENGE:
        return pick_words(round_size)

    challenge = [row["word"] for row in db.get_challenge_words()]
    if len(challenge) >= round_size:
        return random.sample(challenge, round_size)

    words = challenge + pick_words(round_size - len(challenge))
    random.shuffle(words)
    return words


def start_round(round_size, mode=NORMAL):
    """Create a round and return its id plus the words to display."""
    words = choose_words(round_size, mode)
    round_id = db.create_round(len(words), words)
    return round_id, [_presented(rw) for rw in db.get_round_words(round_id)]


def get_round_state(round_id):
    """Everything the game page needs to resume a round, or None if unknown."""
    rnd = db.get_round(round_id)
    if not rnd:
        return None
    return {
        "round_id": round_id,
        "round_size": rnd["round_size"],
        "total_score": rnd["total_score"],
        "words_completed": rnd["words_completed"],
        "words": [_presented(rw, include_progress=True) for rw in db.get_round_words(round_id)],
    }


def _finish_if_complete(round_id):
    if all(w["solved"] for w in db.get_round_words(round_id)):
        db.finish_round(round_id)


def check_answer(round_word_id, answer, elapsed_seconds=0):
    """Score an attempt. Returns None if the word id is unknown."""
    rw = db.get_round_word(round_word_id)
    if not rw:
        return None

    correct = answer.lower().strip() == rw["word"]
    score = 0

    if correct and not rw["solved"]:
        score = scoring.word_score(rw["word_length"], rw["hints_used"])
        db.solve_word(round_word_id, score)
        rw = db.get_round_word(round_word_id)
        db.record_word_result(rw["word"], elapsed_seconds, rw["wrong_attempts"])
        _finish_if_complete(rw["round_id"])
    elif not correct and not rw["solved"]:
        db.increment_wrong_attempts(round_word_id)

    return {"correct": correct, "score": score, "word": rw["word"].upper()}


def skip_word(round_word_id):
    """Give up on a word: it counts as solved for zero points."""
    rw = db.get_round_word(round_word_id)
    if not rw:
        return None
    if not rw["solved"]:
        db.solve_word(round_word_id, 0)
        db.record_word_skipped(rw["word"])
        _finish_if_complete(rw["round_id"])
    return {"word": rw["word"].upper()}


def reveal_hint(round_word_id, filled_positions):
    """Reveal the leftmost letter that is not already correctly placed.

    Position 0 is skipped because the first letter is always given. Returns
    position -1 when every letter is already correct.
    """
    rw = db.get_round_word(round_word_id)
    if not rw:
        return None

    word = rw["word"].upper()
    filled = {f.get("position"): f.get("letter") for f in filled_positions}
    for i in range(1, len(word)):
        if filled.get(i) != word[i]:
            db.add_hint(round_word_id)
            return {"position": i, "letter": word[i]}
    return {"position": -1, "letter": ""}


ROUNDS_PER_PAGE = 20


def _stars_for(total_score, total_letters):
    max_possible = total_letters * scoring.POINTS_PER_LETTER
    return scoring.star_rating(scoring.score_pct(total_score, max_possible))


def lifetime_stats():
    """Totals across every finished round, independent of the page shown.

    The best round is found across the whole history rather than the current
    page, so the badge stays correct once older rounds scroll off.
    """
    rows = db.get_round_scores()
    if not rows:
        return {"rounds_played": 0, "best_score": 0, "best_id": None, "avg_stars": 0}

    best = max(rows, key=lambda r: r["total_score"])
    stars = [_stars_for(r["total_score"], r["total_letters"]) for r in rows]
    return {
        "rounds_played": len(rows),
        "best_score": best["total_score"],
        "best_id": best["id"],
        "avg_stars": round(sum(stars) / len(stars), 1),
    }


def history_page(page=1, per_page=ROUNDS_PER_PAGE):
    """One page of history, with star ratings and pagination metadata."""
    total = db.count_finished_rounds()
    total_pages = max(1, -(-total // per_page))  # ceiling division
    page = max(1, min(page, total_pages))

    rounds = db.get_history(limit=per_page, offset=(page - 1) * per_page)
    for r in rounds:
        max_possible = r["total_letters"] * scoring.POINTS_PER_LETTER
        pct = scoring.score_pct(r["total_score"], max_possible)
        r["stars"] = scoring.star_rating(pct)
        r["pct"] = round(pct)

    return {
        "rounds": rounds,
        "page": page,
        "total_pages": total_pages,
        "total_rounds": total,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }


def summarise_round(round_id):
    """Score summary for a finished round, or None if the round is unknown."""
    rnd = db.get_round(round_id)
    if not rnd:
        return None
    words = db.get_round_words(round_id)
    max_possible = scoring.max_round_score(w["word_length"] for w in words)
    pct = scoring.score_pct(rnd["total_score"], max_possible)
    return {
        "round": rnd,
        "words": words,
        "pct": pct,
        "stars": scoring.star_rating(pct),
    }
