import math
from typing import Any, Mapping, Sequence

from app.clock import from_epoch_ms
from app.reports.range import Range
from app.world import as_row


def iso_week(ms: int) -> str:
    """ISO 8601 week label, e.g. 2026-W01, computed in UTC."""
    year, week, _ = from_epoch_ms(ms).isocalendar()
    return f"{year}-W{week:02d}"


def part(value: Any, name: str) -> Sequence[Any]:
    return value[name] if isinstance(value, Mapping) else getattr(value, name)


def _half_up(value: float, places: int) -> float:
    scale = 10**places
    return math.floor(value * scale + 0.5) / scale


def expected_reports(sample: Any, window: Range) -> dict[str, list[dict[str, Any]]]:
    world = part(sample, "world")
    studio_name = {s["id"]: s["name"] for s in (as_row(s) for s in part(world, "studios"))}
    classes = [as_row(c) for c in part(world, "classes")]
    bookings = [as_row(b) for b in part(sample, "bookings")]
    events = [as_row(e) for e in part(sample, "events")]
    inside = [e for e in events if window.start <= e["occurred_at"] < window.end]

    by_day: dict[str, set[int]] = {}
    for event in inside:
        if event["user_id"] is None:
            continue
        day = from_epoch_ms(event["occurred_at"]).strftime("%Y-%m-%d")
        by_day.setdefault(day, set()).add(event["user_id"])
    daily_actives = [
        {"day": day, "active_users": len(by_day[day])} for day in sorted(by_day)
    ]

    def key(event: dict[str, Any]) -> tuple[str, int]:
        return (event["session_id"], event["studio_id"])

    viewed_at: dict[tuple[str, int], int] = {}
    for event in inside:
        if event["event_name"] == "class_view" and event["studio_id"] is not None:
            k = key(event)
            viewed_at[k] = min(viewed_at.get(k, event["occurred_at"]), event["occurred_at"])
    started_at: dict[tuple[str, int], int] = {}
    for event in inside:
        k = key(event)
        if event["event_name"] == "booking_started" and k in viewed_at:
            if event["occurred_at"] > viewed_at[k]:
                started_at[k] = min(started_at.get(k, event["occurred_at"]), event["occurred_at"])
    paid_keys: set[tuple[str, int]] = set()
    for event in inside:
        k = key(event)
        if event["event_name"] == "booking_paid" and k in started_at:
            if event["occurred_at"] > started_at[k]:
                paid_keys.add(k)

    funnel: dict[int, dict[str, int]] = {}

    def bump(k: tuple[str, int], stage: str) -> None:
        studio_id = k[1]
        funnel.setdefault(studio_id, {"viewed": 0, "started": 0, "paid": 0})[stage] += 1

    for k in viewed_at:
        bump(k, "viewed")
    for k in started_at:
        bump(k, "started")
    for k in paid_keys:
        bump(k, "paid")
    booking_funnel = [
        {"studio_id": studio_id, "studio": studio_name[studio_id], **funnel[studio_id]}
        for studio_id in sorted(funnel)
    ]

    views: dict[int, int] = {}
    for event in inside:
        if event["event_name"] == "class_view" and event["class_id"] is not None:
            views[event["class_id"]] = views.get(event["class_id"], 0) + 1
    paid_inside = [
        b
        for b in bookings
        if b["paid_at"] is not None and window.start <= b["paid_at"] < window.end
    ]
    top_classes = []
    for klass in classes:
        paid = [b for b in paid_inside if b["class_id"] == klass["id"]]
        row = {
            "class_id": klass["id"],
            "title": klass["title"],
            "studio_id": klass["studio_id"],
            "views": views.get(klass["id"], 0),
            "paid_bookings": len(paid),
            "revenue_cents": sum(b["price_cents"] for b in paid),
        }
        if row["views"] > 0 or row["paid_bookings"] > 0:
            top_classes.append(row)
    top_classes.sort(key=lambda r: (-r["paid_bookings"], -r["views"], r["class_id"]))

    cohorts: dict[tuple[int, str], dict[str, Any]] = {}
    for booking in paid_inside:
        week = iso_week(booking["paid_at"])
        cohort = cohorts.setdefault(
            (booking["studio_id"], week),
            {"studio_id": booking["studio_id"], "week": week, "paid": 0, "cancelled": 0},
        )
        cohort["paid"] += 1
        if booking["cancelled_at"] is not None and booking["cancelled_at"] < window.end:
            cohort["cancelled"] += 1
    cancellation_rate = [
        {
            "studio_id": cohort["studio_id"],
            "studio": studio_name[cohort["studio_id"]],
            "week": cohort["week"],
            "paid_bookings": cohort["paid"],
            "cancelled": cohort["cancelled"],
            "cancellation_rate": _half_up(cohort["cancelled"] / cohort["paid"], 4),
        }
        for cohort in sorted(cohorts.values(), key=lambda c: (c["studio_id"], c["week"]))
    ]

    return {
        "daily_actives": daily_actives,
        "booking_funnel": booking_funnel,
        "top_classes": top_classes,
        "cancellation_rate": cancellation_rate,
    }
