from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.adapters import instagram as instagram_adapter
from src.adapters.instagram import (
    InstagramSearchConfig,
    _age_from_days,
    _candidate_handles,
    _compute_account_age,
    _compute_cadence,
    _extract_handle_from_instagram_url,
    _search_instagram_handles_web,
    _validate_instagram_candidate,
    find_instagram_profile,
)


def test_candidate_handles_extracts_unique_tokens() -> None:
    handles = _candidate_handles("Alice Co @Alice.Co alice_co")
    assert handles == ["alice.co"]


def test_candidate_handles_ignores_generic_tokens() -> None:
    handles = _candidate_handles("Alice Company example.com")
    assert handles == []


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


def test_extract_handle_from_instagram_url() -> None:
    assert (
        _extract_handle_from_instagram_url("https://www.instagram.com/example_handle/")
        == "example_handle"
    )
    assert _extract_handle_from_instagram_url("https://www.instagram.com/p/abc123/") is None


def test_validate_instagram_candidate_requires_web_match(monkeypatch) -> None:
    config = InstagramSearchConfig(websearch_api_key="fake-key")
    monkeypatch.setattr(
        instagram_adapter,
        "_search_instagram_handles_web",
        lambda *_args, **_kwargs: {"different_handle"},
    )
    assert _validate_instagram_candidate("Example Person", "example_handle", config) is False


def test_validate_instagram_candidate_accepts_web_match(monkeypatch) -> None:
    config = InstagramSearchConfig(websearch_api_key="fake-key")
    monkeypatch.setattr(
        instagram_adapter,
        "_search_instagram_handles_web",
        lambda *_args, **_kwargs: {"example_handle"},
    )
    assert _validate_instagram_candidate("Example Person", "example_handle", config) is True


def test_find_instagram_profile_skips_unvalidated_candidate(monkeypatch) -> None:
    class FakeProfile:
        followers = 100

        @staticmethod
        def get_posts():
            return []

    monkeypatch.setattr(
        instagram_adapter.instaloader.Profile,
        "from_username",
        lambda *_args, **_kwargs: FakeProfile(),
    )
    monkeypatch.setattr(
        instagram_adapter,
        "_validate_instagram_candidate",
        lambda *_args, **_kwargs: False,
    )
    result = find_instagram_profile(
        "Example Person",
        config=InstagramSearchConfig(websearch_api_key="fake-key"),
        loader=SimpleNamespace(context=object()),
    )
    assert result is None


def test_instagram_web_search_falls_back_to_duckduckgo(monkeypatch) -> None:
    monkeypatch.setattr(
        instagram_adapter,
        "_search_instagram_handles_serper",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        instagram_adapter,
        "_search_instagram_handles_duckduckgo",
        lambda *_args, **_kwargs: {"example_handle"},
    )
    handles = _search_instagram_handles_web("Example Person", InstagramSearchConfig())
    assert handles == {"example_handle"}
