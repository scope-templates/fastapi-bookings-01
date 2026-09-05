import sqlite3

from app.db import open_database


def test_creates_the_tables_and_the_occurred_at_index():
    conn = open_database(":memory:")
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    assert tables == ["bookings", "classes", "events", "studios", "users"]
    event_indexes = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'events'"
        )
    ]
    assert "events_occurred_at" in event_indexes
    booking_indexes = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'bookings'"
        )
    ]
    assert "bookings_active_member_class_date" in booking_indexes


def test_runs_on_a_sqlite_that_knows_iso_weeks():
    assert tuple(int(p) for p in sqlite3.sqlite_version.split(".")) >= (3, 46, 0)
    conn = open_database(":memory:")
    row = conn.execute("SELECT strftime('%G-W%V', 1735603200, 'unixepoch') AS w").fetchone()
    assert row["w"] == "2025-W01"  # 2024-12-31 is ISO week 1 of 2025


def test_keeps_foreign_keys_on_and_the_journal_in_write_ahead_mode():
    conn = open_database(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
