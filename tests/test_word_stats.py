"""Challenge-word tracking: which words stay on the practice list."""
import database as db
import game


def _stats(word):
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM word_stats WHERE word = ?", (word,)
        ).fetchone()
    return dict(row) if row else None


def test_a_fast_clean_solve_is_not_a_miss(app):
    db.record_word_result("cat", elapsed_seconds=2, wrong_attempts=0)
    assert _stats("cat")["miss_count"] == 0
    assert _stats("cat")["consecutive_correct"] == 1


def test_wrong_attempts_count_as_misses(app):
    db.record_word_result("cat", elapsed_seconds=1, wrong_attempts=2)
    assert _stats("cat")["miss_count"] == 2


def test_a_slow_solve_counts_as_a_miss(app):
    # "cat" is 3 letters, so over 6s is mild and over 12s is hard.
    assert db.miss_events_for("cat", elapsed_seconds=2, wrong_attempts=0) == 0
    assert db.miss_events_for("cat", elapsed_seconds=7, wrong_attempts=0) == 1
    assert db.miss_events_for("cat", elapsed_seconds=20, wrong_attempts=0) == 2


def test_a_miss_resets_the_correct_streak(app):
    for _ in range(2):
        db.record_word_result("cat", elapsed_seconds=1, wrong_attempts=0)
    assert _stats("cat")["consecutive_correct"] == 2

    db.record_word_result("cat", elapsed_seconds=1, wrong_attempts=1)
    assert _stats("cat")["consecutive_correct"] == 0


def test_skipping_a_word_weighs_heavily(app):
    db.record_word_skipped("cat")
    assert _stats("cat")["miss_count"] == db.SKIP_MISS_WEIGHT


def test_missed_words_appear_on_the_challenge_list(app):
    db.record_word_result("house", elapsed_seconds=1, wrong_attempts=1)
    assert [w["word"] for w in db.get_challenge_words()] == ["house"]


def test_a_word_graduates_after_three_clean_solves(app):
    db.record_word_result("house", elapsed_seconds=1, wrong_attempts=1)
    for _ in range(db.GRADUATION_STREAK):
        db.record_word_result("house", elapsed_seconds=1, wrong_attempts=0)
    assert db.get_challenge_words() == []


def test_challenge_words_are_ordered_by_miss_count(app):
    db.record_word_result("house", elapsed_seconds=1, wrong_attempts=1)
    db.record_word_result("garden", elapsed_seconds=1, wrong_attempts=5)
    assert [w["word"] for w in db.get_challenge_words()] == ["garden", "house"]


def test_a_challenge_round_prefers_practice_words(app):
    for word in ("house", "garden", "picture", "treasure", "morning"):
        db.record_word_skipped(word)

    chosen = game.choose_words(5, mode=game.CHALLENGE)

    assert sorted(chosen) == ["garden", "house", "morning", "picture", "treasure"]


def test_a_challenge_round_tops_up_when_practice_words_run_out(app):
    db.record_word_skipped("house")

    chosen = game.choose_words(5, mode=game.CHALLENGE)

    assert len(chosen) == 5
    assert "house" in chosen
