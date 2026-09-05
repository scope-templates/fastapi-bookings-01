import sqlite3
from dataclasses import asdict

import pytest

from app.db import open_database
from app.world import Booking, insert_bookings, insert_world
from tests.tiny_world import TINY_WORLD


def test_inserts_every_row_with_the_given_ids():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    assert conn.execute("SELECT COUNT(*) AS n FROM classes").fetchone()["n"] == 2
    assert [row["id"] for row in conn.execute("SELECT id FROM users ORDER BY id")] == [1, 2]
    assert dict(conn.execute("SELECT * FROM studios WHERE id = 1").fetchone()) == asdict(
        TINY_WORLD.studios[0]
    )
    assert dict(conn.execute("SELECT * FROM classes WHERE id = 2").fetchone()) == asdict(
        TINY_WORLD.classes[1]
    )
    assert dict(conn.execute("SELECT * FROM users WHERE id = 2").fetchone()) == asdict(
        TINY_WORLD.users[1]
    )


def test_inserts_bookings():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    insert_bookings(
        conn,
        [
            Booking(
                id=1,
                user_id=1,
                class_id=1,
                studio_id=1,
                status="paid",
                created_at=10,
                paid_at=20,
                cancelled_at=None,
                price_cents=1800,
                occurs_at=30,
            )
        ],
    )
    assert conn.execute("SELECT status FROM bookings WHERE id = 1").fetchone()["status"] == "paid"


def test_refuses_a_booking_for_a_member_who_does_not_exist():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert_bookings(
            conn,
            [
                Booking(
                    id=2,
                    user_id=99,
                    class_id=1,
                    studio_id=1,
                    status="pending",
                    created_at=10,
                    paid_at=None,
                    cancelled_at=None,
                    price_cents=1800,
                    occurs_at=30,
                )
            ],
        )


def test_takes_plain_dictionaries_too():
    conn = open_database(":memory:")
    insert_world(
        conn,
        {
            "studios": [{"id": 1, "name": "Harbor Yoga", "city": "Eastport"}],
            "classes": [],
            "users": [],
        },
    )
    assert conn.execute("SELECT city FROM studios WHERE id = 1").fetchone()["city"] == "Eastport"
