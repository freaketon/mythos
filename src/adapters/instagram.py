from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import instaloader
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)

_HANDLE_PATTERN = re.compile(r"[A-Za-z0-9._]+")


class InstagramProfileData(BaseModel):
    handle: str | None = None
    followers: int | None = None
    publishing_cadence: str | None = None
    account_age: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class InstagramSearchConfig:
    candidate_limit: int = 5
    posts_limit: int = 12


def _sanitize_handle(value: str) -> str | None:
    candidate = value.strip().lstrip("@")
    match = _HANDLE_PATTERN.fullmatch(candidate)
    return candidate if match else None


def _candidate_handles(query: str) -> list[str]:
    tokens = re.split(r"[^A-Za-z0-9._]+", query.lower())
    handles = []
    for token in tokens:
        if not token:
            continue
        handle = _sanitize_handle(token)
        if handle and handle not in handles:
            handles.append(handle)
    return handles


def _cadence_from_gaps(gaps: Iterable[int]) -> str | None:
    gap_list = [gap for gap in gaps if gap > 0]
    if len(gap_list) < 2:
        return None
    average_gap = sum(gap_list) / len(gap_list)
    if average_gap <= 7:
        return "Weekly or more"
    if average_gap <= 30:
        return "Monthly"
    if average_gap <= 90:
        return "Quarterly"
    return "Less frequent"


def _age_from_days(days: int | None) -> str | None:
    if days is None:
        return None
    if days >= 365:
        years = max(1, math.floor(days / 365))
        unit = "year" if years == 1 else "years"
        return f"{years} {unit}"
    if days >= 30:
        months = max(1, math.floor(days / 30))
        unit = "month" if months == 1 else "months"
        return f"{months} {unit}"
    value = max(1, days)
    unit = "day" if value == 1 else "days"
    return f"{value} {unit}"


def _days_between(older: datetime, newer: datetime) -> int:
    delta = newer - older
    return max(0, delta.days)


def _extract_post_dates(profile: instaloader.Profile, limit: int) -> list[datetime]:
    dates: list[datetime] = []
    for post in profile.get_posts():
        dates.append(post.date_utc.replace(tzinfo=timezone.utc))
        if len(dates) >= limit:
            break
    return dates


def _compute_cadence(dates: list[datetime]) -> str | None:
    if len(dates) < 2:
        return None
    sorted_dates = sorted(dates)
    gaps = [
        _days_between(older, newer)
        for older, newer in zip(sorted_dates, sorted_dates[1:])
    ]
    return _cadence_from_gaps(gaps)


def _compute_account_age(dates: list[datetime]) -> str | None:
    if not dates:
        return None
    oldest = min(dates)
    today = datetime.now(timezone.utc)
    days = _days_between(oldest, today)
    return _age_from_days(days)


def _build_profile_url(handle: str) -> str:
    return f"https://www.instagram.com/{handle}/"


def find_instagram_profile(
    query: str,
    *,
    config: InstagramSearchConfig | None = None,
    loader: instaloader.Instaloader | None = None,
) -> InstagramProfileData | None:
    config = config or InstagramSearchConfig()
    loader = loader or instaloader.Instaloader()

    for handle in _candidate_handles(query)[: config.candidate_limit]:
        try:
            profile = instaloader.Profile.from_username(loader.context, handle)
        except instaloader.exceptions.ProfileNotExistsException:
            continue
        except instaloader.exceptions.ConnectionException:
            LOGGER.warning("Instagram lookup failed for handle %s.", handle)
            continue

        LOGGER.info("Instagram source profile: %s", _build_profile_url(handle))
        dates = _extract_post_dates(profile, config.posts_limit)
        cadence = _compute_cadence(dates)
        account_age = _compute_account_age(dates)

        return InstagramProfileData(
            handle=handle,
            followers=profile.followers,
            publishing_cadence=cadence,
            account_age=account_age,
            source_url=_build_profile_url(handle),
        )

    return None
