"""Game rules: answers, hints, skips and round completion."""
import database as db
import game


def test_check_correct_answer_scores_and_solves(round_words):
    _, rows = round_words
    cat = rows[0]

    result = game.check_answer(cat["id"], "CAT")

    assert result == {"correct": True, "score": 30, "word": "CAT"}
    assert db.get_round_word(cat["id"])["solved"] == 1


def test_check_wrong_answer_records_an_attempt_and_scores_nothing(round_words):
    _, rows = round_words
    cat = rows[0]

    result = game.check_answer(cat["id"], "act")

    assert result["correct"] is False
    assert result["score"] == 0
    stored = db.get_round_word(cat["id"])
    assert stored["solved"] == 0
    assert stored["wrong_attempts"] == 1


def test_answers_are_case_and_whitespace_insensitive(round_words):
    _, rows = round_words
    assert game.check_answer(rows[0]["id"], "  CaT  ")["correct"] is True


def test_solving_the_same_word_twice_does_not_double_score(round_words):
    round_id, rows = round_words
    game.check_answer(rows[0]["id"], "cat")
    game.check_answer(rows[0]["id"], "cat")
    assert db.get_round(round_id)["total_score"] == 30


def test_hints_reduce_the_score(round_words):
    _, rows = round_words
    house = rows[1]

    game.reveal_hint(house["id"], filled_positions=[])
    result = game.check_answer(house["id"], "house")

    assert result["score"] == 50 - 15


def test_hint_reveals_the_leftmost_unfilled_letter(round_words):
    _, rows = round_words
    house = rows[1]

    # Position 0 is always given, so the first hint is position 1.
    assert game.reveal_hint(house["id"], []) == {"position": 1, "letter": "O"}

    filled = [{"position": 0, "letter": "H"}, {"position": 1, "letter": "O"}]
    assert game.reveal_hint(house["id"], filled) == {"position": 2, "letter": "U"}


def test_hint_on_a_fully_correct_word_reveals_nothing(round_words):
    _, rows = round_words
    filled = [{"position": i, "letter": c} for i, c in enumerate("HOUSE")]
    assert game.reveal_hint(rows[1]["id"], filled)["position"] == -1


def test_skip_solves_the_word_for_no_points(round_words):
    _, rows = round_words

    assert game.skip_word(rows[0]["id"]) == {"word": "CAT"}

    stored = db.get_round_word(rows[0]["id"])
    assert stored["solved"] == 1
    assert stored["score"] == 0


def test_round_finishes_once_every_word_is_solved(round_words):
    round_id, rows = round_words

    game.check_answer(rows[0]["id"], "cat")
    assert db.get_round(round_id)["finished_at"] is None

    game.check_answer(rows[1]["id"], "house")
    assert db.get_round(round_id)["finished_at"] is not None


def test_unknown_word_ids_return_none(app):
    assert game.check_answer(9999, "cat") is None
    assert game.skip_word(9999) is None
    assert game.reveal_hint(9999, []) is None


def test_round_state_does_not_leak_the_answer(round_words):
    round_id, _ = round_words

    state = game.get_round_state(round_id)

    for word in state["words"]:
        assert "word" not in word
        assert set(word) == {"id", "scrambled", "length", "first_letter",
                             "solved", "score", "hints_used"}


def test_summary_uses_real_word_lengths_for_stars(round_words):
    round_id, rows = round_words

    game.check_answer(rows[0]["id"], "cat")
    game.check_answer(rows[1]["id"], "house")

    summary = game.summarise_round(round_id)
    assert summary["pct"] == 100
    assert summary["stars"] == 3


def test_history_and_summary_agree_on_stars(round_words, player_id):
    """Regression: history used to assume 50 points per word regardless of length."""
    round_id, rows = round_words
    game.check_answer(rows[0]["id"], "cat")
    game.check_answer(rows[1]["id"], "house")

    import scoring
    entry = next(r for r in db.get_history(player_id) if r["id"] == round_id)
    history_stars = scoring.star_rating(
        scoring.score_pct(entry["total_score"],
                          entry["total_letters"] * scoring.POINTS_PER_LETTER)
    )

    assert history_stars == game.summarise_round(round_id)["stars"]
