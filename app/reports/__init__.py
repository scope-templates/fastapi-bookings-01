import sqlite3
from typing import Any, Callable

from app.reports.booking_funnel import booking_funnel
from app.reports.cancellation_rate import cancellation_rate
from app.reports.daily_actives import daily_actives
from app.reports.range import Range, parse_range
from app.reports.top_classes import top_classes

Report = Callable[[sqlite3.Connection, Range], list[dict[str, Any]]]

REPORTS: dict[str, Report] = {
    "daily_actives": daily_actives,
    "booking_funnel": booking_funnel,
    "top_classes": top_classes,
    "cancellation_rate": cancellation_rate,
}


def is_report_name(name: str) -> bool:
    return name in REPORTS


def run_report(conn: sqlite3.Connection, name: str, window: Range) -> list[dict[str, Any]]:
    return REPORTS[name](conn, window)


__all__ = [
    "REPORTS",
    "Range",
    "is_report_name",
    "parse_range",
    "run_report",
]
