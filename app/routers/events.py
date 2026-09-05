from typing import Annotated, Any, Literal, Mapping

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.clock import now_ms
from app.db import get_db
from app.events import PropertyValue, ingest_events
from app.http import json_response
from app.session import session_from_cookie

router = APIRouter()

# The names a page may report. Paying and cancelling are recorded by the booking service itself.
BrowsingEvent = Literal["page_view", "class_view", "search", "signup", "login"]

CLOCK_SLACK_MS = 60_000


class IncomingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: BrowsingEvent
    studio_id: int | None = Field(default=None, gt=0)
    class_id: int | None = Field(default=None, gt=0)
    occurred_at: int | None = Field(default=None, ge=0)
    properties: dict[str, PropertyValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def occurred_at_is_a_time_when_given(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "occurred_at" in data and data["occurred_at"] is None:
            raise ValueError("occurred_at must say when, or be left out")
        return data

    @field_validator("occurred_at")
    @classmethod
    def within_the_clock_slack(cls, value: int | None) -> int | None:
        if value is not None and value > now_ms() + CLOCK_SLACK_MS:
            raise ValueError("occurred_at is in the future")
        return value


INCOMING = TypeAdapter(Annotated[list[IncomingEvent], Field(min_length=1, max_length=1000)])


@router.post("/api/events")
async def record(request: Request) -> JSONResponse:
    session = session_from_cookie(request.headers.get("cookie"))
    try:
        payload = await request.json()
    except Exception:
        payload = None
    try:
        incoming = INCOMING.validate_python(payload)
    except ValidationError as err:
        issues = err.errors(include_url=False, include_context=False, include_input=False)
        return json_response(
            {"error": "invalid_events", "issues": issues}, status_code=400, session=session
        )

    conn = get_db()
    studio_ids = list(dict.fromkeys(e.studio_id for e in incoming if e.studio_id is not None))
    if studio_ids:
        placeholders = ", ".join("?" for _ in studio_ids)
        known = {
            row["id"]
            for row in conn.execute(f"SELECT id FROM studios WHERE id IN ({placeholders})", studio_ids)
        }
        unknown = next((studio_id for studio_id in studio_ids if studio_id not in known), None)
        if unknown is not None:
            return json_response(
                {"error": "unknown_studio", "studio_id": unknown}, status_code=400, session=session
            )

    now = now_ms()
    accepted = ingest_events(
        conn,
        [
            {
                "occurred_at": e.occurred_at if e.occurred_at is not None else now,
                "user_id": session.user_id,
                "session_id": session.session_id,
                "studio_id": e.studio_id,
                "booking_id": None,
                "class_id": e.class_id,
                "event_name": e.event_name,
                "properties": e.properties,
            }
            for e in incoming
        ],
    )
    return json_response({"accepted": accepted}, status_code=202, session=session)
