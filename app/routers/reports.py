from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.clock import from_epoch_ms
from app.db import get_db
from app.http import json_response
from app.reports import is_report_name, parse_range, run_report
from app.session import session_from_cookie

router = APIRouter()


def _iso(ms: int) -> str:
    moment = from_epoch_ms(ms)
    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{moment.microsecond // 1000:03d}Z"


@router.get("/api/reports/{name}")
async def report(name: str, request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    if session.user_id is None:
        return json_response({"error": "sign_in_required"}, status_code=401, session=session)
    if not is_report_name(name):
        return json_response({"error": "no_such_report"}, status_code=404, session=session)
    try:
        window = parse_range(request.query_params.get("from"), request.query_params.get("to"))
    except ValueError as err:
        return json_response(
            {"error": "bad_range", "message": str(err)}, status_code=400, session=session
        )
    rows = run_report(get_db(), name, window)
    body = {"report": name, "from": _iso(window.start), "to": _iso(window.end), "rows": rows}
    return json_response(body, session=session)
