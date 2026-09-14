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


def test_iso_weeks_come_out_right_on_the_sqlite_we_have():
    from app.reports.cancellation_rate import ISO_WEEK

    conn = open_database(":memory:")
    sql = f"SELECT {ISO_WEEK} AS w FROM (SELECT :paid_at AS paid_at) b"
    assert conn.execute(sql, {"paid_at": 1735603200 * 1000}).fetchone()["w"] == "2025-W01"  # 2024-12-31
    assert conn.execute(sql, {"paid_at": 1798761600 * 1000}).fetchone()["w"] == "2026-W53"  # 2027-01-01
    assert conn.execute(sql, {"paid_at": 1799107200 * 1000}).fetchone()["w"] == "2027-W01"  # 2027-01-05


def test_keeps_foreign_keys_on_and_the_journal_in_write_ahead_mode():
    conn = open_database(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
