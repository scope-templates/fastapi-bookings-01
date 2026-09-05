from dataclasses import replace
from hashlib import sha256

import pytest

from app.classes import next_occurrence
from app.events import canonical_json
from app.world import ClassRow, as_row
from scripts.generate import Options, generate
from tests.helpers import utc

DAY = 86_400_000
SMALL = Options(
    events=2000, seed=7, end=utc(2026, 8, 31), studios=4, classes_per_studio=(3, 5), users=200
)
SMALL_FINGERPRINT = "b54c193867bb5f9b3fb25ca6eb095445a75a4f562754ce45f9fd38ea4c530621"


def fingerprint(generated):
    digest = sha256()
    for event in generated.events:
        digest.update(canonical_json(event).encode())
    for booking in generated.bookings:
        digest.update(canonical_json(as_row(booking)).encode())
    return digest.hexdigest()


def test_is_deterministic_for_the_same_inputs():
    assert fingerprint(generate(SMALL)) == fingerprint(generate(SMALL))
    assert fingerprint(generate(SMALL)) == SMALL_FINGERPRINT
    assert fingerprint(generate(replace(SMALL, seed=8))) != fingerprint(generate(SMALL))


def test_rejects_a_class_count_range_no_studio_could_satisfy():
    with pytest.raises(ValueError):
        generate(replace(SMALL, classes_per_studio=(0, 5)))


def test_rejects_an_event_budget_with_no_room_for_a_single_event():
    with pytest.raises(ValueError):
        generate(replace(SMALL, events=0))


def test_never_exceeds_the_cap_and_drops_a_visit_whole():
    generated = generate(SMALL)
    assert len(generated.events) <= 2000
    assert len(generated.events) > 1900
    last = generated.events[-1]
    visit = [e for e in generated.events if e["session_id"] == last["session_id"]]
    assert visit[0]["event_name"] in ("page_view", "signup", "login")


def test_keeps_every_event_inside_the_window_and_every_booking_event_on_a_real_booking():
    generated = generate(SMALL)
    start = SMALL.end - 548 * DAY
    assert all(start <= e["occurred_at"] < SMALL.end for e in generated.events)
    ids = {b.id for b in generated.bookings}
    booking_events = [e for e in generated.events if e["event_name"].startswith("booking_")]
    assert booking_events
    assert all(e["booking_id"] in ids for e in booking_events)
    dates = {f"{b.user_id}:{b.class_id}:{b.occurs_at}" for b in generated.bookings}
    assert len(dates) == len(generated.bookings)


def test_orders_every_visit_by_time_with_booking_stages_at_least_twenty_seconds_apart():
    generated = generate(SMALL)
    visits: dict[str, list[dict]] = {}
    for event in generated.events:
        visits.setdefault(event["session_id"], []).append(event)
    for events in visits.values():
        for earlier, later in zip(events, events[1:]):
            assert later["occurred_at"] > earlier["occurred_at"]
            if later["event_name"].startswith("booking_") and earlier["event_name"].startswith(
                "booking_"
            ):
                assert later["occurred_at"] - earlier["occurred_at"] >= 20_000


def test_weights_recent_days_more_heavily():
    generated = generate(replace(SMALL, events=20000))
    middle = SMALL.end - 274 * DAY
    late = sum(1 for e in generated.events if e["occurred_at"] >= middle)
    assert late / len(generated.events) > 0.6


def test_matches_booking_rows_to_booking_events():
    generated = generate(SMALL)
    for booking in generated.bookings:
        names = [e["event_name"] for e in generated.events if e["booking_id"] == booking.id]
        assert names[0] == "booking_started"
        if booking.status == "pending":
            assert names == ["booking_started"]
        if booking.status == "paid":
            assert names[:2] == ["booking_started", "booking_paid"]
        if booking.status == "cancelled":
            assert names == ["booking_started", "booking_paid", "booking_cancelled"]


def test_books_the_next_date_of_the_class_and_cancels_before_it_comes_round():
    generated = generate(SMALL)
    by_id = {c.id: c for c in generated.world.classes}
    for booking in generated.bookings:
        assert booking.occurs_at == next_occurrence(by_id[booking.class_id], booking.created_at)
    cancelled = [b for b in generated.bookings if b.status == "cancelled"]
    assert cancelled
    for booking in cancelled:
        assert booking.cancelled_at < booking.occurs_at


def test_records_a_signup_for_exactly_the_members_who_joined_inside_the_window_and_were_met():
    generated = generate(SMALL)
    start = SMALL.end - 548 * DAY
    signed_up_at: dict[int, int] = {}
    for event in generated.events:
        if event["event_name"] != "signup":
            continue
        assert event["user_id"] not in signed_up_at
        signed_up_at[event["user_id"]] = event["occurred_at"]
    assert signed_up_at
    met = {e["user_id"] for e in generated.events if e["user_id"] is not None}
    joined_in_window = [
        u.id for u in generated.world.users if u.created_at >= start and u.id in met
    ]
    assert sorted(signed_up_at) == sorted(joined_in_window)
    by_id = {u.id: u for u in generated.world.users}
    for user_id, at in signed_up_at.items():
        assert by_id[user_id].created_at == at
    for event in generated.events:
        if event["user_id"] in signed_up_at:
            assert event["occurred_at"] >= signed_up_at[event["user_id"]]
    for user in generated.world.users:
        if user.created_at < start:
            assert user.id not in signed_up_at


def test_next_occurrence_steps_back_in_whole_weeks():
    klass = ClassRow(
        id=1, studio_id=1, title="Wheel Basics", price_cents=2400, starts_at=utc(2026, 9, 8, 7)
    )
    assert next_occurrence(klass, utc(2026, 8, 20)) == utc(2026, 8, 25, 7)
    assert next_occurrence(klass, utc(2026, 9, 8, 7)) == utc(2026, 9, 15, 7)
