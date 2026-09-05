from typing import Any, Mapping

WEEK = 7 * 86_400_000


def _starts_at(klass: Any) -> int:
    return klass["starts_at"] if isinstance(klass, Mapping) else klass.starts_at


def next_occurrence(klass: Any, t: int) -> int:
    """A class is a weekly series anchored by `starts_at`, so it also ran on every earlier week."""
    weeks = (t - _starts_at(klass)) // WEEK + 1
    return _starts_at(klass) + weeks * WEEK
