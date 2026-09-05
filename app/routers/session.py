from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.clock import now_ms
from app.db import get_db
from app.events import ingest_events
from app.http import json_response
from app.session import session_from_cookie, user_cookie

router = APIRouter()


async def _body(request: Request) -> dict:
    try:
        parsed = await request.json()
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post("/api/session")
async def sign_in(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    wanted = (await _body(request)).get("user_id")
    user_id = wanted if isinstance(wanted, int) and not isinstance(wanted, bool) else None
    if user_id is not None:
        conn = get_db()
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            return json_response({"error": "no_such_user"}, status_code=404, session=session)
        ingest_events(
            conn,
            [
                {
                    "occurred_at": now_ms(),
                    "user_id": user_id,
                    "session_id": session.session_id,
                    "studio_id": None,
                    "booking_id": None,
                    "class_id": None,
                    "event_name": "login",
                    "properties": {"device": "web"},
                }
            ],
        )
    response = json_response({"user_id": user_id}, session=session)
    response.headers.append("set-cookie", user_cookie(user_id))
    return response
