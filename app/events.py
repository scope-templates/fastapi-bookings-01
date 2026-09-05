import json
import sqlite3
from typing import Annotated, Any, Iterable, Literal, Mapping, get_args

from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr, TypeAdapter

from app.db import transaction
from app.world import as_row

EventName = Literal[
    "page_view",
    "class_view",
    "search",
    "booking_started",
    "booking_paid",
    "booking_cancelled",
    "signup",
    "login",
]
EVENT_NAMES: tuple[str, ...] = get_args(EventName)

PropertyValue = (
    StrictBool | StrictInt | Annotated[StrictFloat, Field(allow_inf_nan=False)] | StrictStr | None
)


class Event(BaseModel):
    occurred_at: int = Field(ge=0)
    user_id: int | None = Field(default=None, gt=0)
    session_id: str = Field(min_length=1, max_length=64)
    studio_id: int | None = Field(default=None, gt=0)
    booking_id: int | None = Field(default=None, gt=0)
    class_id: int | None = Field(default=None, gt=0)
    event_name: EventName
    properties: dict[str, PropertyValue] = Field(default_factory=dict)


EVENT_BATCH = TypeAdapter(Annotated[list[Event], Field(min_length=1, max_length=1000)])


def canonical_json(value: Any) -> str:
    """One spelling per value: keys in order, no whitespace, a stated nothing still stated."""
    if isinstance(value, Mapping):
        pairs = [
            f"{json.dumps(k, ensure_ascii=False)}:{canonical_json(v)}"
            for k, v in sorted(value.items())
        ]
        return "{" + ",".join(pairs) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


INSERT = """INSERT INTO events (occurred_at, user_id, session_id, studio_id, booking_id, class_id, event_name, properties)
VALUES (:occurred_at, :user_id, :session_id, :studio_id, :booking_id, :class_id, :event_name, :properties)"""

COLUMNS = (
    "occurred_at",
    "user_id",
    "session_id",
    "studio_id",
    "booking_id",
    "class_id",
    "event_name",
    "properties",
)


def _bind(event: Any) -> dict[str, Any]:
    row = event.model_dump() if isinstance(event, Event) else as_row(event)
    bound = {name: row.get(name) for name in COLUMNS}
    bound["properties"] = canonical_json(row.get("properties") or {})
    return bound


def ingest_events(conn: sqlite3.Connection, events: Iterable[Any]) -> int:
    rows = [_bind(e) for e in events]
    with transaction(conn):
        conn.executemany(INSERT, rows)
    return len(rows)
