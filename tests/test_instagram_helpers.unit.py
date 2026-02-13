from __future__ import annotations

import src.adapters.instagram as instagram


def test_candidate_handles_from_mixed_query() -> None:
    query = "Find @SomeUser and https://instagram.com/Other.User plus ig: third_user"
    handles = instagram._candidate_handles(query)
    assert "someuser" in handles
    assert "other.user" in handles
    assert "third_user" in handles


def test_sanitize_handle_rejects_bad_values() -> None:
    assert instagram._sanitize_handle("") is None
    assert instagram._sanitize_handle(".bad") is None
    assert instagram._sanitize_handle("bad.") is None
    assert instagram._sanitize_handle("www") is None
    assert instagram._sanitize_handle("com") is None
    assert instagram._sanitize_handle("ok_name") == "ok_name"


def test_age_and_cadence_helpers() -> None:
    assert instagram._age_from_days(1) == "1 day"
    assert instagram._age_from_days(40) == "1 month"
    assert instagram._age_from_days(800) == "2 years"
    assert instagram._cadence_from_gaps([2, 3, 4]) == "Weekly or more"
    assert instagram._cadence_from_gaps([40, 50, 60]) == "Quarterly"


def test_extract_redirect_url_duckduckgo() -> None:
    href = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Finstagram.com%2Fsomeuser"
    assert instagram._extract_redirect_url(href) == "https://instagram.com/someuser"

