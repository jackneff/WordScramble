"""Scoring and star thresholds."""
import scoring


def test_score_is_ten_points_per_letter():
    assert scoring.word_score(5, hints_used=0) == 50


def test_each_hint_costs_fifteen_points():
    assert scoring.word_score(5, hints_used=1) == 35
    assert scoring.word_score(5, hints_used=2) == 20


def test_score_never_goes_negative():
    assert scoring.word_score(3, hints_used=10) == 0


def test_max_round_score_sums_word_lengths():
    assert scoring.max_round_score([3, 5, 8]) == 160


def test_star_thresholds():
    assert scoring.star_rating(100) == 3
    assert scoring.star_rating(80) == 3
    assert scoring.star_rating(79.9) == 2
    assert scoring.star_rating(50) == 2
    assert scoring.star_rating(49.9) == 1
    assert scoring.star_rating(0) == 1


def test_score_pct_handles_an_empty_round():
    assert scoring.score_pct(0, 0) == 0
