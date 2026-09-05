import json
from pathlib import Path

from app.db import open_database
from app.reports import REPORTS
from app.reports.range import Range
from app.sample import SAMPLE_FILE, load_sample, read_sample
from tests.helpers import utc
from tests.helpers.reports import expected_reports, iso_week

CASES_FILE = Path(__file__).resolve().parent / "helpers" / "sample_cases.json"

SAMPLE = read_sample()
CASES = json.loads(CASES_FILE.read_text(encoding="utf-8"))


def windows():
    return [(case, Range(case["from"], case["to"])) for case in CASES]


def test_iso_week_labels_the_weeks_that_straddle_a_year_boundary():
    assert iso_week(utc(2024, 12, 31)) == "2025-W01"
    assert iso_week(utc(2027, 1, 2)) == "2026-W53"
    assert iso_week(utc(2026, 1, 5)) == "2026-W02"


def test_the_bundled_sample_has_three_studios_and_about_five_hundred_events():
    assert SAMPLE_FILE.exists()
    assert 480 <= len(SAMPLE["events"]) <= 500
    assert len(CASES) >= 4
    assert len(SAMPLE["world"]["studios"]) == 3


def test_each_report_returns_the_samples_known_rows():
    loaded = open_database(":memory:")
    load_sample(loaded)
    for case, window in windows():
        for name, rows in case["expected"].items():
            assert REPORTS[name](loaded, window) == rows, f"{name} {case['label']}"


def test_the_known_rows_match_a_plain_recalculation():
    for case, window in windows():
        recalculated = expected_reports(SAMPLE, window)
        for name, rows in case["expected"].items():
            assert recalculated[name] == rows, f"{name} {case['label']}"


def test_every_window_has_rows():
    for case in CASES:
        total = sum(len(rows) for rows in case["expected"].values())
        assert total > 0, case["label"]


def test_the_app_database_fills_itself_from_the_sample_when_empty(monkeypatch):
    import app.db as database

    monkeypatch.setattr(database, "_shared", None)
    conn = database.get_db()
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == len(
        SAMPLE["events"]
    )
    assert database.get_db() is conn
