from datetime import datetime, timezone

from app.clock import to_epoch_ms


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> int:
    """Epoch milliseconds for a UTC wall clock."""
    return to_epoch_ms(datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc))
