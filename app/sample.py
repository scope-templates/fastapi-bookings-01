import json
import sqlite3
from pathlib import Path
from typing import Any

from app.events import ingest_events
from app.world import insert_bookings, insert_world

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "scripts" / "sample.json"


def read_sample(file: Path | str = SAMPLE_FILE) -> dict[str, Any]:
    with open(file, encoding="utf-8") as handle:
        return json.load(handle)


def load_sample(conn: sqlite3.Connection, sample: dict[str, Any] | None = None) -> None:
    """Sample data for local development and tests."""
    if sample is None:
        sample = read_sample()
    insert_world(conn, sample["world"])
    insert_bookings(conn, sample["bookings"])
    ingest_events(conn, sample["events"])
