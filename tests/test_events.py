import pytest
from pydantic import ValidationError

from app.db import open_database
from app.events import EVENT_BATCH, EVENT_NAMES, canonical_json, ingest_events


def test_event_names_covers_browsing_and_booking():
    assert set(EVENT_NAMES) == {
        "page_view",
        "class_view",
        "search",
        "booking_started",
        "booking_paid",
        "booking_cancelled",
        "signup",
        "login",
    }


def test_canonical_json_sorts_keys_and_strips_whitespace():
    assert canonical_json({"b": 1, "a": {"d": None, "c": "x"}}) == '{"a":{"c":"x","d":null},"b":1}'


def test_canonical_json_keeps_a_value_that_was_stated_as_nothing():
    assert canonical_json({"a": None, "b": 1}) == '{"a":null,"b":1}'


def test_batch_rejects_an_unknown_event_name():
    with pytest.raises(ValidationError):
        EVENT_BATCH.validate_python(
            [{"occurred_at": 1, "session_id": "s1", "studio_id": 1, "event_name": "purchase"}]
        )


def test_batch_defaults_nullable_fields():
    parsed = EVENT_BATCH.validate_python(
        [{"occurred_at": 1, "session_id": "s1", "studio_id": 1, "event_name": "page_view"}]
    )
    assert parsed[0].user_id is None
    assert parsed[0].booking_id is None
    assert parsed[0].class_id is None
    assert parsed[0].properties == {}


def test_batch_rejects_a_nested_property_value():
    with pytest.raises(ValidationError):
        EVENT_BATCH.validate_python(
            [
                {
                    "occurred_at": 1,
                    "session_id": "s",
                    "studio_id": 1,
                    "event_name": "page_view",
                    "properties": {"nested": {"a": 1}},
                }
            ]
        )


def test_batch_rejects_an_empty_list():
    with pytest.raises(ValidationError):
        EVENT_BATCH.validate_python([])


def test_ingest_stores_a_batch_with_canonical_properties():
    conn = open_database(":memory:")
    conn.execute("INSERT INTO studios (id, name, city) VALUES (1, 'Harbor Yoga', 'Eastport')")
    stored = ingest_events(
        conn,
        [
            {
                "occurred_at": 10,
                "user_id": None,
                "session_id": "s1",
                "studio_id": 1,
                "booking_id": None,
                "class_id": None,
                "event_name": "page_view",
                "properties": {"device": "web", "referrer": "direct"},
            },
            {
                "occurred_at": 20,
                "user_id": 5,
                "session_id": "s1",
                "studio_id": 1,
                "booking_id": None,
                "class_id": 3,
                "event_name": "class_view",
                "properties": {"class_id": 3},
            },
        ],
    )
    assert stored == 2
    rows = conn.execute("SELECT event_name, properties FROM events ORDER BY id").fetchall()
    assert rows[0]["properties"] == '{"device":"web","referrer":"direct"}'
    assert rows[1]["event_name"] == "class_view"
    second = conn.execute(
        "SELECT occurred_at, user_id, session_id, studio_id, booking_id, class_id "
        "FROM events WHERE id = 2"
    ).fetchone()
    assert dict(second) == {
        "occurred_at": 20,
        "user_id": 5,
        "session_id": "s1",
        "studio_id": 1,
        "booking_id": None,
        "class_id": 3,
    }


def test_ingest_stores_an_event_that_belongs_to_no_studio():
    conn = open_database(":memory:")
    parsed = EVENT_BATCH.validate_python(
        [{"occurred_at": 30, "session_id": "s1", "event_name": "login", "user_id": 7}]
    )
    assert parsed[0].studio_id is None
    assert ingest_events(conn, parsed) == 1
    row = conn.execute("SELECT user_id, studio_id, event_name FROM events").fetchone()
    assert dict(row) == {"user_id": 7, "studio_id": None, "event_name": "login"}


def test_ingest_stores_nothing_for_an_empty_batch():
    conn = open_database(":memory:")
    assert ingest_events(conn, []) == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0
