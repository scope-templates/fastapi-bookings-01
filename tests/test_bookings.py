import sqlite3
import threading

import pytest

from app.bookings import BookingError, cancel_booking, create_booking, pay_booking
from app.classes import next_occurrence
from app.db import open_database
from app.world import Booking, ClassRow, Studio, User, World, insert_bookings, insert_world
from tests.helpers import utc
from tests.tiny_world import TINY_WORLD

NOW = utc(2026, 9, 1, 12)
OCCURS = utc(2026, 10, 1, 7)
WEEK = 7 * 86_400_000


def fresh_db():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    return conn


def booked(
    booking_id, class_id, *, user_id=1, status="paid", paid_at=None, cancelled_at=None, occurs_at=OCCURS
):
    return Booking(
        id=booking_id,
        user_id=user_id,
        class_id=class_id,
        studio_id=1,
        status=status,
        created_at=NOW,
        paid_at=paid_at,
        cancelled_at=cancelled_at,
        price_cents=1800,
        occurs_at=occurs_at,
    )


def recorded(conn):
    return [
        dict(row)
        for row in conn.execute(
            "SELECT event_name, booking_id, user_id, class_id FROM events ORDER BY id"
        )
    ]


def test_create_leaves_the_booking_pending_and_records_booking_started():
    conn = fresh_db()
    booking = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    assert booking["status"] == "pending"
    assert booking["price_cents"] == 1800
    assert booking["occurs_at"] == next_occurrence(TINY_WORLD.classes[0], NOW)
    assert recorded(conn) == [
        {"event_name": "booking_started", "booking_id": booking["id"], "user_id": 1, "class_id": 1}
    ]


def test_pay_records_booking_paid_with_class_and_price():
    conn = fresh_db()
    booking = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    paid = pay_booking(
        conn, booking_id=booking["id"], user_id=1, session_id="s-abc", now=NOW + 1000
    )
    assert paid["status"] == "paid"
    row = conn.execute(
        "SELECT properties FROM events WHERE event_name = 'booking_paid'"
    ).fetchone()
    assert row["properties"] == '{"class_id":1,"price_cents":1800}'


def test_cancel_works_only_from_paid_and_before_the_class_starts():
    conn = fresh_db()
    booking = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    with pytest.raises(BookingError):
        cancel_booking(conn, booking_id=booking["id"], user_id=1, session_id="s", now=NOW)
    pay_booking(conn, booking_id=booking["id"], user_id=1, session_id="s", now=NOW)
    cancelled = cancel_booking(
        conn, booking_id=booking["id"], user_id=1, session_id="s", now=NOW + 5000
    )
    assert cancelled["status"] == "cancelled"
    assert [e["event_name"] for e in recorded(conn)] == [
        "booking_started",
        "booking_paid",
        "booking_cancelled",
    ]
    assert [e["class_id"] for e in recorded(conn)] == [1, 1, 1]


def test_refuses_cancelling_after_the_class_has_started():
    conn = fresh_db()
    booking = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    pay_booking(conn, booking_id=booking["id"], user_id=1, session_id="s", now=NOW)
    with pytest.raises(BookingError, match="started"):
        cancel_booking(
            conn, booking_id=booking["id"], user_id=1, session_id="s", now=booking["occurs_at"] + 1
        )
    with pytest.raises(BookingError, match="started"):
        cancel_booking(
            conn, booking_id=booking["id"], user_id=1, session_id="s", now=booking["occurs_at"]
        )
    cancelled = cancel_booking(
        conn, booking_id=booking["id"], user_id=1, session_id="s", now=booking["occurs_at"] - 1
    )
    assert cancelled["status"] == "cancelled"


def test_refuses_a_second_booking_of_the_same_class_date_by_the_same_member():
    conn = fresh_db()
    create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    with pytest.raises(BookingError, match="already"):
        create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)


def test_a_member_can_book_the_same_class_again_for_a_later_date():
    conn = fresh_db()
    first = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    pay_booking(conn, booking_id=first["id"], user_id=1, session_id="s", now=NOW + 1000)
    later = create_booking(
        conn, user_id=1, class_id=1, session_id="s", now=first["occurs_at"] + 1
    )
    assert later["id"] != first["id"]
    assert later["occurs_at"] > first["occurs_at"]
    assert later["occurs_at"] == next_occurrence(TINY_WORLD.classes[0], first["occurs_at"] + 1)
    rows = conn.execute(
        "SELECT status FROM bookings WHERE user_id = 1 AND class_id = 1 ORDER BY id"
    ).fetchall()
    assert [row["status"] for row in rows] == ["paid", "pending"]


def test_refuses_acting_on_someone_elses_booking():
    conn = fresh_db()
    booking = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    with pytest.raises(BookingError):
        pay_booking(conn, booking_id=booking["id"], user_id=2, session_id="s", now=NOW)


def test_refuses_a_booking_for_an_unknown_class():
    conn = fresh_db()
    with pytest.raises(BookingError, match="(?i)not found"):
        create_booking(conn, user_id=1, class_id=99, session_id="s-abc", now=NOW)


def test_rebooking_after_a_cancellation_keeps_the_cancelled_booking_on_record():
    conn = fresh_db()
    first = create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    pay_booking(conn, booking_id=first["id"], user_id=1, session_id="s", now=NOW)
    cancel_booking(conn, booking_id=first["id"], user_id=1, session_id="s", now=NOW + 1000)
    second = create_booking(conn, user_id=1, class_id=1, session_id="s", now=NOW + 2000)
    assert second["id"] != first["id"]
    rows = conn.execute(
        "SELECT id, status FROM bookings WHERE user_id = 1 AND class_id = 1 ORDER BY id"
    ).fetchall()
    assert [row["status"] for row in rows] == ["cancelled", "pending"]


def test_refuses_two_active_bookings_of_the_same_class_date_by_the_same_member():
    conn = fresh_db()
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        insert_bookings(
            conn,
            [
                booked(1, 1, status="pending"),
                booked(2, 1, status="paid", paid_at=NOW),
            ],
        )


def test_allows_the_same_class_on_two_dates_for_the_same_member():
    conn = fresh_db()
    insert_bookings(
        conn,
        [
            booked(1, 1, status="paid", paid_at=NOW),
            booked(2, 1, status="pending", occurs_at=OCCURS + WEEK),
        ],
    )
    rows = conn.execute(
        "SELECT id, occurs_at FROM bookings WHERE user_id = 1 AND class_id = 1 ORDER BY id"
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"id": 1, "occurs_at": OCCURS},
        {"id": 2, "occurs_at": OCCURS + WEEK},
    ]


def test_allows_an_active_booking_alongside_a_cancelled_one():
    conn = fresh_db()
    insert_bookings(
        conn,
        [
            booked(1, 1, status="cancelled", paid_at=NOW, cancelled_at=NOW),
            booked(2, 1, status="pending"),
        ],
    )
    rows = conn.execute(
        "SELECT id, status FROM bookings WHERE user_id = 1 AND class_id = 1 ORDER BY id"
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"id": 1, "status": "cancelled"},
        {"id": 2, "status": "pending"},
    ]


def test_reports_a_double_booking_as_a_conflict():
    conn = fresh_db()
    insert_bookings(
        conn,
        [
            booked(
                1,
                1,
                status="paid",
                paid_at=NOW,
                occurs_at=next_occurrence(TINY_WORLD.classes[0], NOW),
            )
        ],
    )
    with pytest.raises(BookingError) as caught:
        create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    assert caught.value.code == "already_booked"
    assert caught.value.status == 409


def test_a_booking_that_slips_past_the_check_still_comes_back_as_a_conflict(monkeypatch):
    conn = fresh_db()
    insert_bookings(
        conn,
        [
            booked(
                1,
                1,
                status="paid",
                paid_at=NOW,
                occurs_at=next_occurrence(TINY_WORLD.classes[0], NOW),
            )
        ],
    )
    monkeypatch.setattr("app.bookings.assert_can_book", lambda existing: None)
    with pytest.raises(BookingError) as caught:
        create_booking(conn, user_id=1, class_id=1, session_id="s-abc", now=NOW)
    assert caught.value.code == "already_booked"
    assert caught.value.status == 409


AT_ONCE = 24


def crowded_world():
    """Enough studios, classes and members for every thread to book something of its own."""
    studios = [Studio(id=s, name=f"Studio {s}", city="Eastport") for s in range(1, 5)]
    classes = [
        ClassRow(
            id=c,
            studio_id=(c - 1) % 4 + 1,
            title=f"Class {c}",
            price_cents=1800,
            starts_at=OCCURS,
        )
        for c in range(1, AT_ONCE + 1)
    ]
    users = [
        User(id=u, email=f"member{u}@example.com", created_at=NOW - 86_400_000)
        for u in range(1, AT_ONCE + 1)
    ]
    return World(studios=studios, classes=classes, users=users)


def test_bookings_made_at_the_same_moment_each_get_one_started_event():
    conn = open_database(":memory:")
    insert_world(conn, crowded_world())
    together = threading.Barrier(AT_ONCE)
    guard = threading.Lock()
    made = []
    failures = []

    def book(n):
        try:
            together.wait()
            booking = create_booking(conn, user_id=n, class_id=n, session_id=f"s-{n}", now=NOW)
        except BaseException as err:
            with guard:
                failures.append(err)
        else:
            with guard:
                made.append(booking)

    threads = [threading.Thread(target=book, args=(n,)) for n in range(1, AT_ONCE + 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures, failures
    assert len(made) == AT_ONCE
    assert conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()["n"] == AT_ONCE
    started = conn.execute(
        "SELECT booking_id, COUNT(*) AS n FROM events WHERE event_name = 'booking_started' "
        "GROUP BY booking_id"
    ).fetchall()
    assert {row["booking_id"] for row in started} == {booking["id"] for booking in made}
    assert [row["n"] for row in started] == [1] * AT_ONCE
