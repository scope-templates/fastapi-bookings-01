import sqlite3
from typing import Any

from app.reports.range import Range

SQL = """
SELECT strftime('%Y-%m-%d', occurred_at / 1000, 'unixepoch') AS day,
       COUNT(DISTINCT user_id) AS active_users
FROM events
WHERE occurred_at >= :start AND occurred_at < :end AND user_id IS NOT NULL
GROUP BY day
ORDER BY day"""


def daily_actives(conn: sqlite3.Connection, window: Range) -> list[dict[str, Any]]:
    rows = conn.execute(SQL, {"start": window.start, "end": window.end}).fetchall()
    return [dict(row) for row in rows]
