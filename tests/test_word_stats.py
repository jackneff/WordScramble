"""Challenge-word tracking: which words stay on the practice list."""
import database as db
import game


def _stats(player_id, word):
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM word_stats WHERE word = ? AND player_id = ?", (word, player_id)
        ).fetchone()
    return dict(row) if row else None


def test_a_fast_clean_solve_is_not_a_miss(app, player_id):
    db.record_word_result(player_id, "cat", elapsed_seconds=2, wrong_attempts=0)
    assert _stats(player_id, "cat")["miss_count"] == 0
    assert _stats(player_id, "cat")["consecutive_correct"] == 1


def test_wrong_attempts_count_as_misses(app, player_id):
    db.record_word_result(player_id, "cat", elapsed_seconds=1, wrong_attempts=2)
    assert _stats(player_id, "cat")["miss_count"] == 2


def test_a_slow_solve_counts_as_a_miss(app):
    # "cat" is 3 letters, so over 6s is mild and over 12s is hard.
    assert db.miss_events_for("cat", elapsed_seconds=2, wrong_attempts=0) == 0
    assert db.miss_events_for("cat", elapsed_seconds=7, wrong_attempts=0) == 1
    assert db.miss_events_for("cat", elapsed_seconds=20, wrong_attempts=0) == 2


def test_a_miss_resets_the_correct_streak(app, player_id):
    for _ in range(2):
        db.record_word_result(player_id, "cat", elapsed_seconds=1, wrong_attempts=0)
    assert _stats(player_id, "cat")["consecutive_correct"] == 2

    db.record_word_result(player_id, "cat", elapsed_seconds=1, wrong_attempts=1)
    assert _stats(player_id, "cat")["consecutive_correct"] == 0


def test_skipping_a_word_weighs_heavily(app, player_id):
    db.record_word_skipped(player_id, "cat")
    assert _stats(player_id, "cat")["miss_count"] == db.SKIP_MISS_WEIGHT


def test_missed_words_appear_on_the_challenge_list(app, player_id):
    db.record_word_result(player_id, "house", elapsed_seconds=1, wrong_attempts=1)
    assert [w["word"] for w in db.get_challenge_words(player_id)] == ["house"]


def test_a_word_graduates_after_three_clean_solves(app, player_id):
    db.record_word_result(player_id, "house", elapsed_seconds=1, wrong_attempts=1)
    for _ in range(db.GRADUATION_STREAK):
        db.record_word_result(player_id, "house", elapsed_seconds=1, wrong_attempts=0)
    assert db.get_challenge_words(player_id) == []


def test_challenge_words_are_ordered_by_miss_count(app, player_id):
    db.record_word_result(player_id, "house", elapsed_seconds=1, wrong_attempts=1)
    db.record_word_result(player_id, "garden", elapsed_seconds=1, wrong_attempts=5)
    assert [w["word"] for w in db.get_challenge_words(player_id)] == ["garden", "house"]


def test_a_challenge_round_prefers_practice_words(app, player_id):
    for word in ("house", "garden", "picture", "treasure", "morning"):
        db.record_word_skipped(player_id, word)

    chosen = game.choose_words(5, player_id, mode=game.CHALLENGE)

    assert sorted(chosen) == ["garden", "house", "morning", "picture", "treasure"]


def test_a_challenge_round_tops_up_when_practice_words_run_out(app, player_id):
    db.record_word_skipped(player_id, "house")

    chosen = game.choose_words(5, player_id, mode=game.CHALLENGE)

    assert len(chosen) == 5
    assert "house" in chosen


def test_word_stats_do_not_leak_between_players(app, player_id, other_player_id):
    db.record_word_result(player_id, "house", elapsed_seconds=1, wrong_attempts=3)

    assert [w["word"] for w in db.get_challenge_words(player_id)] == ["house"]
    assert db.get_challenge_words(other_player_id) == []
