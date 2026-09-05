from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.clock import now_ms
from app.main import app
from app.session import parse_user_id

MEMBER = "ss_user=1; ss_session=abc"
CLIENT = TestClient(app)
# A client that reads the failure response rather than re-raising what the route threw.
QUIET_CLIENT = TestClient(app, raise_server_exceptions=False)


def post(path, body=None, cookie="", **kwargs):
    CLIENT.cookies.clear()
    return CLIENT.post(path, json=body, headers={"cookie": cookie}, **kwargs)


def get(path, cookie=MEMBER):
    CLIENT.cookies.clear()
    return CLIENT.get(path, headers={"cookie": cookie})


def moment(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_parse_user_id_keeps_digits_and_rejects_anything_else():
    assert parse_user_id("abc") is None
    assert parse_user_id("12") == 12


def test_session_signs_a_known_member_in_and_out():
    signed_in = post("/api/session", {"user_id": 1})
    assert signed_in.status_code == 200
    assert "ss_user=1" in signed_in.headers["set-cookie"]
    signed_out = post("/api/session", {})
    assert "ss_user=;" in signed_out.headers["set-cookie"]
    missing = post("/api/session", {"user_id": 9999})
    assert missing.status_code == 404


def test_session_records_a_login_for_the_member_who_signed_in():
    from app.db import get_db

    response = post("/api/session", {"user_id": 1}, cookie="ss_session=login1")
    assert response.status_code == 200
    row = get_db().execute(
        "SELECT user_id, studio_id, session_id, properties FROM events "
        "WHERE event_name = 'login' AND session_id = 'login1'"
    ).fetchone()
    assert dict(row) == {
        "user_id": 1,
        "studio_id": None,
        "session_id": "login1",
        "properties": '{"device":"web"}',
    }


def test_events_accepts_a_batch_and_sets_a_session_cookie_when_missing():
    response = post(
        "/api/events", [{"event_name": "page_view", "studio_id": 1, "properties": {"path": "/"}}]
    )
    assert response.status_code == 202
    assert "ss_session=" in response.headers["set-cookie"]
    assert response.json() == {"accepted": 1}


def test_events_leaves_an_existing_session_cookie_alone():
    response = post(
        "/api/events", [{"event_name": "page_view", "studio_id": 1}], cookie="ss_session=abc"
    )
    assert response.status_code == 202
    assert response.headers.get("set-cookie") is None
    assert response.headers["cache-control"] == "private, no-store"


def test_events_reads_a_cookie_that_is_not_valid_escaping():
    response = post(
        "/api/events",
        [{"event_name": "page_view", "studio_id": 1}],
        cookie="ss_session=%E0; ss_user=1",
    )
    assert response.status_code == 202


def test_events_accepts_a_class_view_that_names_its_class():
    response = post(
        "/api/events",
        [{"event_name": "class_view", "studio_id": 1, "class_id": 1}],
        cookie="ss_session=abc",
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": 1}


def test_events_rejects_an_unknown_name_and_a_malformed_body():
    assert post("/api/events", [{"event_name": "purchase", "studio_id": 1}]).status_code == 400
    CLIENT.cookies.clear()
    malformed = CLIENT.post("/api/events", content="not json", headers={"cookie": ""})
    assert malformed.status_code == 400


def test_events_rejects_a_name_outside_the_list_a_page_may_report():
    response = post("/api/events", [{"event_name": "newsletter_opened", "studio_id": 1}])
    assert response.status_code == 400


def test_events_rejects_a_name_the_booking_service_writes_and_a_time_in_the_future():
    assert post("/api/events", [{"event_name": "booking_paid", "studio_id": 1}]).status_code == 400
    ahead = [{"event_name": "page_view", "studio_id": 1, "occurred_at": now_ms() + 3_600_000}]
    assert post("/api/events", ahead).status_code == 400


def test_events_accepts_an_event_that_belongs_to_no_studio():
    response = post(
        "/api/events",
        [{"event_name": "login", "properties": {"device": "web"}}],
        cookie="ss_session=nostudio; ss_user=1",
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": 1}


def test_events_rejects_a_timestamp_stated_as_nothing():
    response = post("/api/events", [{"event_name": "page_view", "studio_id": 1, "occurred_at": None}])
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_events"


def test_events_takes_a_batch_that_leaves_the_timestamp_out():
    response = post("/api/events", [{"event_name": "page_view", "studio_id": 1}])
    assert response.status_code == 202


def test_events_rejects_a_batch_that_names_a_booking():
    response = post(
        "/api/events", [{"event_name": "page_view", "studio_id": 1, "booking_id": 5}]
    )
    assert response.status_code == 400


def test_events_rejects_a_batch_naming_a_studio_that_does_not_exist():
    response = post(
        "/api/events",
        [{"event_name": "page_view", "studio_id": 1}, {"event_name": "search", "studio_id": 999999}],
    )
    assert response.status_code == 400
    assert response.json() == {"error": "unknown_studio", "studio_id": 999999}


def test_an_unplanned_failure_comes_back_as_an_internal_error():
    QUIET_CLIENT.cookies.clear()
    response = QUIET_CLIENT.post(
        "/api/events",
        json=[{"event_name": "page_view", "studio_id": 2**70}],
        headers={"cookie": ""},
    )
    assert response.status_code == 500
    assert response.json() == {"error": "internal"}
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "private, no-store"


def test_reports_returns_rows_for_a_known_name_and_404_for_an_unknown_one():
    ok = get("/api/reports/daily_actives?from=2026-08-01&to=2026-08-31")
    assert ok.status_code == 200
    body = ok.json()
    assert body["report"] == "daily_actives"
    assert isinstance(body["rows"], list)
    assert body["from"] == "2026-08-01T00:00:00.000Z"
    assert get("/api/reports/nope").status_code == 404


def test_reports_defaults_to_the_most_recent_thirty_days():
    body = get("/api/reports/daily_actives").json()
    assert moment(body["to"]) - moment(body["from"]) == timedelta(days=30)
    assert abs(moment(body["to"]) - datetime.now(timezone.utc)) < timedelta(minutes=1)
    assert isinstance(body["rows"], list)


def test_reports_returns_400_for_a_bad_range():
    response = get("/api/reports/daily_actives?from=2026-09-01&to=2026-08-01")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_range"


def test_reports_require_a_signed_in_member():
    response = get("/api/reports/daily_actives", cookie="")
    assert response.status_code == 401
    assert response.json()["error"] == "sign_in_required"


def test_bookings_need_a_member_then_book_list_pay_and_cancel():
    assert post("/api/bookings", {"class_id": 1}).status_code == 401
    created = post("/api/bookings", {"class_id": 1}, cookie=MEMBER)
    assert created.status_code == 201
    booking = created.json()
    assert booking["status"] == "pending"

    listed = get("/api/bookings")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "private, no-store"
    assert any(row["id"] == booking["id"] for row in listed.json())

    paid = post(f"/api/bookings/{booking['id']}/pay", {}, cookie=MEMBER)
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    cancelled = post(f"/api/bookings/{booking['id']}/cancel", {}, cookie=MEMBER)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_bookings_map_rule_failures_to_their_status_codes():
    created = post("/api/bookings", {"class_id": 2}, cookie=MEMBER)
    booking = created.json()
    again = post("/api/bookings", {"class_id": 2}, cookie=MEMBER)
    assert again.status_code == 409
    assert again.json()["error"] == "already_booked"

    someone_else = post(
        f"/api/bookings/{booking['id']}/pay", {}, cookie="ss_user=2; ss_session=zzz"
    )
    assert someone_else.status_code == 404

    bad_id = post("/api/bookings/abc/pay", {}, cookie=MEMBER)
    assert bad_id.status_code == 400

    bad_body = post("/api/bookings", {"class_id": "one"}, cookie=MEMBER)
    assert bad_body.status_code == 400
    assert bad_body.json()["error"] == "invalid_body"

    for wanted in (0, -3):
        refused = post("/api/bookings", {"class_id": wanted}, cookie=MEMBER)
        assert refused.status_code == 400
        assert refused.json()["error"] == "invalid_body"
