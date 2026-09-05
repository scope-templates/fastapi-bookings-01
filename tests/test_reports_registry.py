from app.db import open_database
from app.reports import REPORTS, Range, is_report_name, run_report
from app.world import insert_world
from tests.tiny_world import TINY_WORLD


def fresh_db():
    conn = open_database(":memory:")
    insert_world(conn, TINY_WORLD)
    return conn


def test_recognises_every_name_it_holds_and_nothing_else():
    for name in REPORTS:
        assert is_report_name(name)
    assert not is_report_name("nope")
    assert not is_report_name("revenue")


def test_runs_every_name_it_holds():
    conn = fresh_db()
    for name in REPORTS:
        assert isinstance(run_report(conn, name, Range(0, 10)), list)
