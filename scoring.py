"""Scoring and star-rating rules.

Kept in one module so the game page, the summary page and the history page
can never disagree about what a round was worth.
"""

POINTS_PER_LETTER = 10
HINT_PENALTY = 15

THREE_STAR_PCT = 80
TWO_STAR_PCT = 50


def word_score(word_length, hints_used):
    """Points earned for solving one word. Never negative."""
    return max(0, word_length * POINTS_PER_LETTER - hints_used * HINT_PENALTY)


def max_word_score(word_length):
    """Points a word is worth with no hints used."""
    return word_length * POINTS_PER_LETTER


def max_round_score(word_lengths):
    """Best possible total for a round made of these word lengths."""
    return sum(max_word_score(n) for n in word_lengths)


def score_pct(total_score, max_possible):
    if max_possible <= 0:
        return 0.0
    return total_score / max_possible * 100


def star_rating(pct):
    """1-3 stars from a percentage of the maximum possible score."""
    if pct >= THREE_STAR_PCT:
        return 3
    if pct >= TWO_STAR_PCT:
        return 2
    return 1
