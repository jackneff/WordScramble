"""CSRF protection on the endpoints that change something.

`raw_client` is a plain test client with no token, so these exercise the
rejection path that the ordinary `client` fixture deliberately bypasses.
"""
import security


def test_a_get_needs_no_token(raw_client):
    assert raw_client.get("/").status_code == 200


def test_a_form_post_without_a_token_is_rejected(raw_client):
    res = raw_client.post("/lists", data={"name": "Week 1", "words": "planet"})

    assert res.status_code == 400
    assert "CSRF" in res.get_data(as_text=True)


def test_a_delete_without_a_token_is_rejected(raw_client):
    assert raw_client.post("/lists/week-1/delete").status_code == 400


def test_an_api_post_without_a_token_is_rejected_as_json(raw_client):
    res = raw_client.post("/api/start", json={"round_size": 5})

    assert res.status_code == 400
    assert res.get_json()["error"] == "Invalid CSRF token"


def test_a_wrong_token_is_rejected(raw_client):
    with raw_client.session_transaction() as session:
        session[security.SESSION_KEY] = "the-real-token"

    res = raw_client.post(
        "/api/start", json={}, headers={security.HEADER_NAME: "a-guess"}
    )

    assert res.status_code == 400


def test_a_non_ascii_token_is_rejected_not_crashed(raw_client):
    """compare_digest raises on non-ASCII str, which used to mean a 500."""
    with raw_client.session_transaction() as session:
        session[security.SESSION_KEY] = "the-real-token"

    res = raw_client.post(
        "/api/start", json={}, headers={security.HEADER_NAME: "tökén"}
    )

    assert res.status_code == 400


def test_the_matching_token_is_accepted(raw_client):
    with raw_client.session_transaction() as session:
        session[security.SESSION_KEY] = "the-real-token"

    res = raw_client.post(
        "/api/start",
        json={"round_size": 5},
        headers={security.HEADER_NAME: "the-real-token"},
    )

    assert res.status_code == 200
    assert "round_id" in res.get_json()


def test_the_page_carries_a_token_for_the_form_to_use(client):
    body = client.get("/lists").get_data(as_text=True)

    assert 'name="csrf_token"' in body
    assert 'name="csrf-token"' in body
