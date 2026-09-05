from fastapi.testclient import TestClient

from app.clock import now_ms
from app.db import get_db
from app.main import app

CLIENT = TestClient(app)
CLASS_KEYS = {"id", "studio_id", "studio", "title", "price_cents", "next_on"}


def get(path, cookie=""):
    CLIENT.cookies.clear()
    return CLIENT.get(path, headers={"cookie": cookie})


def searches():
    return get_db().execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_name = 'search'"
    ).fetchone()["n"]


def test_studios_lists_each_studio_with_its_timetable():
    response = get("/api/studios")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    listing = response.json()
    assert [studio["name"] for studio in listing] == sorted(s["name"] for s in listing)
    for studio in listing:
        assert set(studio) == {"id", "name", "city", "classes"}
        ids = [klass["id"] for klass in studio["classes"]]
        assert ids == sorted(ids)
        for klass in studio["classes"]:
            assert set(klass) == {"id", "title", "price_cents", "next_on"}


def test_every_class_names_the_date_it_next_runs():
    now = now_ms()
    for studio in get("/api/studios").json():
        for klass in studio["classes"]:
            assert klass["next_on"] > now


def test_a_class_comes_back_with_its_studio():
    response = get("/api/classes/1")
    assert response.status_code == 200
    klass = response.json()
    assert set(klass) == CLASS_KEYS
    assert klass["id"] == 1
    assert klass["studio"]
    assert klass["next_on"] > now_ms()


def test_a_class_nobody_offers_is_not_found():
    for path in ("/api/classes/999999", "/api/classes/abc"):
        response = get(path)
        assert response.status_code == 404
        assert response.json() == {"error": "no_such_class"}


def test_classes_without_a_query_lists_them_all_and_records_nothing():
    before = searches()
    listing = get("/api/classes").json()
    assert len(listing) == len(get_db().execute("SELECT id FROM classes").fetchall())
    assert all(set(klass) == CLASS_KEYS for klass in listing)
    assert get("/api/classes?q=").status_code == 200
    assert get("/api/classes?q=%20%20").status_code == 200
    assert searches() == before


def test_classes_matches_a_title_whatever_its_case():
    listing = get("/api/classes?q=fLoW").json()
    assert listing
    assert all("flow" in klass["title"].lower() for klass in listing)
    assert len(listing) < len(get("/api/classes").json())


def test_a_search_records_one_event_for_the_session():
    before = searches()
    response = get("/api/classes?q=%20wheel%20", cookie="ss_session=hunting; ss_user=1")
    assert response.status_code == 200
    assert searches() == before + 1
    row = get_db().execute(
        "SELECT user_id, session_id, studio_id, class_id, properties FROM events "
        "WHERE event_name = 'search' AND session_id = 'hunting'"
    ).fetchone()
    assert dict(row) == {
        "user_id": 1,
        "session_id": "hunting",
        "studio_id": None,
        "class_id": None,
        "properties": '{"query":"wheel"}',
    }


def test_browsing_hands_out_a_session_cookie_when_there_is_none():
    response = get("/api/classes")
    assert "ss_session=" in response.headers["set-cookie"]
    assert get("/api/studios", cookie="ss_session=known").headers.get("set-cookie") is None
