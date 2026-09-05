import sqlite3
from typing import Any

from app.reports.range import Range

SQL = """
WITH views AS (
  SELECT class_id, COUNT(*) AS views
  FROM events
  WHERE event_name = 'class_view' AND class_id IS NOT NULL AND occurred_at >= :start AND occurred_at < :end
  GROUP BY class_id
)
SELECT c.id AS class_id, c.title, c.studio_id,
       COALESCE(v.views, 0) AS views,
       COUNT(b.id) AS paid_bookings,
       COALESCE(SUM(b.price_cents), 0) AS revenue_cents
FROM classes c
LEFT JOIN views v ON v.class_id = c.id
LEFT JOIN bookings b ON b.class_id = c.id
 AND b.paid_at IS NOT NULL AND b.paid_at >= :start AND b.paid_at < :end
GROUP BY c.id
HAVING views > 0 OR paid_bookings > 0
ORDER BY paid_bookings DESC, views DESC, c.id"""


def top_classes(conn: sqlite3.Connection, window: Range) -> list[dict[str, Any]]:
    rows = conn.execute(SQL, {"start": window.start, "end": window.end}).fetchall()
    return [dict(row) for row in rows]
