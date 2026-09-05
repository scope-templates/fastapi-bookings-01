import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.clock import DAY, to_epoch_ms  # noqa: E402
from app.reports.range import Range  # noqa: E402
from scripts.generate import Options, generate  # noqa: E402
from tests.helpers.reports import expected_reports  # noqa: E402


def utc(year: int, month: int, day: int) -> int:
    return to_epoch_ms(datetime(year, month, day, tzinfo=timezone.utc))


def main() -> int:
    end = utc(2026, 8, 31)
    generated = generate(
        Options(events=500, seed=7, end=end, studios=3, classes_per_studio=(3, 3), users=40)
    )
    windows = [
        ("August", Range(end - 30 * DAY, end)),
        ("everything", Range(end - 548 * DAY, end)),
        ("December to January", Range(utc(2025, 12, 1), utc(2026, 1, 12))),
        ("one day", Range(utc(2026, 8, 16), utc(2026, 8, 17))),
    ]

    sample = {
        "world": asdict(generated.world),
        "bookings": [asdict(b) for b in generated.bookings],
        "events": generated.events,
    }
    cases = [
        {
            "label": label,
            "from": window.start,
            "to": window.end,
            "expected": expected_reports(generated, window),
        }
        for label, window in windows
    ]

    out = ROOT / "scripts" / "sample.json"
    out.write_text(json.dumps(sample, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(sample['events'])} events, {len(sample['bookings'])} bookings")

    cases_out = ROOT / "tests" / "helpers" / "sample_cases.json"
    cases_out.write_text(json.dumps(cases, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {cases_out}: {len(cases)} windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
