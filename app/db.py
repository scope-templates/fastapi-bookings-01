import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.schema import SCHEMA

DEFAULT_DATABASE_PATH = "data/studio-slot.sqlite"
MEMORY = ":memory:"


def open_database(path: str | None = None) -> sqlite3.Connection:
    file = path or os.environ.get("DATABASE_PATH") or DEFAULT_DATABASE_PATH
    if file != MEMORY:
        Path(file).resolve().parent.mkdir(parents=True, exist_ok=True)
    # Handlers share one connection across a thread pool. Preparing each statement
    # afresh keeps two threads from landing on the same cached one mid-read.
    conn = sqlite3.connect(
        file, isolation_level=None, check_same_thread=False, cached_statements=0
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


# Handlers run in a thread pool over one connection, so a unit of work holds this
# from BEGIN to COMMIT and no other thread can put statements inside it. It is
# re-entrant because a unit of work often contains a smaller one.
_writing = threading.RLock()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One unit of work. Nested uses join the transaction already running."""
    with _writing:
        if conn.in_transaction:
            yield conn
            return
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) AS n FROM studios").fetchone()["n"] == 0


_shared: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """The application database. Loads the bundled sample the first time it is opened empty."""
    global _shared
    if _shared is None:
        from app.sample import load_sample

        conn = open_database()
        if is_empty(conn):
            load_sample(conn)
        _shared = conn
    return _shared
