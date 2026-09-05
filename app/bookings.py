import sqlite3
from typing import Any

from app.classes import next_occurrence
from app.db import transaction
from app.events import ingest_events


class BookingError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def assert_can_book(existing: dict[str, Any] | None) -> None:
    if existing is not None:
        raise BookingError("already_booked", "This class date is already booked")


def assert_can_pay(booking: dict[str, Any]) -> None:
    if booking["status"] != "pending":
        raise BookingError("not_pending", "Only a pending booking can be paid")


def assert_can_cancel(booking: dict[str, Any], now: int) -> None:
    if booking["status"] != "paid":
        raise BookingError("not_paid", "Only a paid booking can be cancelled")
    if now >= booking["occurs_at"]:
        raise BookingError("class_started", "The class has already started")


def _get_class(conn: sqlite3.Connection, class_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    if row is None:
        raise BookingError("no_such_class", "Class not found", 404)
    return dict(row)


def _get_own_booking(conn: sqlite3.Connection, booking_id: int, user_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row is None or row["user_id"] != user_id:
        raise BookingError("no_such_booking", "Booking not found", 404)
    return dict(row)


def _read(conn: sqlite3.Connection, booking_id: int) -> dict[str, Any]:
    return dict(conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone())


def create_booking(
    conn: sqlite3.Connection, *, user_id: int, class_id: int, session_id: str, now: int
) -> dict[str, Any]:
    klass = _get_class(conn, class_id)
    occurs_at = next_occurrence(klass, now)
    existing = conn.execute(
        "SELECT * FROM bookings WHERE user_id = ? AND class_id = ? AND occurs_at = ? AND status != 'cancelled'",
        (user_id, class_id, occurs_at),
    ).fetchone()
    assert_can_book(existing)
    try:
        with transaction(conn):
            cursor = conn.execute(
                """INSERT INTO bookings (user_id, class_id, studio_id, status, created_at, paid_at, cancelled_at, price_cents, occurs_at)
                   VALUES (?, ?, ?, 'pending', ?, NULL, NULL, ?, ?)""",
                (user_id, klass["id"], klass["studio_id"], now, klass["price_cents"], occurs_at),
            )
            booking_id = int(cursor.lastrowid)
            ingest_events(
                conn,
                [
                    {
                        "occurred_at": now,
                        "user_id": user_id,
                        "session_id": session_id,
                        "studio_id": klass["studio_id"],
                        "booking_id": booking_id,
                        "class_id": klass["id"],
                        "event_name": "booking_started",
                        "properties": {"class_id": klass["id"], "price_cents": klass["price_cents"]},
                    }
                ],
            )
            return _read(conn, booking_id)
    except sqlite3.IntegrityError as err:
        if err.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
            raise BookingError("already_booked", "This class date is already booked") from err
        raise


def pay_booking(
    conn: sqlite3.Connection, *, booking_id: int, user_id: int, session_id: str, now: int
) -> dict[str, Any]:
    booking = _get_own_booking(conn, booking_id, user_id)
    assert_can_pay(booking)
    with transaction(conn):
        conn.execute("UPDATE bookings SET status = 'paid', paid_at = ? WHERE id = ?", (now, booking["id"]))
        ingest_events(conn, [_booking_event(booking, "booking_paid", session_id, user_id, now)])
        return _read(conn, booking["id"])


def cancel_booking(
    conn: sqlite3.Connection, *, booking_id: int, user_id: int, session_id: str, now: int
) -> dict[str, Any]:
    booking = _get_own_booking(conn, booking_id, user_id)
    assert_can_cancel(booking, now)
    with transaction(conn):
        conn.execute(
            "UPDATE bookings SET status = 'cancelled', cancelled_at = ? WHERE id = ?", (now, booking["id"])
        )
        ingest_events(conn, [_booking_event(booking, "booking_cancelled", session_id, user_id, now)])
        return _read(conn, booking["id"])


def _booking_event(
    booking: dict[str, Any], event_name: str, session_id: str, user_id: int, now: int
) -> dict[str, Any]:
    return {
        "occurred_at": now,
        "user_id": user_id,
        "session_id": session_id,
        "studio_id": booking["studio_id"],
        "booking_id": booking["id"],
        "class_id": booking["class_id"],
        "event_name": event_name,
        "properties": {"class_id": booking["class_id"], "price_cents": booking["price_cents"]},
    }
