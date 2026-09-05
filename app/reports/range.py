import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.clock import DAY, now_ms, to_epoch_ms

DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NO_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$")


@dataclass(frozen=True)
class Range:
    """Half-open in UTC: `start` counts, `end` does not."""

    start: int
    end: int


def _parse_utc(label: str, value: str | None) -> int | None:
    if not value:
        return None
    text = value
    if DATE_ONLY.match(value):
        text = f"{value}T00:00:00+00:00"
    elif NO_OFFSET.match(value):
        text = f"{value}+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as err:
        raise ValueError(f"{label} is not a valid date") from err
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return to_epoch_ms(moment)


def parse_range(from_: str | None = None, to: str | None = None, now: int | None = None) -> Range:
    """Defaults: `to` is now, `from` is thirty days earlier."""
    end = _parse_utc("to", to)
    if end is None:
        end = now if now is not None else now_ms()
    start = _parse_utc("from", from_)
    if start is None:
        start = end - 30 * DAY
    if start >= end:
        raise ValueError("from must be before to")
    return Range(start, end)
