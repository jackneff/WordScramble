"""History paging, lifetime stats, and the all-time best round."""
import database as db
import game


def _finished_round(words, hints=0):
    """Create a round, solve every word, and return its id."""
    round_id = db.create_round(len(words), words)
    for row in db.get_round_words(round_id):
        for _ in range(hints):
            db.add_hint(row["id"])
        game.check_answer(row["id"], row["word"])
    return round_id


def test_history_pages_at_twenty_rounds(app):
    for _ in range(25):
        _finished_round(["cat"])

    first = game.history_page(1)
    second = game.history_page(2)

    assert len(first["rounds"]) == 20
    assert len(second["rounds"]) == 5
    assert first["total_rounds"] == 25
    assert first["total_pages"] == 2
    assert first["has_next"] and not first["has_prev"]
    assert second["has_prev"] and not second["has_next"]


def test_pages_do_not_overlap(app):
    for _ in range(25):
        _finished_round(["cat"])

    first = {r["id"] for r in game.history_page(1)["rounds"]}
    second = {r["id"] for r in game.history_page(2)["rounds"]}

    assert not first & second
    assert len(first | second) == 25


def test_out_of_range_pages_are_clamped(app):
    _finished_round(["cat"])

    assert game.history_page(0)["page"] == 1
    assert game.history_page(99)["page"] == 1
    assert game.history_page(-5)["page"] == 1


def test_empty_history_reports_one_page(app):
    result = game.history_page(1)

    assert result["rounds"] == []
    assert result["total_pages"] == 1
    assert not result["has_next"]


def test_best_round_is_found_beyond_the_first_page(app):
    """Regression: the badge used to come from the fetched page only."""
    best_id = _finished_round(["treasure", "birthday"])   # 160 points
    for _ in range(25):
        _finished_round(["cat"])                          # 30 points each

    stats = game.lifetime_stats()
    page_one_ids = {r["id"] for r in game.history_page(1)["rounds"]}

    assert stats["best_id"] == best_id
    assert best_id not in page_one_ids       # the best round has aged off page 1
    assert stats["best_score"] == 160


def test_lifetime_stats_count_every_round(app):
    for _ in range(25):
        _finished_round(["cat"])

    assert game.lifetime_stats()["rounds_played"] == 25


def test_lifetime_stats_average_stars(app):
    _finished_round(["house"])              # clean solve -> 3 stars
    _finished_round(["house"], hints=2)     # 50 - 30 = 20/50 = 40% -> 1 star

    assert game.lifetime_stats()["avg_stars"] == 2.0


def test_lifetime_stats_on_an_empty_history(app):
    stats = game.lifetime_stats()

    assert stats["rounds_played"] == 0
    assert stats["best_id"] is None
    assert stats["best_score"] == 0
    assert stats["avg_stars"] == 0


def test_unfinished_rounds_are_excluded(app):
    _finished_round(["cat"])
    db.create_round(1, ["house"])           # started, never solved

    assert game.lifetime_stats()["rounds_played"] == 1
    assert game.history_page(1)["total_rounds"] == 1


def test_history_route_accepts_and_survives_a_page_parameter(client):
    for _ in range(25):
        _finished_round(["cat"])

    assert client.get("/history").status_code == 200
    assert client.get("/history?page=2").status_code == 200
    assert client.get("/history?page=999").status_code == 200
    assert client.get("/history?page=abc").status_code == 200
    assert client.get("/history?page=-1").status_code == 200
