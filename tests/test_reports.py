import pytest

from app.db import open_database
from app.events import ingest_events
from app.reports.booking_funnel import booking_funnel
from app.reports.cancellation_rate import cancellation_rate
from app.reports.daily_actives import daily_actives
from app.reports.range import Range, parse_range
from app.reports.top_classes import top_classes
from app.world import Booking, insert_bookings, insert_world
from tests.helpers import utc
from tests.tiny_world import TINY_WORLD

DAY = 86_400_000


def fresh_db():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    return conn


def ev(occurred_at, event_name, **overrides):
    row = {
        "occurred_at": occurred_at,
        "event_name": event_name,
        "user_id": None,
        "session_id": "s1",
        "studio_id": 1,
        "booking_id": None,
        "class_id": None,
        "properties": {},
    }
    row.update(overrides)
    return row


def bk(booking_id, class_id, **overrides):
    row = {
        "id": booking_id,
        "class_id": class_id,
        "user_id": 1,
        "studio_id": 1,
        "status": "paid",
        "created_at": 0,
        "paid_at": None,
        "cancelled_at": None,
        "price_cents": 1800,
        "occurs_at": utc(2026, 10, 1) + booking_id * DAY,
    }
    row.update(overrides)
    return Booking(**row)


def test_parse_range_is_half_open_utc_and_validates_order():
    assert parse_range("2026-01-01", "2026-02-01") == Range(utc(2026, 1, 1), utc(2026, 2, 1))
    with pytest.raises(ValueError, match="before"):
        parse_range("2026-02-01", "2026-01-01")
    with pytest.raises(ValueError, match="from"):
        parse_range("nope", "2026-01-01")


def test_parse_range_defaults_to_the_trailing_thirty_days():
    now = utc(2026, 9, 1, 12)
    assert parse_range(None, None, now) == Range(now - 30 * DAY, now)


def test_parse_range_reads_a_bare_time_as_utc_and_honours_a_stated_offset():
    assert parse_range("2026-01-01T06:00", "2026-01-02").start == utc(2026, 1, 1, 6)
    assert parse_range("2026-01-01T00:00:00+05:00", "2026-01-02").start == utc(2025, 12, 31, 19)
    assert parse_range("2026-01-01T00:00:00.250", "2026-01-02").start == utc(2026, 1, 1) + 250


def test_parse_range_rejects_a_window_that_covers_nothing():
    with pytest.raises(ValueError, match="before"):
        parse_range("2026-01-01", "2026-01-01")


def test_daily_actives_counts_distinct_signed_in_members_per_utc_day():
    conn = fresh_db()
    ingest_events(
        conn,
        [
            ev(utc(2026, 3, 1, 23, 59), "page_view", user_id=1),
            ev(utc(2026, 3, 1, 23, 59), "class_view", user_id=1),
            ev(utc(2026, 3, 2, 0, 0), "page_view", user_id=2),
            ev(utc(2026, 3, 2, 1, 0), "page_view"),
            ev(utc(2026, 3, 3, 0, 0), "page_view", user_id=1),
        ],
    )
    assert daily_actives(conn, Range(utc(2026, 3, 1), utc(2026, 3, 3))) == [
        {"day": "2026-03-01", "active_users": 1},
        {"day": "2026-03-02", "active_users": 1},
    ]


def test_an_event_that_belongs_to_no_studio_counts_but_leaves_the_funnel_alone():
    conn = fresh_db()
    ingest_events(
        conn,
        [
            ev(utc(2026, 3, 1, 9), "class_view", session_id="a", properties={"class_id": 1}),
            ev(utc(2026, 3, 1, 10), "booking_started", session_id="a", user_id=2, booking_id=1),
        ],
    )
    window = Range(utc(2026, 3, 1), utc(2026, 3, 2))
    before = booking_funnel(conn, window)
    ingest_events(conn, [ev(utc(2026, 3, 1, 11), "page_view", user_id=1, studio_id=None)])
    assert daily_actives(conn, window) == [{"day": "2026-03-01", "active_users": 2}]
    assert booking_funnel(conn, window) == before


def test_booking_funnel_counts_sessions_by_ordered_stage_per_studio():
    conn = fresh_db()
    ingest_events(
        conn,
        [
            ev(100, "class_view", session_id="a", properties={"class_id": 1}),
            ev(200, "booking_started", session_id="a", user_id=1, booking_id=1),
            ev(300, "booking_paid", session_id="a", user_id=1, booking_id=1),
            ev(100, "class_view", session_id="b", properties={"class_id": 1}),
            ev(150, "class_view", session_id="b", properties={"class_id": 1}),
            ev(400, "booking_started", session_id="b", user_id=2, booking_id=2),
            ev(50, "booking_paid", session_id="c", user_id=2, booking_id=3),
            ev(60, "class_view", session_id="c"),
        ],
    )
    assert booking_funnel(conn, Range(0, 1000)) == [
        {"studio_id": 1, "studio": "Harbor Yoga", "viewed": 3, "started": 2, "paid": 1}
    ]


def test_a_stage_at_the_same_millisecond_does_not_advance_the_funnel():
    conn = fresh_db()
    ingest_events(
        conn,
        [
            ev(100, "class_view", session_id="z", properties={"class_id": 1}),
            ev(100, "booking_started", session_id="z", user_id=1, booking_id=1),
            ev(100, "booking_paid", session_id="z", user_id=1, booking_id=1),
        ],
    )
    assert booking_funnel(conn, Range(0, 1000)) == [
        {"studio_id": 1, "studio": "Harbor Yoga", "viewed": 1, "started": 0, "paid": 0}
    ]


def test_the_funnel_counts_a_view_that_lands_exactly_on_the_start():
    conn = fresh_db()
    ingest_events(conn, [ev(100, "class_view", session_id="e", properties={"class_id": 1})])
    assert booking_funnel(conn, Range(100, 200)) == [
        {"studio_id": 1, "studio": "Harbor Yoga", "viewed": 1, "started": 0, "paid": 0}
    ]


def test_top_classes_counts_paid_bookings_and_revenue_and_sorts_by_paid_views_id():
    conn = fresh_db()
    ingest_events(
        conn,
        [
            ev(1, "class_view", class_id=1),
            ev(2, "class_view", class_id=2, studio_id=2),
            ev(3, "class_view", class_id=2, studio_id=2),
        ],
    )
    insert_bookings(conn, [bk(9, 1, paid_at=4)])
    assert top_classes(conn, Range(0, 100)) == [
        {
            "class_id": 1,
            "title": "Sunrise Flow",
            "studio_id": 1,
            "views": 1,
            "paid_bookings": 1,
            "revenue_cents": 1800,
        },
        {
            "class_id": 2,
            "title": "Wheel Basics",
            "studio_id": 2,
            "views": 2,
            "paid_bookings": 0,
            "revenue_cents": 0,
        },
    ]


def test_top_classes_keeps_a_booking_later_cancelled_and_drops_one_paid_before_the_window():
    conn = fresh_db()
    insert_bookings(
        conn,
        [
            bk(1, 1, status="cancelled", paid_at=150, cancelled_at=500),
            bk(2, 1, paid_at=50),
        ],
    )
    assert top_classes(conn, Range(100, 200)) == [
        {
            "class_id": 1,
            "title": "Sunrise Flow",
            "studio_id": 1,
            "views": 0,
            "paid_bookings": 1,
            "revenue_cents": 1800,
        }
    ]


def test_top_classes_leaves_out_a_view_that_names_no_class():
    conn = fresh_db()
    ingest_events(conn, [ev(1, "class_view"), ev(2, "class_view", class_id=1)])
    assert top_classes(conn, Range(0, 100)) == [
        {
            "class_id": 1,
            "title": "Sunrise Flow",
            "studio_id": 1,
            "views": 1,
            "paid_bookings": 0,
            "revenue_cents": 0,
        }
    ]


def test_cancellation_rate_is_a_paid_week_cohort_rate():
    conn = fresh_db()
    paid_monday = utc(2025, 12, 29, 10)  # ISO 2026-W01
    insert_bookings(
        conn,
        [
            bk(1, 1, status="cancelled", paid_at=paid_monday, cancelled_at=utc(2026, 1, 20)),
            bk(2, 1, user_id=2, paid_at=paid_monday + 2),
            bk(3, 2, user_id=2, studio_id=2, paid_at=utc(2026, 1, 6)),
        ],
    )
    assert cancellation_rate(conn, Range(utc(2025, 12, 1), utc(2026, 2, 1))) == [
        {
            "studio_id": 1,
            "studio": "Harbor Yoga",
            "week": "2026-W01",
            "paid_bookings": 2,
            "cancelled": 1,
            "cancellation_rate": 0.5,
        },
        {
            "studio_id": 2,
            "studio": "Kiln & Wheel",
            "week": "2026-W02",
            "paid_bookings": 1,
            "cancelled": 0,
            "cancellation_rate": 0,
        },
    ]


def test_a_booking_cancelled_after_the_window_counts_as_paid_and_not_cancelled():
    conn = fresh_db()
    insert_bookings(
        conn,
        [bk(1, 1, status="cancelled", paid_at=utc(2026, 1, 5), cancelled_at=utc(2026, 3, 1))],
    )
    assert cancellation_rate(conn, Range(utc(2026, 1, 1), utc(2026, 2, 1))) == [
        {
            "studio_id": 1,
            "studio": "Harbor Yoga",
            "week": "2026-W02",
            "paid_bookings": 1,
            "cancelled": 0,
            "cancellation_rate": 0,
        }
    ]


def test_a_booking_paid_before_the_window_is_left_out_even_when_cancelled_inside_it():
    conn = fresh_db()
    insert_bookings(
        conn,
        [bk(1, 1, status="cancelled", paid_at=utc(2025, 11, 3), cancelled_at=utc(2026, 1, 10))],
    )
    assert cancellation_rate(conn, Range(utc(2026, 1, 1), utc(2026, 2, 1))) == []


def test_an_early_january_payment_lands_in_the_trailing_week_of_the_year_before():
    conn = fresh_db()
    insert_bookings(conn, [bk(1, 1, paid_at=utc(2027, 1, 2))])
    assert cancellation_rate(conn, Range(utc(2026, 12, 1), utc(2027, 2, 1))) == [
        {
            "studio_id": 1,
            "studio": "Harbor Yoga",
            "week": "2026-W53",
            "paid_bookings": 1,
            "cancelled": 0,
            "cancellation_rate": 0,
        }
    ]
