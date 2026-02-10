from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.adapters.instagram import (
    _age_from_days,
    _candidate_handles,
    _compute_account_age,
    _compute_cadence,
)


def test_candidate_handles_extracts_unique_tokens() -> None:
    handles = _candidate_handles("Alice Co @Alice.Co alice_co")
    assert handles == ["alice", "co", "alice.co", "alice_co"]


def test_compute_cadence_from_dates() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = [base, base + timedelta(days=5), base + timedelta(days=10)]
    assert _compute_cadence(dates) == "Weekly or more"


def test_compute_account_age() -> None:
    base = datetime.now(timezone.utc) - timedelta(days=400)
    dates = [base]
    assert _compute_account_age(dates) == "1 year"


def test_age_from_days_pluralization() -> None:
    assert _age_from_days(800) == "2 years"
    assert _age_from_days(30) == "1 month"
