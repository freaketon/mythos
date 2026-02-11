from __future__ import annotations

import logging
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable

from youtubesearchpython import ChannelsSearch

import httpx
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
    confidence: int | None = None
    source: str | None = None
    accepted: bool = True


@dataclass(frozen=True)
class YouTubeSearchConfig:
    search_limit: int = 5
    videos_limit: int = 12
    request_sleep: float = 0.5
    score_threshold: int = 60
    yt_search_limit: int = 5
    language: str = "en"
    region: str = "US"
    retry_attempts: int = 2
    retry_backoff: float = 1.0
    youtube_api_key: str | None = None
    youtube_api_max_results: int = 5
    websearch_api_key: str | None = None
    websearch_endpoint: str = "https://google.serper.dev/search"


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
) -> tuple[YouTubeCandidate | None, int | None, bool]:
    scored = [
        (candidate, _score_candidate(candidate, tokens)) for candidate in candidates
    ]
    if not scored:
        return None, None, False
    best, best_score = max(scored, key=lambda item: item[1])
    accepted = best_score >= threshold
    return best, best_score, accepted


def _search_scrapetube(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    for query in queries:
        results = _with_retry(
            lambda: scrapetube.get_search(
                query,
                results_type="channel",
                limit=config.search_limit,
                sleep=config.request_sleep,
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
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
        results = _with_retry(
            lambda: search.result().get("result", []),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
        for raw in results:
            if isinstance(raw, dict):
                candidate = _build_candidate_from_yt_search(raw)
                if candidate:
                    candidates.append(candidate)
    return candidates


def _search_youtube_api(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    api_key = config.youtube_api_key or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return []
    candidates: list[YouTubeCandidate] = []
    client = httpx.Client(timeout=10)
    for query in queries:
        response = _with_retry(
            lambda: client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "channel",
                    "maxResults": config.youtube_api_max_results,
                    "key": api_key,
                },
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
        data = response.json()
        items = data.get("items", [])
        channel_ids = [
            item.get("id", {}).get("channelId")
            for item in items
            if isinstance(item, dict)
        ]
        channel_ids = [cid for cid in channel_ids if cid]
        if not channel_ids:
            continue
        details = _with_retry(
            lambda: client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "snippet,statistics",
                    "id": ",".join(channel_ids),
                    "key": api_key,
                },
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
        detail_items = details.json().get("items", [])
        for item in detail_items:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
            statistics = (
                item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
            )
            title = snippet.get("title")
            custom_url = snippet.get("customUrl")
            handle = None
            if isinstance(custom_url, str) and custom_url.startswith("@"):
                handle = _normalize_handle(custom_url)
            channel_id = item.get("id")
            url = _build_channel_url(channel_id, handle)
            if not url:
                continue
            subs_raw = statistics.get("subscriberCount")
            subscriber_count = int(subs_raw) if isinstance(subs_raw, str) and subs_raw.isdigit() else None
            candidates.append(
                YouTubeCandidate(
                    title=title,
                    handle=handle,
                    url=url,
                    subscriber_count=subscriber_count,
                    channel_id=channel_id,
                    source="youtube-api",
                )
            )
    return candidates


def _search_websearch_serper(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    api_key = config.websearch_api_key or os.getenv("SERPER_API_KEY")
    if not api_key:
        return []
    candidates: list[YouTubeCandidate] = []
    client = httpx.Client(timeout=10)
    for query in queries:
        response = _with_retry(
            lambda: client.post(
                config.websearch_endpoint,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query},
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
        data = response.json()
        organic = data.get("organic", [])
        for item in organic:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            title = item.get("title")
            if not isinstance(link, str) or "youtube.com" not in link:
                continue
            handle = None
            if "/@" in link:
                handle = _normalize_handle(link.split("/@")[-1].split("/")[0])
            url = link
            candidates.append(
                YouTubeCandidate(
                    title=title if isinstance(title, str) else None,
                    handle=handle,
                    url=url,
                    subscriber_count=None,
                    channel_id=None,
                    source="websearch",
                )
            )
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
    best, best_score, accepted = _select_best_candidate(
        candidates, tokens, config.score_threshold
    )

    if best is None:
        fallback_candidates = _search_yt_search_python(queries, config)
        best, best_score, accepted = _select_best_candidate(
            fallback_candidates, tokens, config.score_threshold
        )

    if best is None:
        api_candidates = _search_youtube_api(queries, config)
        best, best_score, accepted = _select_best_candidate(
            api_candidates, tokens, config.score_threshold
        )

    if best is None:
        web_candidates = _search_websearch_serper(queries, config)
        best, best_score, accepted = _select_best_candidate(
            web_candidates, tokens, config.score_threshold
        )

    if best is None:
        return None
    if not accepted:
        return YouTubeChannelData(
            handle=best.handle,
            url=best.url,
            subscriber_count=best.subscriber_count,
            source_url=best.url,
            confidence=best_score,
            source=best.source,
            accepted=False,
        )

    LOGGER.info("YouTube source channel: %s", best.url)

    videos = _with_retry(
        lambda: scrapetube.get_channel(
            channel_id=best.channel_id,
            channel_url=best.url if best.channel_id is None else None,
            limit=config.videos_limit,
            sleep=config.request_sleep,
        ),
        attempts=config.retry_attempts,
        backoff=config.retry_backoff,
    )
    video_results = _coerce_video_results(videos)
    days_list = [
        days
        for days in (_relative_time_to_days(video.publishedTimeText) for video in video_results)
        if days is not None
    ]
    publishing_cadence = _cadence_from_days(days_list)

    oldest_video = _with_retry(
        lambda: scrapetube.get_channel(
            channel_id=best.channel_id,
            channel_url=best.url if best.channel_id is None else None,
            limit=1,
            sort_by="oldest",
            sleep=config.request_sleep,
        ),
        attempts=config.retry_attempts,
        backoff=config.retry_backoff,
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
        confidence=best_score,
        source=best.source,
        accepted=True,
    )


def find_youtube_channel(
    query: str,
    *,
    config: YouTubeSearchConfig | None = None,
) -> YouTubeChannelData | None:
    return find_best_youtube_channel([query], config=config)
def _with_retry(func, *, attempts: int, backoff: float):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            LOGGER.warning("YouTube lookup failed (attempt %s/%s).", attempt + 1, attempts)
            time.sleep(backoff * (attempt + 1))
    if last_error:
        raise last_error
    return None
