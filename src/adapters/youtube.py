from __future__ import annotations

import logging
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from youtubesearchpython import ChannelsSearch

import httpx
import scrapetube
from pydantic import BaseModel, ConfigDict, ValidationError

LOGGER = logging.getLogger(__name__)

_RELATIVE_TIME_PATTERN = re.compile(
    r"(?P<value>\d+)\s+(?P<unit>day|week|month|year)s?\s+ago",
    re.IGNORECASE,
)
_SUBSCRIBER_PATTERN = re.compile(
    r"(?P<count>[\d,.]+)\s*(?P<unit>[KMB])?",
    re.IGNORECASE,
)
_CHANNEL_URL_ID_PATTERN = re.compile(r"/channel/([A-Za-z0-9_-]+)")
_HTML_HREF_PATTERN = re.compile(r'href="([^"]+)"')
_DOMAIN_PATTERN = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


class ScrapetubeSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channelId: str | None = None
    channelTitle: str | None = None
    channelHandle: str | None = None
    subscriberCountText: str | dict[str, object] | None = None


class ScrapetubeVideoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    publishedTimeText: str | dict[str, object] | None = None
    title: str | dict[str, object] | None = None


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
    web_validation: bool = True
    web_validation_queries: int = 3


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


def _extract_text(value: str | dict[str, object] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    simple_text = value.get("simpleText")
    if isinstance(simple_text, str):
        return simple_text
    runs = value.get("runs")
    if isinstance(runs, list):
        parts: list[str] = []
        for run in runs:
            if isinstance(run, dict):
                text = run.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)
    return None


def _parse_subscriber_count(text: str | dict[str, object] | None) -> int | None:
    normalized_text = _extract_text(text)
    if not normalized_text:
        return None
    match = _SUBSCRIBER_PATTERN.search(normalized_text.replace("subscribers", ""))
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


def _relative_time_to_days(text: str | dict[str, object] | None) -> int | None:
    normalized_text = _extract_text(text)
    if not normalized_text:
        return None
    match = _RELATIVE_TIME_PATTERN.search(normalized_text)
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
            try:
                parsed.append(ScrapetubeVideoResult.model_validate(raw))
            except ValidationError:
                LOGGER.warning("Skipping malformed scrapetube video result.")
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
        try:
            results = _with_retry(
                lambda: list(
                    scrapetube.get_search(
                        query,
                        results_type="channel",
                        limit=config.search_limit,
                        sleep=config.request_sleep,
                    )
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
        except Exception:
            LOGGER.warning("Scrapetube search failed for query: %s", query)
            continue
        for raw in results:
            if not isinstance(raw, dict):
                continue
            try:
                parsed = ScrapetubeSearchResult.model_validate(raw)
            except ValidationError:
                LOGGER.warning("Skipping malformed scrapetube result for query: %s", query)
                continue
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
        try:
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
        except Exception:
            LOGGER.warning("yt-search-python lookup failed for query: %s", query)
            continue
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
        try:
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
        except Exception:
            LOGGER.warning("YouTube API search failed for query: %s", query)
            continue
        items = data.get("items", [])
        channel_ids = [
            item.get("id", {}).get("channelId")
            for item in items
            if isinstance(item, dict)
        ]
        channel_ids = [cid for cid in channel_ids if cid]
        if not channel_ids:
            continue
        try:
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
        except Exception:
            LOGGER.warning("YouTube API channel details failed for query: %s", query)
            continue
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
        try:
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
        except Exception:
            LOGGER.warning("Websearch fallback failed for query: %s", query)
            continue
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


def _search_websearch_duckduckgo(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    client = httpx.Client(timeout=10)
    for query in queries:
        try:
            response = _with_retry(
                lambda: client.get(
                    "https://duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            html = response.text
        except Exception:
            LOGGER.warning("DuckDuckGo fallback failed for query: %s", query)
            continue

        for match in _HTML_HREF_PATTERN.finditer(html):
            raw_href = match.group(1)
            link = _extract_redirect_url(raw_href)
            if "youtube.com" not in link and "youtu.be" not in link:
                continue
            handle = None
            channel_id = None
            if "/@" in link:
                handle = _normalize_handle(link.split("/@")[-1].split("/")[0])
            channel_match = _CHANNEL_URL_ID_PATTERN.search(link)
            if channel_match:
                channel_id = channel_match.group(1)
            candidates.append(
                YouTubeCandidate(
                    title=None,
                    handle=handle,
                    url=link,
                    subscriber_count=None,
                    channel_id=channel_id,
                    source="websearch-ddg",
                )
            )
    return candidates


def _search_websearch(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates = _search_websearch_serper(queries, config)
    if candidates:
        return candidates
    return _search_websearch_duckduckgo(queries, config)


def _extract_domains(queries: list[str]) -> list[str]:
    found: list[str] = []
    for query in queries:
        for match in _DOMAIN_PATTERN.finditer(query):
            domain = match.group(0).lower().strip().strip(".")
            if domain not in found:
                found.append(domain)
    return found


def _search_domain_first_hit(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> YouTubeCandidate | None:
    domains = _extract_domains(queries)
    for domain in domains:
        domain_query = f"{domain} youtube"
        candidates = _search_websearch([domain_query], config)
        if candidates:
            first = candidates[0]
            return YouTubeCandidate(
                title=first.title,
                handle=first.handle,
                url=first.url,
                subscriber_count=first.subscriber_count,
                channel_id=first.channel_id,
                source="websearch-domain-first",
            )
    return None


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    normalized = url.strip().lower().split("?", 1)[0].rstrip("/")
    return normalized or None


def _normalize_candidate_handle(handle: str | None) -> str | None:
    if not handle:
        return None
    return _normalize_handle(handle).lower()


def _extract_channel_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = _CHANNEL_URL_ID_PATTERN.search(url)
    if not match:
        return None
    return match.group(1)


def _enrich_candidate_with_youtube_api(
    candidate: YouTubeCandidate,
    config: YouTubeSearchConfig,
) -> YouTubeCandidate:
    api_key = config.youtube_api_key or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return candidate

    channel_id = candidate.channel_id or _extract_channel_id_from_url(candidate.url)
    if not channel_id:
        return candidate

    client = httpx.Client(timeout=10)
    try:
        response = _with_retry(
            lambda: client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "snippet,statistics",
                    "id": channel_id,
                    "key": api_key,
                },
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
        items = response.json().get("items", [])
        if not items:
            return candidate
        item = items[0]
        if not isinstance(item, dict):
            return candidate
        snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
        statistics = (
            item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
        )
        api_channel_id = item.get("id") if isinstance(item.get("id"), str) else channel_id
        custom_url = snippet.get("customUrl")
        api_handle = (
            _normalize_handle(custom_url)
            if isinstance(custom_url, str) and custom_url.startswith("@")
            else candidate.handle
        )
        api_url = _build_channel_url(api_channel_id, api_handle) or candidate.url
        subs_raw = statistics.get("subscriberCount")
        api_subscribers = (
            int(subs_raw) if isinstance(subs_raw, str) and subs_raw.isdigit() else candidate.subscriber_count
        )
        return YouTubeCandidate(
            title=snippet.get("title") if isinstance(snippet.get("title"), str) else candidate.title,
            handle=api_handle,
            url=api_url,
            subscriber_count=api_subscribers,
            channel_id=api_channel_id,
            source=f"{candidate.source}+youtube-api",
        )
    except Exception:
        LOGGER.warning("YouTube API enrichment failed for channel_id=%s", channel_id)
        return candidate


def _validate_with_websearch(
    candidate: YouTubeCandidate,
    queries: list[str],
    config: YouTubeSearchConfig,
) -> bool:
    if not config.web_validation:
        return True

    candidate_url = _normalize_url(candidate.url)
    candidate_handle = _normalize_candidate_handle(candidate.handle)
    if not candidate_url and not candidate_handle and not candidate.channel_id:
        return False

    validation_queries: list[str] = []
    for query in queries[: config.web_validation_queries]:
        query = query.strip()
        if query:
            validation_queries.append(f"{query} youtube")
    if candidate.handle:
        validation_queries.append(candidate.handle)
    if candidate.url:
        validation_queries.append(candidate.url)

    web_candidates = _search_websearch(validation_queries, config)
    if not web_candidates:
        return False

    for web_candidate in web_candidates:
        if candidate_url and _normalize_url(web_candidate.url) == candidate_url:
            return True
        if candidate_handle and _normalize_candidate_handle(web_candidate.handle) == candidate_handle:
            return True
        if candidate.channel_id and web_candidate.channel_id == candidate.channel_id:
            return True
    return False


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
        web_candidates = _search_websearch(queries, config)
        best, best_score, accepted = _select_best_candidate(
            web_candidates, tokens, config.score_threshold
        )
    if best is None:
        domain_fallback = _search_domain_first_hit(queries, config)
        if domain_fallback is not None:
            best = domain_fallback
            best_score = config.score_threshold
            accepted = True

    if best is None:
        return None
    best = _enrich_candidate_with_youtube_api(best, config)
    if accepted and not _validate_with_websearch(best, queries, config):
        accepted = False
        LOGGER.warning(
            "YouTube candidate failed web validation: url=%s handle=%s source=%s",
            best.url,
            best.handle,
            best.source,
        )
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

    try:
        videos = _with_retry(
            lambda: list(
                scrapetube.get_channel(
                    channel_id=best.channel_id,
                    channel_url=best.url if best.channel_id is None else None,
                    limit=config.videos_limit,
                    sleep=config.request_sleep,
                )
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
    except Exception:
        LOGGER.warning("Failed to fetch YouTube videos for %s", best.url)
        videos = []
    video_results = _coerce_video_results(videos)
    days_list = [
        days
        for days in (_relative_time_to_days(video.publishedTimeText) for video in video_results)
        if days is not None
    ]
    publishing_cadence = _cadence_from_days(days_list)

    try:
        oldest_video = _with_retry(
            lambda: list(
                scrapetube.get_channel(
                    channel_id=best.channel_id,
                    channel_url=best.url if best.channel_id is None else None,
                    limit=1,
                    sort_by="oldest",
                    sleep=config.request_sleep,
                )
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
    except Exception:
        LOGGER.warning("Failed to fetch oldest YouTube video for %s", best.url)
        oldest_video = []
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


def fetch_recent_video_titles(
    *,
    channel_id: str | None = None,
    channel_url: str | None = None,
    limit: int = 5,
    config: YouTubeSearchConfig | None = None,
) -> list[str]:
    """
    Best-effort recent video titles for a channel.

    This is used for qualification/cold-outreach grounding.
    """
    config = config or YouTubeSearchConfig()
    if limit <= 0:
        return []
    if not channel_id and not channel_url:
        return []
    try:
        videos = _with_retry(
            lambda: list(
                scrapetube.get_channel(
                    channel_id=channel_id,
                    channel_url=channel_url if channel_id is None else None,
                    limit=max(1, limit),
                    sleep=config.request_sleep,
                )
            ),
            attempts=config.retry_attempts,
            backoff=config.retry_backoff,
        )
    except Exception:
        return []

    results = _coerce_video_results(videos)
    titles: list[str] = []
    for video in results:
        title = _extract_text(video.title)
        title = (title or "").strip()
        if not title:
            continue
        if title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles
def _with_retry(func, *, attempts: int, backoff: float):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            LOGGER.debug("YouTube lookup retry (attempt %s/%s).", attempt + 1, attempts)
            time.sleep(backoff * (attempt + 1))
    if last_error:
        raise last_error
    return None
