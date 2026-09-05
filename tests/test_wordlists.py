"""Custom vocabulary lists: discovery, validation and playing a list."""
import pytest

import database as db
import game
import wordlists


@pytest.fixture
def lists_dir(tmp_path, monkeypatch):
    """A lists directory the module reads by default."""
    directory = tmp_path / "lists"
    directory.mkdir()
    monkeypatch.setattr(wordlists.Config, "LISTS_DIR", str(directory), raising=False)
    return directory


def write_list(directory, name, words):
    (directory / name).write_text("\n".join(words), encoding="utf-8")


def make_words(count):
    """Distinct letters-only words, for bulk fixtures."""
    words = []
    for i in range(count):
        suffix, n = "", i
        for _ in range(3):
            suffix = chr(ord("a") + n % 26) + suffix
            n //= 26
        words.append("w" + suffix)
    return words


# --- discovery -------------------------------------------------------------

def test_a_dropped_file_becomes_a_list(lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])

    lists = wordlists.available_lists()

    assert lists == [{"slug": "week-12", "name": "Week 12", "count": 3}]


def test_filenames_become_readable_names(lists_dir):
    write_list(lists_dir, "sight_words.txt", ["there", "where"])
    write_list(lists_dir, "unit-3-science.txt", ["orbit", "comet"])

    names = [entry["name"] for entry in wordlists.available_lists()]

    assert names == ["Sight Words", "Unit 3 Science"]


def test_lists_are_picked_up_without_a_restart(lists_dir):
    assert wordlists.available_lists() == []

    write_list(lists_dir, "new.txt", ["planet", "rocket", "comet"])

    assert len(wordlists.available_lists()) == 1


def test_a_missing_directory_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        wordlists.Config, "LISTS_DIR", str(tmp_path / "nope"), raising=False
    )
    assert wordlists.available_lists() == []


def test_non_txt_and_badly_named_files_are_ignored(lists_dir):
    write_list(lists_dir, "notes.md", ["planet"])
    write_list(lists_dir, "Week 12.txt", ["planet"])      # space in the name
    write_list(lists_dir, "-leading.txt", ["planet"])
    write_list(lists_dir, "good.txt", ["planet"])

    assert [e["slug"] for e in wordlists.available_lists()] == ["good"]


def test_an_empty_list_is_not_offered(lists_dir):
    write_list(lists_dir, "empty.txt", [])
    write_list(lists_dir, "comments.txt", ["# just a comment", ""])

    assert wordlists.available_lists() == []


# --- parsing ---------------------------------------------------------------

def test_words_are_normalised_and_deduplicated(lists_dir):
    write_list(lists_dir, "messy.txt", ["  Planet ", "ROCKET", "planet", "comet"])

    assert wordlists.get_list_words("messy") == ["planet", "rocket", "comet"]


def test_unusable_entries_are_skipped(lists_dir):
    write_list(lists_dir, "mixed.txt", [
        "# this week",
        "planet",
        "it",                    # too short to scramble
        "supercalifragilistic",  # too long for the tile row
        "hy-phen",               # not a plain word
        "42",
        "rocket",
    ])

    assert wordlists.get_list_words("mixed") == ["planet", "rocket"]


def test_words_may_be_separated_by_commas_or_spaces(lists_dir):
    """A list copied out of an email is rarely one word per line."""
    write_list(lists_dir, "pasted.txt", ["planet, rocket; comet", "orbit galaxy"])

    assert wordlists.get_list_words("pasted") == [
        "planet", "rocket", "comet", "orbit", "galaxy",
    ]


def test_comment_lines_are_ignored_even_with_several_words(lists_dir):
    write_list(lists_dir, "commented.txt", ["# week twelve spelling", "planet rocket"])

    assert wordlists.get_list_words("commented") == ["planet", "rocket"]


def test_a_list_is_capped(lists_dir):
    write_list(lists_dir, "huge.txt", make_words(900))

    assert len(wordlists.get_list_words("huge")) == wordlists.MAX_WORDS_PER_LIST


# --- lookup safety ---------------------------------------------------------

def test_unknown_lists_return_none(lists_dir):
    assert wordlists.get_list_words("nope") is None
    assert wordlists.get_list_words("") is None
    assert wordlists.get_list_words(None) is None


def test_path_traversal_is_rejected(lists_dir, tmp_path):
    (tmp_path / "secret.txt").write_text("planet\nrocket", encoding="utf-8")

    for attempt in ["../secret", "..%2Fsecret", "/etc/passwd", "..\\secret", "a/../b"]:
        assert wordlists.get_list_words(attempt) is None


# --- playing a list --------------------------------------------------------

def test_a_round_is_drawn_only_from_the_chosen_list(app, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet", "orbit", "galaxy"])

    chosen = game.choose_words(5, word_list="week-12")

    assert sorted(chosen) == ["comet", "galaxy", "orbit", "planet", "rocket"]


def test_a_short_list_makes_a_short_round(app, lists_dir):
    """A 3-word list is played as a 3-word round, not padded with other words."""
    write_list(lists_dir, "short.txt", ["planet", "rocket", "comet"])

    round_id, words = game.start_round(10, word_list="short")

    assert len(words) == 3
    assert db.get_round(round_id)["round_size"] == 3
    stored = {w["word"] for w in db.get_round_words(round_id)}
    assert stored == {"planet", "rocket", "comet"}


def test_a_long_list_is_sampled_down_to_the_round_size(app, lists_dir):
    write_list(lists_dir, "big.txt", make_words(60))

    _, words = game.start_round(5, word_list="big")

    assert len(words) == 5


def test_the_round_records_which_list_it_used(app, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])

    round_id, _ = game.start_round(5, word_list="week-12")

    assert db.get_round(round_id)["word_list"] == "week-12"


def test_a_normal_round_records_no_list(app):
    round_id, _ = game.start_round(5)

    assert db.get_round(round_id)["word_list"] is None


def test_starting_a_deleted_list_fails_cleanly(app, lists_dir):
    assert game.start_round(5, word_list="gone") == (None, None)


def test_history_shows_the_list_name(app, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])
    round_id, _ = game.start_round(5, word_list="week-12")
    for row in db.get_round_words(round_id):
        game.check_answer(row["id"], row["word"])

    entry = game.history_page(1)["rounds"][0]

    assert entry["list_name"] == "Week 12"


def test_history_still_names_a_deleted_list(app, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])
    round_id, _ = game.start_round(5, word_list="week-12")
    for row in db.get_round_words(round_id):
        game.check_answer(row["id"], row["word"])

    (lists_dir / "week-12.txt").unlink()

    assert game.history_page(1)["rounds"][0]["list_name"] == "Week 12"


def test_list_words_feed_the_challenge_tracker(app, lists_dir):
    """Words from a parent's list must earn practice tracking like any other."""
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])
    round_id, _ = game.start_round(5, word_list="week-12")

    row = db.get_round_words(round_id)[0]
    game.check_answer(row["id"], "wrong")
    game.check_answer(row["id"], row["word"])

    assert row["word"] in [w["word"] for w in db.get_challenge_words()]


# --- HTTP ------------------------------------------------------------------

def test_the_home_page_offers_the_lists(client, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])

    body = client.get("/").get_data(as_text=True)

    assert "Week 12" in body
    assert "All Words" in body


def test_the_home_page_hides_the_picker_with_no_lists(client, lists_dir):
    body = client.get("/").get_data(as_text=True)

    assert "Which words?" not in body


def test_starting_a_list_round_over_http(client, lists_dir):
    write_list(lists_dir, "week-12.txt", ["planet", "rocket", "comet"])

    res = client.post("/api/start", json={"round_size": 5, "word_list": "week-12"})

    assert res.status_code == 200
    assert len(res.get_json()["words"]) == 3


def test_requesting_an_unknown_list_over_http_is_a_404(client, lists_dir):
    res = client.post("/api/start", json={"round_size": 5, "word_list": "nope"})

    assert res.status_code == 404


def test_a_traversal_attempt_over_http_is_a_404(client, lists_dir):
    res = client.post("/api/start", json={"round_size": 5, "word_list": "../../etc/passwd"})

    assert res.status_code == 404
