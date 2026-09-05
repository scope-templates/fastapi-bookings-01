from app.world import ClassRow, Studio, User, World
from tests.helpers import utc

TINY_WORLD = World(
    studios=[
        Studio(id=1, name="Harbor Yoga", city="Eastport"),
        Studio(id=2, name="Kiln & Wheel", city="Westmill"),
    ],
    classes=[
        ClassRow(
            id=1, studio_id=1, title="Sunrise Flow", price_cents=1800, starts_at=utc(2026, 10, 1, 7)
        ),
        ClassRow(
            id=2, studio_id=2, title="Wheel Basics", price_cents=4500, starts_at=utc(2026, 10, 2, 18)
        ),
    ],
    users=[
        User(id=1, email="ada@example.com", created_at=utc(2025, 1, 1)),
        User(id=2, email="bo@example.com", created_at=utc(2025, 4, 1)),
    ],
)
