import time
from datetime import datetime, timedelta, timezone

DAY = 86_400_000
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def to_epoch_ms(moment: datetime) -> int:
    delta = moment.astimezone(timezone.utc) - EPOCH
    return delta.days * DAY + delta.seconds * 1000 + delta.microseconds // 1000


def from_epoch_ms(ms: int) -> datetime:
    return EPOCH + timedelta(milliseconds=ms)
