import sqlite3
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.classes import next_occurrence
from app.clock import now_ms
from app.db import get_db
from app.events import ingest_events
from app.http import json_response, parse_id
from app.session import Session, session_from_cookie

router = APIRouter()

STUDIOS_SQL = "SELECT id, name, city FROM studios ORDER BY name"

CLASSES_SQL = """SELECT c.id, c.studio_id, s.name AS studio, c.title, c.price_cents, c.starts_at
FROM classes c
JOIN studios s ON s.id = c.studio_id
ORDER BY s.name, c.id"""

ONE_CLASS_SQL = """SELECT c.id, c.studio_id, s.name AS studio, c.title, c.price_cents, c.starts_at
FROM classes c
JOIN studios s ON s.id = c.studio_id
WHERE c.id = ?"""


def _listed(klass: dict[str, Any], now: int) -> dict[str, Any]:
    """A class as a member browsing sees it: what it costs and when it next runs."""
    return {
        "id": klass["id"],
        "studio_id": klass["studio_id"],
        "studio": klass["studio"],
        "title": klass["title"],
        "price_cents": klass["price_cents"],
        "next_on": next_occurrence(klass, now),
    }


def _all_classes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(CLASSES_SQL)]


@router.get("/api/studios")
async def studios(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    conn = get_db()
    now = now_ms()
    timetables: dict[int, list[dict[str, Any]]] = {}
    for klass in _all_classes(conn):
        timetables.setdefault(klass["studio_id"], []).append(
            {
                "id": klass["id"],
                "title": klass["title"],
                "price_cents": klass["price_cents"],
                "next_on": next_occurrence(klass, now),
            }
        )
    listing = [
        {**dict(studio), "classes": timetables.get(studio["id"], [])}
        for studio in conn.execute(STUDIOS_SQL)
    ]
    return json_response(listing, session=session)


@router.get("/api/classes")
async def classes(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    conn = get_db()
    now = now_ms()
    query = (request.query_params.get("q") or "").strip()
    found = _all_classes(conn)
    if query:
        wanted = query.lower()
        found = [klass for klass in found if wanted in klass["title"].lower()]
        _record_search(conn, session, query, now)
    return json_response([_listed(klass, now) for klass in found], session=session)


@router.get("/api/classes/{class_id}")
async def one_class(class_id: str, request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    wanted = parse_id(class_id)
    row = None if wanted is None else get_db().execute(ONE_CLASS_SQL, (wanted,)).fetchone()
    if row is None:
        return json_response({"error": "no_such_class"}, status_code=404, session=session)
    return json_response(_listed(dict(row), now_ms()), session=session)


def _record_search(conn: sqlite3.Connection, session: Session, query: str, now: int) -> None:
    ingest_events(
        conn,
        [
            {
                "occurred_at": now,
                "user_id": session.user_id,
                "session_id": session.session_id,
                "studio_id": None,
                "booking_id": None,
                "class_id": None,
                "event_name": "search",
                "properties": {"query": query},
            }
        ],
    )
