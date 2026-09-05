import sqlite3
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable, Mapping, Sequence

from app.db import transaction

BookingStatus = str


@dataclass(frozen=True)
class Studio:
    id: int
    name: str
    city: str


@dataclass(frozen=True)
class ClassRow:
    id: int
    studio_id: int
    title: str
    price_cents: int
    starts_at: int


@dataclass(frozen=True)
class User:
    id: int
    email: str
    created_at: int


@dataclass
class Booking:
    id: int
    user_id: int
    class_id: int
    studio_id: int
    status: BookingStatus
    created_at: int
    paid_at: int | None
    cancelled_at: int | None
    price_cents: int
    occurs_at: int


@dataclass
class World:
    studios: list[Studio] = field(default_factory=list)
    classes: list[ClassRow] = field(default_factory=list)
    users: list[User] = field(default_factory=list)


def as_row(value: Any) -> dict[str, Any]:
    """Rows arrive either as one of the dataclasses above or as plain dictionaries."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return dict(value)


def _part(world: Any, name: str) -> Sequence[Any]:
    return world[name] if isinstance(world, Mapping) else getattr(world, name)


STUDIO_SQL = "INSERT INTO studios (id, name, city) VALUES (:id, :name, :city)"
CLASS_SQL = """INSERT INTO classes (id, studio_id, title, price_cents, starts_at)
VALUES (:id, :studio_id, :title, :price_cents, :starts_at)"""
USER_SQL = "INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"
BOOKING_SQL = """INSERT INTO bookings (id, user_id, class_id, studio_id, status, created_at, paid_at, cancelled_at, price_cents, occurs_at)
VALUES (:id, :user_id, :class_id, :studio_id, :status, :created_at, :paid_at, :cancelled_at, :price_cents, :occurs_at)"""


def insert_world(conn: sqlite3.Connection, world: Any) -> None:
    with transaction(conn):
        conn.executemany(STUDIO_SQL, [as_row(s) for s in _part(world, "studios")])
        conn.executemany(CLASS_SQL, [as_row(c) for c in _part(world, "classes")])
        conn.executemany(USER_SQL, [as_row(u) for u in _part(world, "users")])


def insert_bookings(conn: sqlite3.Connection, rows: Iterable[Any]) -> None:
    with transaction(conn):
        conn.executemany(BOOKING_SQL, [as_row(r) for r in rows])
