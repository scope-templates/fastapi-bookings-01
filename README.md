# Studio Slot

Class booking for independent studios. Studios list their weekly classes; members browse, book a
class for its next date, pay, and can cancel until the class starts. The reports show how members
find and book classes.

## Running

    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload

The app keeps its data in a SQLite file at `data/studio-slot.sqlite` (set `DATABASE_PATH` to use
another location). On first start it loads a small bundled sample so the endpoints have something to
serve. Sign in as a sample member with `POST /api/session` to book. `python scripts/seed.py`
generates a larger sample; see `scripts/seed.py` for its options.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/session` | Sign in as a member (`{"user_id": 1}`) or out (`{}`) |
| POST | `/api/events` | Record activity for the current session (page views, searches, class views, sign-ins) |
| GET | `/api/studios` | Every studio, with its classes and the date each next runs |
| GET | `/api/classes?q=` | Classes whose title matches `q`, or all of them when it is empty |
| GET | `/api/classes/:id` | One class, its studio and the date it next runs |
| POST | `/api/bookings` | Book a class (`{"class_id": 1}`) |
| GET | `/api/bookings` | The signed-in member's bookings |
| POST | `/api/bookings/:id/pay` | Pay a pending booking |
| POST | `/api/bookings/:id/cancel` | Cancel a paid booking before the class starts |
| GET | `/api/reports/:name?from&to` | A report for a signed-in member; dates are UTC, `to` exclusive |

## Reports

- `daily_actives`: signed-in members per day
- `booking_funnel`: per studio, sessions that viewed a class, started a booking, and paid
- `top_classes`: per class, views, paid bookings and revenue
- `cancellation_rate`: per studio and week, the share of paid bookings later cancelled

The API takes any `from` and `to`; without them it reports the most recent 30 days.

## Tests

    python -m pytest
