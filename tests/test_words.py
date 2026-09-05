"""Word selection and scrambling."""
import pytest

import words


@pytest.fixture
def pools():
    return {
        3: ["cat", "dog", "sun", "bed", "pig"],
        4: ["tree", "fish", "moon", "cake", "bird"],
        5: ["house", "plant", "green", "smile", "chair"],
        6: ["garden", "yellow", "friend", "castle", "orange"],
        7: ["picture", "morning", "kitchen", "blanket", "monster"],
        8: ["treasure", "birthday", "sandwich", "elephant", "mountain"],
    }


def test_scramble_never_returns_the_original_word():
    for _ in range(200):
        assert words.scramble("house") != "house"


def test_scramble_preserves_the_letters():
    assert sorted(words.scramble("banana")) == sorted("banana")


def test_scramble_returns_unscrambleable_words_unchanged():
    # "aaa" has only one possible arrangement, so looping forever is the bug.
    assert words.scramble("aaa") == "aaa"
    assert words.scramble("a") == "a"


def test_pick_words_returns_the_requested_count(pools):
    for count in (5, 10, 15):
        assert len(words.pick_words(count, by_length=pools)) == count


def test_pick_words_returns_no_duplicates(pools):
    picked = words.pick_words(15, by_length=pools)
    assert len(set(picked)) == len(picked)


def test_small_rounds_are_not_forced_to_include_every_length(pools):
    """A 5-word round should not have to spend a slot on each of 6 lengths."""
    lengths = {len(w) for w in words.pick_words(5, by_length=pools)}
    assert len(lengths) <= 5


def test_pick_words_tops_up_when_a_length_is_short():
    sparse = {4: ["tree", "fish"], 5: ["house", "plant", "green", "smile", "chair"]}
    picked = words.pick_words(5, by_length=sparse)
    assert len(picked) == 5


def test_pick_words_handles_zero():
    assert words.pick_words(0) == []
