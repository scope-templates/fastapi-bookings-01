import sqlite3
from typing import Any

from app.reports.range import Range

# The ISO week a payment falls in, spelled out from the Thursday of that week so it reads the same
# on the older SQLite the production host runs as on a new one (%G and %V only arrived in 3.46).
ISO_THURSDAY = "date(b.paid_at / 1000, 'unixepoch', '-3 days', 'weekday 4')"
ISO_WEEK = (
    f"strftime('%Y', {ISO_THURSDAY}) || '-W' || "
    f"printf('%02d', (strftime('%j', {ISO_THURSDAY}) - 1) / 7 + 1)"
)

CANCELLED = "CASE WHEN b.cancelled_at IS NOT NULL AND b.cancelled_at < :end THEN 1 ELSE 0 END"

SQL = f"""
SELECT b.studio_id, st.name AS studio,
       {ISO_WEEK} AS week,
       COUNT(*) AS paid_bookings,
       SUM({CANCELLED}) AS cancelled,
       ROUND(1.0 * SUM({CANCELLED}) / COUNT(*), 4) AS cancellation_rate
FROM bookings b
JOIN studios st ON st.id = b.studio_id
WHERE b.paid_at IS NOT NULL AND b.paid_at >= :start AND b.paid_at < :end
GROUP BY b.studio_id, week
ORDER BY b.studio_id, week"""


def cancellation_rate(conn: sqlite3.Connection, window: Range) -> list[dict[str, Any]]:
    rows = conn.execute(SQL, {"start": window.start, "end": window.end}).fetchall()
    return [dict(row) for row in rows]
