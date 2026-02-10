from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Iterable

from youtubesearchpython import ChannelsSearch

import scrapetube
from pydantic import BaseModel, ConfigDict

LOGGER = logging.getLogger(__name__)

_RELATIVE_TIME_PATTERN = re.compile(
    r"(?P<value>\d+)\s+(?P<unit>day|week|month|year)s?\s+ago",
    re.IGNORECASE,
)
_SUBSCRIBER_PATTERN = re.compile(
    r"(?P<count>[\d,.]+)\s*(?P<unit>[KMB])?",
    re.IGNORECASE,
)


class ScrapetubeSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channelId: str | None = None
    channelTitle: str | None = None
    channelHandle: str | None = None
    subscriberCountText: str | None = None


class ScrapetubeVideoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    publishedTimeText: str | None = None


class YouTubeChannelData(BaseModel):
    handle: str | None = None
    url: str | None = None
    subscriber_count: int | None = None
    publishing_cadence: str | None = None
    channel_age: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class YouTubeSearchConfig:
    search_limit: int = 5
    videos_limit: int = 12
    request_sleep: float = 0.5
    score_threshold: int = 60
    yt_search_limit: int = 5
    language: str = "en"
    region: str = "US"


@dataclass(frozen=True)
class YouTubeCandidate:
    title: str | None
    handle: str | None
    url: str | None
    subscriber_count: int | None
    channel_id: str | None
    source: str


def _normalize_handle(handle: str) -> str:
    normalized = handle.strip()
    if not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return normalized


def _build_channel_url(channel_id: str | None, handle: str | None) -> str | None:
    if handle:
        normalized = _normalize_handle(handle)
        return f"https://www.youtube.com/{normalized}"
    if channel_id:
        return f"https://www.youtube.com/channel/{channel_id}"
    return None


def _parse_subscriber_count(text: str | None) -> int | None:
    if not text:
        return None
    match = _SUBSCRIBER_PATTERN.search(text.replace("subscribers", ""))
    if not match:
        return None
    value = match.group("count").replace(",", "")
    unit = (match.group("unit") or "").upper()
    try:
        numeric = float(value)
    except ValueError:
        return None
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(unit, 1)
    return int(numeric * multiplier)


def _relative_time_to_days(text: str | None) -> int | None:
    if not text:
        return None
    match = _RELATIVE_TIME_PATTERN.search(text)
    if not match:
        return None
    value = int(match.group("value"))
    unit = match.group("unit").lower()
    if unit == "day":
        return value
    if unit == "week":
        return value * 7
    if unit == "month":
        return value * 30
    if unit == "year":
        return value * 365
    return None


def _cadence_from_days(days: list[int]) -> str | None:
    if len(days) < 2:
        return None
    sorted_days = sorted(days)
    gaps = [b - a for a, b in zip(sorted_days, sorted_days[1:]) if b > a]
    if not gaps:
        return None
    average_gap = sum(gaps) / len(gaps)
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


def _coerce_video_results(raw_results: Iterable[object]) -> list[ScrapetubeVideoResult]:
    parsed: list[ScrapetubeVideoResult] = []
    for raw in raw_results:
        if isinstance(raw, dict):
            parsed.append(ScrapetubeVideoResult.model_validate(raw))
    return parsed


def _tokenize(text: str) -> set[str]:
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) >= 3}


def _score_candidate(candidate: YouTubeCandidate, tokens: set[str]) -> int:
    score = 0
    title = (candidate.title or "").lower()
    handle = (candidate.handle or "").lower().lstrip("@")
    for token in tokens:
        if handle and token in handle:
            score += 50
        if title and token in title:
            score += 40
    if candidate.subscriber_count:
        score += min(10, int(math.log10(candidate.subscriber_count + 1)))
    return score


def _build_candidate_from_scrapetube(
    result: ScrapetubeSearchResult,
) -> YouTubeCandidate | None:
    handle = result.channelHandle
    if handle:
        handle = _normalize_handle(handle)
    url = _build_channel_url(result.channelId, handle)
    if not url:
        return None
    subscriber_count = _parse_subscriber_count(result.subscriberCountText)
    return YouTubeCandidate(
        title=result.channelTitle,
        handle=handle,
        url=url,
        subscriber_count=subscriber_count,
        channel_id=result.channelId,
        source="scrapetube",
    )


def _build_candidate_from_yt_search(result: dict[str, object]) -> YouTubeCandidate | None:
    title = str(result.get("title") or "")
    channel_id = str(result.get("id") or "")
    link = str(result.get("link") or "") or None
    handle = None
    subscribers_field = result.get("subscribers")
    if isinstance(subscribers_field, str) and subscribers_field.strip().startswith("@"):
        handle = _normalize_handle(subscribers_field.strip())
    if link and "/@" in link:
        handle = _normalize_handle(link.split("/@")[-1].split("/")[0])
    url = link or _build_channel_url(channel_id, handle)
    if not url:
        return None
    return YouTubeCandidate(
        title=title or None,
        handle=handle,
        url=url,
        subscriber_count=None,
        channel_id=channel_id or None,
        source="yt-search-python",
    )


def _select_best_candidate(
    candidates: list[YouTubeCandidate],
    tokens: set[str],
    threshold: int,
) -> YouTubeCandidate | None:
    scored = [
        (candidate, _score_candidate(candidate, tokens)) for candidate in candidates
    ]
    if not scored:
        return None
    best, best_score = max(scored, key=lambda item: item[1])
    if best_score >= threshold:
        return best
    return None


def _search_scrapetube(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    for query in queries:
        results = scrapetube.get_search(
            query,
            results_type="channel",
            limit=config.search_limit,
            sleep=config.request_sleep,
        )
        for raw in results:
            if not isinstance(raw, dict):
                continue
            parsed = ScrapetubeSearchResult.model_validate(raw)
            candidate = _build_candidate_from_scrapetube(parsed)
            if candidate:
                candidates.append(candidate)
    return candidates


def _search_yt_search_python(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    for query in queries:
        search = ChannelsSearch(
            query,
            limit=config.yt_search_limit,
            language=config.language,
            region=config.region,
        )
        results = search.result().get("result", [])
        for raw in results:
            if isinstance(raw, dict):
                candidate = _build_candidate_from_yt_search(raw)
                if candidate:
                    candidates.append(candidate)
    return candidates


def find_best_youtube_channel(
    queries: list[str],
    *,
    config: YouTubeSearchConfig | None = None,
) -> YouTubeChannelData | None:
    config = config or YouTubeSearchConfig()
    tokens = set()
    for query in queries:
        tokens.update(_tokenize(query))

    candidates = _search_scrapetube(queries, config)
    best = _select_best_candidate(candidates, tokens, config.score_threshold)

    if best is None:
        fallback_candidates = _search_yt_search_python(queries, config)
        best = _select_best_candidate(
            fallback_candidates, tokens, config.score_threshold
        )

    if best is None:
        return None

    LOGGER.info("YouTube source channel: %s", best.url)

    videos = scrapetube.get_channel(
        channel_id=best.channel_id,
        channel_url=best.url if best.channel_id is None else None,
        limit=config.videos_limit,
        sleep=config.request_sleep,
    )
    video_results = _coerce_video_results(videos)
    days_list = [
        days
        for days in (_relative_time_to_days(video.publishedTimeText) for video in video_results)
        if days is not None
    ]
    publishing_cadence = _cadence_from_days(days_list)

    oldest_video = scrapetube.get_channel(
        channel_id=best.channel_id,
        channel_url=best.url if best.channel_id is None else None,
        limit=1,
        sort_by="oldest",
        sleep=config.request_sleep,
    )
    oldest_results = _coerce_video_results(oldest_video)
    oldest_days = None
    if oldest_results:
        oldest_days = _relative_time_to_days(oldest_results[0].publishedTimeText)
    if oldest_days is None and days_list:
        oldest_days = max(days_list)
    channel_age = _age_from_days(oldest_days)

    return YouTubeChannelData(
        handle=best.handle,
        url=best.url,
        subscriber_count=best.subscriber_count,
        publishing_cadence=publishing_cadence,
        channel_age=channel_age,
        source_url=best.url,
    )


def find_youtube_channel(
    query: str,
    *,
    config: YouTubeSearchConfig | None = None,
) -> YouTubeChannelData | None:
    return find_best_youtube_channel([query], config=config)
