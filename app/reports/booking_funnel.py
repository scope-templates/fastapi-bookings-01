import sqlite3
from typing import Any

from app.reports.range import Range

SQL = """
WITH viewed AS (
  SELECT session_id, studio_id, MIN(occurred_at) AS t
  FROM events
  WHERE event_name = 'class_view' AND occurred_at >= :start AND occurred_at < :end
  GROUP BY session_id, studio_id
),
started AS (
  SELECT v.session_id, v.studio_id, MIN(e.occurred_at) AS t
  FROM viewed v
  JOIN events e ON e.session_id = v.session_id AND e.studio_id = v.studio_id
   AND e.event_name = 'booking_started' AND e.occurred_at > v.t AND e.occurred_at < :end
  GROUP BY v.session_id, v.studio_id
),
paid AS (
  SELECT s.session_id, s.studio_id
  FROM started s
  JOIN events e ON e.session_id = s.session_id AND e.studio_id = s.studio_id
   AND e.event_name = 'booking_paid' AND e.occurred_at > s.t AND e.occurred_at < :end
  GROUP BY s.session_id, s.studio_id
)
SELECT st.id AS studio_id, st.name AS studio,
       (SELECT COUNT(*) FROM viewed WHERE studio_id = st.id) AS viewed,
       (SELECT COUNT(*) FROM started WHERE studio_id = st.id) AS started,
       (SELECT COUNT(*) FROM paid WHERE studio_id = st.id) AS paid
FROM studios st
WHERE viewed > 0
ORDER BY st.id"""


def booking_funnel(conn: sqlite3.Connection, window: Range) -> list[dict[str, Any]]:
    rows = conn.execute(SQL, {"start": window.start, "end": window.end}).fetchall()
    return [dict(row) for row in rows]
