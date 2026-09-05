import logging
import re
from typing import Any

from fastapi.responses import JSONResponse

from app.bookings import BookingError
from app.session import Session, session_cookie

DIGITS = re.compile(r"^\d+$")
log = logging.getLogger("studio_slot")


def json_response(
    body: Any, *, status_code: int = 200, session: Session | None = None
) -> JSONResponse:
    response = JSONResponse(body, status_code=status_code)
    response.headers["cache-control"] = "private, no-store"
    if session is not None and session.fresh:
        response.headers.append("set-cookie", session_cookie(session))
    return response


def error_response(err: Exception, session: Session | None = None) -> JSONResponse:
    if isinstance(err, BookingError):
        return json_response(
            {"error": err.code, "message": err.message}, status_code=err.status, session=session
        )
    return internal_error_response(err)


def internal_error_response(err: Exception) -> JSONResponse:
    """What the caller gets when something we did not plan for went wrong."""
    log.exception("request failed", exc_info=err)
    return json_response({"error": "internal"}, status_code=500)


def parse_id(value: str) -> int | None:
    return int(value) if DIGITS.match(value) else None
