import math
from dataclasses import dataclass, field
from typing import Any

from app.classes import next_occurrence
from app.rng import Rng
from app.world import Booking, ClassRow, Studio, User, World

DAY = 86_400_000
WINDOW_DAYS = 548


@dataclass(frozen=True)
class StudioKind:
    kind: str
    names: tuple[str, ...]
    classes: tuple[str, ...]


STUDIO_KINDS = (
    StudioKind(
        "yoga",
        ("Harbor Yoga", "Stillwater Yoga", "Ridge Flow", "Lantern Yoga"),
        ("Sunrise Flow", "Slow Stretch", "Power Hour", "Restorative", "Beginners Yoga"),
    ),
    StudioKind(
        "pottery",
        ("Kiln & Wheel", "Mudlark Studio", "Riverclay", "Cedar Pottery"),
        ("Wheel Basics", "Handbuilding", "Glaze Night", "Open Studio", "Mug Workshop"),
    ),
    StudioKind(
        "music",
        ("Fourth Street Music", "Brass Lane", "The Practice Room", "Bellwood Music"),
        ("Guitar Intro", "Piano Lab", "Ukulele Circle", "Singing Basics", "Drum Fundamentals"),
    ),
    StudioKind(
        "dance",
        ("Northgate Dance", "Maple Ballroom", "Studio Nine", "Riverside Dance"),
        ("Salsa Basics", "Contemporary", "Ballet Barre", "Hip Hop Open", "Swing Night"),
    ),
)
CITIES = (
    "Eastport",
    "Westmill",
    "Northgate",
    "Bellwood",
    "Riverside",
    "Cedar Falls",
    "Harbor Point",
    "Maple Grove",
)
DEVICES = ("web", "ios", "android")
REFERRERS = ("direct", "search", "instagram", "friend", "newsletter")
SEARCHES = (
    "yoga near me",
    "pottery beginners",
    "guitar lessons",
    "evening class",
    "weekend workshop",
    "kids music",
)
HOUR_WEIGHTS = (1, 1, 1, 1, 1, 1, 2, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 6, 8, 8, 7, 5, 3, 2)


@dataclass(frozen=True)
class Options:
    events: int
    seed: int
    end: int  # epoch ms, exclusive
    studios: int
    classes_per_studio: tuple[int, int]
    users: int


@dataclass
class Generated:
    world: World
    bookings: list[Booking] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Visit:
    events: list[dict[str, Any]]
    bookings: list[Booking]
    met: list[int]


def weekday(ms: int) -> int:
    """Sunday is 0, counting from the Thursday the epoch began on."""
    return (ms // DAY + 4) % 7


def generate_world(rng: Rng, opts: Options) -> World:
    studios: list[Studio] = []
    classes: list[ClassRow] = []
    class_id = 1
    for i in range(1, opts.studios + 1):
        kind = STUDIO_KINDS[(i - 1) % len(STUDIO_KINDS)]
        base = kind.names[((i - 1) // len(STUDIO_KINDS)) % len(kind.names)]
        name = f"{base} {i}" if i > len(STUDIO_KINDS) * len(kind.names) else base
        studios.append(Studio(id=i, name=name, city=rng.pick(CITIES)))
        count = rng.int(opts.classes_per_studio[0], opts.classes_per_studio[1])
        for c in range(count):
            suffix = f" {c // len(kind.classes) + 1}" if c >= len(kind.classes) else ""
            classes.append(
                ClassRow(
                    id=class_id,
                    studio_id=i,
                    title=kind.classes[c % len(kind.classes)] + suffix,
                    price_cents=rng.int(12, 60) * 100,
                    starts_at=opts.end + rng.int(1, 28) * DAY + rng.int(8, 20) * 3_600_000,
                )
            )
            class_id += 1
    users: list[User] = []
    start = opts.end - WINDOW_DAYS * DAY
    for u in range(1, opts.users + 1):
        # Most of the membership joined during the window; the rest were already on the books.
        if rng.chance(0.6):
            created_at = min(
                opts.end - 1,
                start + math.floor(WINDOW_DAYS * math.sqrt(rng.float())) * DAY + rng.int(0, DAY - 1),
            )
        else:
            created_at = start - rng.int(1, 365) * DAY
        users.append(User(id=u, email=f"member{u}@example.com", created_at=created_at))
    return World(studios=studios, classes=classes, users=users)


def pick_start(rng: Rng, opts: Options) -> int:
    start = opts.end - WINDOW_DAYS * DAY
    while True:
        day = min(WINDOW_DAYS - 1, math.floor(WINDOW_DAYS * math.sqrt(rng.float())))
        if weekday(start + day * DAY) in (0, 6) or rng.chance(0.7):
            break
    pick = rng.float() * sum(HOUR_WEIGHTS)
    hour = 0
    while hour < 23:
        pick -= HOUR_WEIGHTS[hour]
        if pick <= 0:
            break
        hour += 1
    return start + day * DAY + hour * 3_600_000 + rng.int(0, 3_599_999)


def generate_visit(
    rng: Rng, world: World, opts: Options, next_booking_id: int, booked: set[str], met: set[int]
) -> Visit:
    events: list[dict[str, Any]] = []
    bookings: list[Booking] = []
    session_id = rng.hex(12)
    studio = rng.pick(world.studios)
    studio_classes = [c for c in world.classes if c.studio_id == studio.id]
    device = rng.pick(DEVICES)
    referrer = rng.pick(REFERRERS)
    visitor = rng.pick(world.users) if rng.chance(0.7) else None
    t = pick_start(rng, opts)
    # A visit made before someone joined is browsing they did while still a stranger.
    user = visitor if visitor is not None and t >= visitor.created_at else None
    base = {
        "user_id": user.id if user else None,
        "session_id": session_id,
        "studio_id": studio.id,
        "booking_id": None,
        "class_id": None,
    }

    def push(event_name: str, properties: dict[str, Any], **extra: Any) -> None:
        if t < opts.end:
            events.append(
                {"occurred_at": t, **base, **extra, "event_name": event_name, "properties": properties}
            )

    start = opts.end - WINDOW_DAYS * DAY
    if user and user.id not in met and user.created_at >= start:
        # Joining is its own moment, not something buried in whatever visit happens to come first.
        events.append(
            {
                "occurred_at": user.created_at,
                "user_id": user.id,
                "session_id": rng.hex(12),
                "studio_id": studio.id,
                "booking_id": None,
                "class_id": None,
                "event_name": "signup",
                "properties": {"device": device},
            }
        )
    elif user and rng.chance(0.6):
        push("login", {"device": device})
    t += rng.int(1_000, 20_000)
    push("page_view", {"device": device, "referrer": referrer, "path": "/"})
    if rng.chance(0.5):
        t += rng.int(5_000, 40_000)
        push("search", {"device": device, "query": rng.pick(SEARCHES)})
    views = rng.int(1, 3)
    last_class: ClassRow | None = None
    for _ in range(views):
        klass = rng.pick(studio_classes)
        t += rng.int(20_000, 120_000)
        push(
            "class_view",
            {"device": device, "class_id": klass.id, "price_cents": klass.price_cents},
            class_id=klass.id,
        )
        last_class = klass
    if user and last_class and rng.chance(0.35):
        booking_id = next_booking_id
        started_at = t + rng.int(30_000, 300_000)
        occurs_at = next_occurrence(last_class, started_at)
        key = f"{user.id}:{last_class.id}:{occurs_at}"
        if started_at < opts.end and key not in booked:
            t = started_at
            booked.add(key)
            booking = Booking(
                id=booking_id,
                user_id=user.id,
                class_id=last_class.id,
                studio_id=studio.id,
                status="pending",
                created_at=t,
                paid_at=None,
                cancelled_at=None,
                price_cents=last_class.price_cents,
                occurs_at=occurs_at,
            )
            props = {"class_id": last_class.id, "price_cents": last_class.price_cents}
            push("booking_started", props, booking_id=booking_id, class_id=last_class.id)
            if rng.chance(0.8):
                t += rng.int(20_000, 180_000)
                if t < opts.end:
                    booking.status = "paid"
                    booking.paid_at = t
                    push("booking_paid", props, booking_id=booking_id, class_id=last_class.id)
                    if rng.chance(0.12):
                        room = occurs_at - t
                        cancel_at = t + math.floor(room * (0.2 + 0.7 * rng.float()))
                        # Someone booking minutes before the doors open keeps the place
                        # rather than dropping it.
                        if cancel_at - t >= 20_000 and cancel_at < opts.end:
                            booking.status = "cancelled"
                            booking.cancelled_at = cancel_at
                            events.append(
                                {
                                    "occurred_at": cancel_at,
                                    **base,
                                    "booking_id": booking_id,
                                    "class_id": last_class.id,
                                    "event_name": "booking_cancelled",
                                    "properties": props,
                                }
                            )
            bookings.append(booking)
    return Visit(events=events, bookings=bookings, met=[user.id] if user else [])


def generate(opts: Options) -> Generated:
    low, high = opts.classes_per_studio
    if low < 1 or low > high:
        raise ValueError("classes_per_studio must be (low, high) with 1 <= low <= high")
    if opts.events < 1:
        raise ValueError("events must be at least 1")
    rng = Rng(opts.seed)
    world = generate_world(rng, opts)
    events: list[dict[str, Any]] = []
    bookings: list[Booking] = []
    booked: set[str] = set()
    met: set[int] = set()
    next_booking_id = 1
    guard = 0
    while len(events) < opts.events and guard < opts.events * 4:
        guard += 1
        visit = generate_visit(rng, world, opts, next_booking_id, booked, met)
        if not visit.events:
            continue
        if len(events) + len(visit.events) > opts.events:
            break
        events.extend(visit.events)
        bookings.extend(visit.bookings)
        # A member counts as met only once the visit that met them is kept,
        # so the signup is never doubled.
        met.update(visit.met)
        next_booking_id += len(visit.bookings)
    events.sort(key=lambda e: e["occurred_at"])
    return Generated(world=world, bookings=bookings, events=events)
