from __future__ import annotations

from src.adapters.youtube import (
    _age_from_days,
    _cadence_from_days,
    _parse_subscriber_count,
    _relative_time_to_days,
)


def test_parse_subscriber_count() -> None:
    assert _parse_subscriber_count("1.2K subscribers") == 1200
    assert _parse_subscriber_count("12,345 subscribers") == 12345
    assert _parse_subscriber_count("3M subscribers") == 3_000_000
    assert _parse_subscriber_count({"simpleText": "4.5K subscribers"}) == 4500
    assert _parse_subscriber_count(None) is None


def test_relative_time_to_days() -> None:
    assert _relative_time_to_days("2 days ago") == 2
    assert _relative_time_to_days("3 weeks ago") == 21
    assert _relative_time_to_days("4 months ago") == 120
    assert _relative_time_to_days("1 year ago") == 365
    assert _relative_time_to_days({"simpleText": "11 days ago"}) == 11
    assert _relative_time_to_days("Streamed 2 days ago") == 2
    assert _relative_time_to_days(None) is None


def test_cadence_from_days() -> None:
    assert _cadence_from_days([1, 3, 5, 8]) == "Weekly or more"
    assert _cadence_from_days([3, 20, 50]) == "Monthly"
    assert _cadence_from_days([10, 80, 150]) == "Quarterly"
    assert _cadence_from_days([10, 200, 500]) == "Less frequent"


def test_age_from_days() -> None:
    assert _age_from_days(400) == "1 year"
    assert _age_from_days(800) == "2 years"
    assert _age_from_days(50) == "1 month"
    assert _age_from_days(10) == "10 days"
    assert _age_from_days(None) is None
