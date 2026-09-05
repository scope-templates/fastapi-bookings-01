from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictInt, ValidationError

from app.bookings import BookingError, cancel_booking, create_booking, pay_booking
from app.clock import now_ms
from app.db import get_db
from app.http import error_response, json_response, parse_id
from app.session import session_from_cookie

router = APIRouter()

LIST_SQL = """SELECT b.*, c.title, s.name AS studio
FROM bookings b
JOIN classes c ON c.id = b.class_id
JOIN studios s ON s.id = b.studio_id
WHERE b.user_id = ?
ORDER BY b.created_at DESC, b.id DESC"""


class BookingRequest(BaseModel):
    class_id: StrictInt = Field(gt=0)


@router.post("/api/bookings")
async def book(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    if session.user_id is None:
        return json_response({"error": "sign_in_required"}, status_code=401, session=session)
    try:
        payload = await request.json()
        wanted = BookingRequest.model_validate(payload)
    except (ValidationError, ValueError):
        return json_response({"error": "invalid_body"}, status_code=400, session=session)
    try:
        booking = create_booking(
            get_db(),
            user_id=session.user_id,
            class_id=wanted.class_id,
            session_id=session.session_id,
            now=now_ms(),
        )
    except BookingError as err:
        return error_response(err, session)
    return json_response(booking, status_code=201, session=session)


@router.get("/api/bookings")
async def mine(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    if session.user_id is None:
        return json_response({"error": "sign_in_required"}, status_code=401, session=session)
    rows = get_db().execute(LIST_SQL, (session.user_id,)).fetchall()
    return json_response([dict(row) for row in rows], session=session)


@router.post("/api/bookings/{booking_id}/pay")
async def pay(booking_id: str, request: Request) -> JSONResponse:
    return _act(pay_booking, booking_id, request)


@router.post("/api/bookings/{booking_id}/cancel")
async def cancel(booking_id: str, request: Request) -> JSONResponse:
    return _act(cancel_booking, booking_id, request)


def _act(action, booking_id: str, request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    if session.user_id is None:
        return json_response({"error": "sign_in_required"}, status_code=401, session=session)
    wanted = parse_id(booking_id)
    if wanted is None:
        return json_response({"error": "invalid_id"}, status_code=400, session=session)
    try:
        booking = action(
            get_db(),
            booking_id=wanted,
            user_id=session.user_id,
            session_id=session.session_id,
            now=now_ms(),
        )
    except BookingError as err:
        return error_response(err, session)
    return json_response(booking, session=session)
