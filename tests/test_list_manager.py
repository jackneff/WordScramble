"""The browser-based list manager: paste, upload, replace and delete."""
import io

import pytest

import wordlists
from app import create_app
from config import TestConfig


@pytest.fixture
def lists_dir(tmp_path, monkeypatch):
    directory = tmp_path / "lists"
    directory.mkdir()
    monkeypatch.setattr(wordlists.Config, "LISTS_DIR", str(directory), raising=False)
    return directory


def upload(name):
    return (io.BytesIO(b"planet\nrocket\ncomet\n"), name)


# --- saving ----------------------------------------------------------------

def test_pasted_words_become_a_list(client, lists_dir):
    res = client.post("/lists", data={"name": "Week 12", "words": "planet\nrocket\ncomet"},
                      follow_redirects=True)

    assert res.status_code == 200
    assert wordlists.get_list_words("week-12") == ["planet", "rocket", "comet"]
    assert "Saved Week 12 with 3 words" in res.get_data(as_text=True)


def test_a_saved_list_appears_on_the_home_screen(client, lists_dir):
    client.post("/lists", data={"name": "Week 12", "words": "planet rocket comet"})

    assert "Week 12" in client.get("/").get_data(as_text=True)


def test_an_uploaded_file_becomes_a_list(client, lists_dir):
    res = client.post(
        "/lists",
        data={"name": "Week 13", "file": upload("anything.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert wordlists.get_list_words("week-13") == ["planet", "rocket", "comet"]
    assert "Saved Week 13" in res.get_data(as_text=True)


def test_an_unnamed_upload_falls_back_to_the_filename(client, lists_dir):
    client.post(
        "/lists",
        data={"name": "", "file": upload("Week 14 Science.txt")},
        content_type="multipart/form-data",
    )

    assert wordlists.get_list_name("week-14-science") == "Week 14 Science"


def test_the_upload_filename_does_not_choose_the_path(client, lists_dir, tmp_path):
    """The saved file is named from the list name, never from the upload."""
    client.post(
        "/lists",
        data={"name": "Safe", "file": upload("../../escape.txt")},
        content_type="multipart/form-data",
    )

    assert (lists_dir / "safe.txt").is_file()
    assert not (tmp_path.parent / "escape.txt").exists()


def test_a_traversal_name_is_slugified_not_obeyed(client, lists_dir, tmp_path):
    client.post("/lists", data={"name": "../../etc/passwd", "words": "planet rocket"})

    assert [e["slug"] for e in wordlists.available_lists()] == ["etc-passwd"]


def test_saving_the_same_name_replaces_the_list(client, lists_dir):
    client.post("/lists", data={"name": "Week 12", "words": "planet rocket comet"})
    res = client.post("/lists", data={"name": "Week 12", "words": "saturn galaxy"},
                      follow_redirects=True)

    assert wordlists.get_list_words("week-12") == ["saturn", "galaxy"]
    assert "Replaced Week 12" in res.get_data(as_text=True)


def test_skipped_entries_are_reported(client, lists_dir):
    res = client.post("/lists", data={"name": "Messy", "words": "planet\nit\n42\nrocket"},
                      follow_redirects=True)

    body = res.get_data(as_text=True)
    assert "Saved Messy with 2 words" in body
    assert "Skipped 2 entries" in body


# --- rejections ------------------------------------------------------------

def test_a_list_with_no_usable_words_is_refused(client, lists_dir):
    res = client.post("/lists", data={"name": "Empty", "words": "it 42 ok"},
                      follow_redirects=True)

    assert "No usable words found" in res.get_data(as_text=True)
    assert wordlists.available_lists() == []


def test_a_nameless_list_is_refused(client, lists_dir):
    res = client.post("/lists", data={"name": "!!!", "words": "planet rocket"},
                      follow_redirects=True)

    assert "Give the list a name" in res.get_data(as_text=True)
    assert wordlists.available_lists() == []


def test_a_non_text_upload_is_refused(client, lists_dir):
    res = client.post(
        "/lists",
        data={"name": "Sneaky", "file": (io.BytesIO(b"MZ\x90\x00"), "payload.exe")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert "plain text" in res.get_data(as_text=True)
    assert wordlists.available_lists() == []


def test_an_oversized_body_is_rejected_with_a_message(lists_dir, tmp_path):
    class Small(TestConfig):
        DB_PATH = str(tmp_path / "small.db")
        MAX_CONTENT_LENGTH = 1024

    client = create_app(Small).test_client()
    res = client.post("/lists", data={"name": "Huge", "words": "planet " * 5000},
                      follow_redirects=True)

    assert res.status_code == 200
    assert "too big" in res.get_data(as_text=True)


def test_undecodable_bytes_do_not_crash_the_upload(client, lists_dir):
    res = client.post(
        "/lists",
        data={"name": "Odd", "file": (io.BytesIO(b"planet\n\xff\xfe\nrocket\n"), "odd.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert res.status_code == 200
    assert wordlists.get_list_words("odd") == ["planet", "rocket"]


# --- deleting --------------------------------------------------------------

def test_deleting_a_list(client, lists_dir):
    client.post("/lists", data={"name": "Week 12", "words": "planet rocket comet"})

    res = client.post("/lists/week-12/delete", follow_redirects=True)

    assert "Deleted that list" in res.get_data(as_text=True)
    assert wordlists.available_lists() == []


def test_deleting_something_that_is_not_there(client, lists_dir):
    res = client.post("/lists/nope/delete", follow_redirects=True)

    assert "no longer exists" in res.get_data(as_text=True)


def test_delete_cannot_escape_the_lists_directory(client, lists_dir, tmp_path):
    outside = tmp_path / "important.txt"
    outside.write_text("keep me", encoding="utf-8")

    client.post("/lists/..%2F..%2Fimportant/delete", follow_redirects=True)
    client.post("/lists/../important/delete", follow_redirects=True)

    assert outside.is_file()


def test_delete_is_not_reachable_by_get(client, lists_dir):
    client.post("/lists", data={"name": "Week 12", "words": "planet rocket comet"})

    assert client.get("/lists/week-12/delete").status_code == 405
    assert wordlists.list_exists("week-12")


# --- the page itself -------------------------------------------------------

def test_the_manage_page_lists_what_exists(client, lists_dir):
    client.post("/lists", data={"name": "Week 12", "words": "planet rocket comet"})

    body = client.get("/lists").get_data(as_text=True)

    assert "Week 12" in body
    assert "3 words" in body


def test_the_manage_page_works_with_no_lists(client, lists_dir):
    body = client.get("/lists").get_data(as_text=True)

    assert "No lists yet" in body


def test_the_manager_is_behind_the_pin_gate(tmp_path):
    class Locked(TestConfig):
        DB_PATH = str(tmp_path / "locked.db")
        ACCESS_PIN = "1234"

    client = create_app(Locked).test_client()

    assert client.get("/lists").status_code == 302
    assert client.post("/lists", data={"name": "X", "words": "planet"}).status_code == 302
    assert client.post("/lists/x/delete").status_code == 302
