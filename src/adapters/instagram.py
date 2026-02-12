from __future__ import annotations

import logging
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import instaloader
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)

_HANDLE_PATTERN = re.compile(r"[A-Za-z0-9._]+")
_AT_HANDLE_PATTERN = re.compile(r"(?<![A-Za-z0-9._])@([A-Za-z0-9._]{3,30})")
_INSTAGRAM_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{3,30})",
    re.IGNORECASE,
)
_HTML_HREF_PATTERN = re.compile(r'href="([^"]+)"')


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
    retry_attempts: int = 2
    retry_backoff: float = 1.0
    websearch_api_key: str | None = None
    websearch_endpoint: str = "https://google.serper.dev/search"
    web_validation: bool = True
    web_validation_queries: int = 3


def _sanitize_handle(value: str) -> str | None:
    candidate = value.strip().lstrip("@")
    match = _HANDLE_PATTERN.fullmatch(candidate)
    return candidate if match else None


def _candidate_handles(query: str) -> list[str]:
    handles = []
    for match in _INSTAGRAM_URL_PATTERN.finditer(query):
        handle = _sanitize_handle(match.group(1).lower())
        if handle and handle not in handles:
            handles.append(handle)
    for match in _AT_HANDLE_PATTERN.finditer(query):
        handle = _sanitize_handle(match.group(1).lower())
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


def _normalize_profile_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().lower().split("?", 1)[0].rstrip("/")


def _extract_handle_from_instagram_url(url: str) -> str | None:
    normalized = _normalize_profile_url(url)
    if not normalized:
        return None
    marker = "instagram.com/"
    if marker not in normalized:
        return None
    segment = normalized.split(marker, 1)[1].split("/", 1)[0].strip()
    if not segment or segment in {"p", "reel", "explore", "stories"}:
        return None
    return _sanitize_handle(segment)


def _with_retry(func, *, attempts: int, backoff: float):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            LOGGER.debug(
                "Instagram web lookup failed (attempt %s/%s).",
                attempt + 1,
                attempts,
            )
            time.sleep(backoff * (attempt + 1))
    if last_error:
        raise last_error
    return None


def _search_instagram_handles_web(
    query: str,
    config: InstagramSearchConfig,
) -> set[str]:
    handles = _search_instagram_handles_serper(query, config)
    if handles:
        return handles
    return _search_instagram_handles_duckduckgo(query, config)


def _search_instagram_handles_serper(
    query: str,
    config: InstagramSearchConfig,
) -> set[str]:
    api_key = config.websearch_api_key or os.getenv("SERPER_API_KEY")
    if not api_key:
        return set()

    client = httpx.Client(timeout=10)
    handles: set[str] = set()
    search_queries = [f"{query} instagram", f"site:instagram.com {query}"]
    for item_query in search_queries[: config.web_validation_queries]:
        try:
            response = _with_retry(
                lambda: client.post(
                    config.websearch_endpoint,
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json={"q": item_query},
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            data = response.json()
        except Exception:
            LOGGER.warning("Instagram websearch failed for query: %s", item_query)
            continue

        organic = data.get("organic", [])
        for organic_item in organic:
            if not isinstance(organic_item, dict):
                continue
            link = organic_item.get("link")
            if not isinstance(link, str):
                continue
            handle = _extract_handle_from_instagram_url(link)
            if handle:
                handles.add(handle.lower())
    return handles


def _extract_redirect_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
        query_params = parse_qs(parsed.query)
        uddg = query_params.get("uddg")
        if uddg:
            return unquote(uddg[0])
    return href


def _search_instagram_handles_duckduckgo(
    query: str,
    config: InstagramSearchConfig,
) -> set[str]:
    client = httpx.Client(timeout=10)
    handles: set[str] = set()
    search_queries = [f"{query} instagram", f"site:instagram.com {query}"]
    for item_query in search_queries[: config.web_validation_queries]:
        try:
            response = _with_retry(
                lambda: client.get(
                    "https://duckduckgo.com/html/",
                    params={"q": item_query},
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            html = response.text
        except Exception:
            LOGGER.warning("Instagram DuckDuckGo search failed for query: %s", item_query)
            continue
        for match in _HTML_HREF_PATTERN.finditer(html):
            raw_href = match.group(1)
            link = _extract_redirect_url(raw_href)
            handle = _extract_handle_from_instagram_url(link)
            if handle:
                handles.add(handle.lower())
    return handles


def _validate_instagram_candidate(
    query: str,
    handle: str,
    config: InstagramSearchConfig,
) -> bool:
    if not config.web_validation:
        return True

    observed_handles = _search_instagram_handles_web(query, config)
    if not observed_handles:
        return False
    return handle.lower() in observed_handles


def find_instagram_profile(
    query: str,
    *,
    config: InstagramSearchConfig | None = None,
    loader: instaloader.Instaloader | None = None,
) -> InstagramProfileData | None:
    config = config or InstagramSearchConfig()
    loader = loader or instaloader.Instaloader()
    candidate_handles = _candidate_handles(query)
    if not candidate_handles:
        candidate_handles.extend(
            handle for handle in _search_instagram_handles_web(query, config) if handle not in candidate_handles
        )

    for handle in candidate_handles[: config.candidate_limit]:
        profile = None
        for attempt in range(config.retry_attempts):
            try:
                profile = instaloader.Profile.from_username(loader.context, handle)
                break
            except instaloader.exceptions.ProfileNotExistsException:
                profile = None
                break
            except instaloader.exceptions.ConnectionException:
                LOGGER.debug(
                    "Instagram lookup failed for handle %s (attempt %s/%s).",
                    handle,
                    attempt + 1,
                    config.retry_attempts,
                )
                time.sleep(config.retry_backoff * (attempt + 1))
        if profile is None:
            continue
        if not _validate_instagram_candidate(query, handle, config):
            LOGGER.warning(
                "Instagram candidate failed web validation: handle=%s query=%s",
                handle,
                query,
            )
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
