import argparse
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clock import to_epoch_ms  # noqa: E402
from app.db import is_empty, open_database, transaction  # noqa: E402
from app.events import ingest_events  # noqa: E402
from app.world import insert_bookings, insert_world  # noqa: E402
from scripts.generate import Options, generate  # noqa: E402

USAGE = "python scripts/seed.py [--events N] [--seed S] [--end YYYY-MM-DD] [--truncate]"
CHUNK = 5000
EMPTY_TABLES = (
    "DELETE FROM events; DELETE FROM bookings; DELETE FROM classes; "
    "DELETE FROM users; DELETE FROM studios;"
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="seed", usage=USAGE, add_help=False)
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--truncate", action="store_true")
    args, unknown = parser.parse_known_args()
    try:
        end = to_epoch_ms(datetime.fromisoformat(f"{args.end}T00:00:00+00:00"))
    except ValueError:
        end = None
    if unknown or args.events < 1 or end is None:
        print(f"usage: {USAGE}", file=sys.stderr)
        return 1

    conn = open_database()
    if args.truncate:
        conn.executescript(EMPTY_TABLES)
    if not is_empty(conn):
        print("Database already has data. Re-run with --truncate to replace it.", file=sys.stderr)
        return 1

    started = perf_counter()
    generated = generate(
        Options(
            events=args.events,
            seed=args.seed,
            end=end,
            studios=40,
            classes_per_studio=(5, 15),
            users=12000,
        )
    )
    with transaction(conn):
        insert_world(conn, generated.world)
        insert_bookings(conn, generated.bookings)
        for i in range(0, len(generated.events), CHUNK):
            ingest_events(conn, generated.events[i : i + CHUNK])

    counts = conn.execute(
        "SELECT event_name, COUNT(*) AS n FROM events GROUP BY event_name ORDER BY n DESC"
    ).fetchall()
    for row in counts:
        print(f"{row['event_name']:<18} {row['n']}")
    elapsed = perf_counter() - started
    print(
        f"{len(generated.events)} events, {len(generated.bookings)} bookings, "
        f"{len(generated.world.classes)} classes in {elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
