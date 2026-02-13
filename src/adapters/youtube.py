from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from youtubesearchpython import ChannelsSearch

import httpx
import scrapetube
from pydantic import BaseModel, ConfigDict, ValidationError

LOGGER = logging.getLogger(__name__)
_INVALID_YOUTUBE_API_KEYS: set[str] = set()
_WEBSITE_YOUTUBE_CACHE: dict[str, list[str]] = {}
_CHANNEL_TITLES_CACHE: dict[str, list[str]] = {}

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
_YOUTUBE_CHANNELISH_PATTERN = re.compile(r"/(@[A-Za-z0-9._-]+|channel/|c/|user/)", re.IGNORECASE)
_YOUTUBE_USER_PATTERN = re.compile(r"/user/([^/?#]+)", re.IGNORECASE)
_YOUTUBE_CUSTOM_PATTERN = re.compile(r"/c/([^/?#]+)", re.IGNORECASE)
_JSONLD_PATTERN = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


class ScrapetubeSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channelId: str | None = None
    channelTitle: str | None = None
    channelHandle: str | None = None
    subscriberCountText: str | dict[str, object] | None = None


class ScrapetubeVideoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    publishedTimeText: str | dict[str, object] | None = None


class YouTubeChannelData(BaseModel):
    handle: str | None = None
    url: str | None = None
    subscriber_count: int | None = None
    publishing_cadence: str | None = None
    channel_age: str | None = None
    source_url: str | None = None
    confidence: int | None = None
    confidence_reason: str | None = None
    source: str | None = None
    evidence_sources: list[str] | None = None
    recent_video_titles: list[str] | None = None
    content_affinity: float | None = None
    accepted: bool = True


@dataclass(frozen=True)
class LeadSignals:
    tokens: set[str]
    anchor_tokens: set[str]


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
    google_cse_api_key: str | None = None
    google_cse_cx: str | None = None
    google_cse_endpoint: str = "https://www.googleapis.com/customsearch/v1"
    web_validation: bool = True
    web_validation_queries: int = 3
    website_discovery: bool = True
    website_discovery_max_domains: int = 1
    website_discovery_timeout: float = 6.0
    yt_dlp_enabled: bool = True
    yt_dlp_timeout: float = 10.0
    llm_rerank: bool = False
    llm_model: str = "gpt-5-mini"
    llm_max_candidates: int = 6
    llm_timeout: float = 12.0
    openai_api_key: str | None = None
    openai_endpoint: str = "https://api.openai.com/v1/chat/completions"


@dataclass(frozen=True)
class YouTubeCandidate:
    title: str | None
    handle: str | None
    url: str | None
    subscriber_count: int | None
    channel_id: str | None
    source: str
    published_at: str | None = None
    uploads_playlist_id: str | None = None


def _dedupe_queries(queries: list[str]) -> list[str]:
    deduped: list[str] = []
    for query in queries:
        normalized = query.strip()
        if not normalized:
            continue
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _expand_youtube_queries(queries: list[str]) -> list[str]:
    expanded = _dedupe_queries(queries)
    for query in list(expanded):
        lower = query.lower()
        variants = []
        if "youtube" not in lower and "youtu.be" not in lower:
            variants.append(f"{query} youtube")
        variants.append(f"site:youtube.com {query}")
        for variant in variants:
            if variant not in expanded:
                expanded.append(variant)
    return expanded


_STOPWORDS = {
    "youtube",
    "youtu",
    "youtu",
    "youtu.be",
    "www",
    "http",
    "https",
    "site",
    "channel",
    "official",
    "the",
    "and",
    "for",
    "with",
    "from",
    "com",
    "net",
    "org",
}


def _hint_candidates_from_queries(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    for query in queries:
        text = query.strip()
        if not text:
            continue
        if text.startswith("@"):
            handle = _normalize_handle(text)
            # Don't let a bogus handle become a hard match.
            if not _youtube_url_exists(_build_channel_url(None, handle) or ""):
                continue
            resolved = _youtube_api_channel_candidate_for_handle(handle, "hint-handle+youtube-api", config)
            if resolved:
                candidates.append(resolved)
                continue
            candidates.append(
                YouTubeCandidate(
                    title=None,
                    handle=handle,
                    url=_build_channel_url(None, handle),
                    subscriber_count=None,
                    channel_id=None,
                    published_at=None,
                    uploads_playlist_id=None,
                    source="hint-handle",
                )
            )
            continue

        lowered = text.lower()
        if "youtube.com" in lowered or "youtu.be" in lowered:
            # Prefer a single explicit URL when present.
            url = text.strip().rstrip(").,")
            normalized_url = _normalize_url(url) or url
            if not _youtube_url_exists(normalized_url):
                continue
            if _is_channelish_youtube_url(normalized_url):
                handle = None
                if "/@" in normalized_url:
                    handle = _normalize_handle(normalized_url.split("/@")[-1].split("/")[0])
                channel_id = _extract_channel_id_from_url(normalized_url)
                username = _extract_username_from_url(normalized_url)
                if username:
                    resolved = _youtube_api_channel_candidate_for_username(username, "hint-url-user+youtube-api", config)
                    if resolved:
                        candidates.append(resolved)
                        continue
                if channel_id:
                    resolved = _youtube_api_channel_candidate(channel_id, "hint-url+youtube-api", config)
                    if resolved:
                        candidates.append(resolved)
                        continue
                if handle and _youtube_api_key(config):
                    resolved = _youtube_api_channel_candidate_for_handle(handle, "hint-url-handle+youtube-api", config)
                    if resolved:
                        candidates.append(resolved)
                        continue
                custom = _extract_custom_from_url(normalized_url)
                if custom:
                    resolved_id = _yt_dlp_resolve_channel_id(normalized_url, config)
                    if resolved_id:
                        resolved = _youtube_api_channel_candidate(resolved_id, "hint-url-custom+yt-dlp+youtube-api", config)
                        if resolved:
                            candidates.append(resolved)
                            continue
                candidates.append(
                    YouTubeCandidate(
                        title=None,
                        handle=handle,
                        url=normalized_url,
                        subscriber_count=None,
                        channel_id=channel_id,
                        published_at=None,
                        uploads_playlist_id=None,
                        source="hint-url",
                    )
                )
                continue

            video_id = _extract_video_id(url)
            if video_id:
                channel_id = _youtube_api_resolve_channel_id_from_video_id(video_id, config)
                if channel_id:
                    resolved = _youtube_api_channel_candidate(channel_id, "hint-video-url+youtube-api", config)
                    if resolved:
                        candidates.append(resolved)
    return _dedupe_candidates(candidates)


def _candidate_identity(candidate: YouTubeCandidate) -> str:
    normalized_url = _normalize_url(candidate.url)
    if normalized_url:
        return f"url:{normalized_url}"
    normalized_handle = _normalize_candidate_handle(candidate.handle)
    if normalized_handle:
        return f"handle:{normalized_handle}"
    if candidate.channel_id:
        return f"channel_id:{candidate.channel_id}"
    title = (candidate.title or "").strip().lower()
    source = candidate.source.strip().lower()
    return f"fallback:{source}:{title}"


def _dedupe_candidates(candidates: list[YouTubeCandidate]) -> list[YouTubeCandidate]:
    deduped: list[YouTubeCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _candidate_identity(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


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


def _age_from_published_at(published_at: str | None) -> str | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = max(0, (datetime.now(timezone.utc) - dt).days)
    return _age_from_days(days)


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


def _extract_video_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/", 1)[0]
        return video_id or None
    if "youtube.com" in host:
        qs = parse_qs(parsed.query)
        value = qs.get("v", [])
        if value and isinstance(value[0], str) and value[0]:
            return value[0]
    return None


def _is_channelish_youtube_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    if "youtube.com" not in normalized and "youtu.be" not in normalized:
        return False
    return bool(_YOUTUBE_CHANNELISH_PATTERN.search(normalized))


def _extract_username_from_url(url: str | None) -> str | None:
    normalized = _normalize_url(url)
    if not normalized or "youtube.com" not in normalized:
        return None
    match = _YOUTUBE_USER_PATTERN.search(normalized)
    if not match:
        return None
    username = match.group(1).strip()
    return username or None


def _extract_custom_from_url(url: str | None) -> str | None:
    normalized = _normalize_url(url)
    if not normalized or "youtube.com" not in normalized:
        return None
    match = _YOUTUBE_CUSTOM_PATTERN.search(normalized)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_handle_from_url(url: str | None) -> str | None:
    normalized = _normalize_url(url)
    if not normalized or "youtube.com" not in normalized:
        return None
    if "/@" not in normalized:
        return None
    raw = normalized.split("/@")[-1].split("/")[0]
    return _normalize_handle(raw)


def _yt_dlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


def _yt_dlp_resolve_channel_id(url: str, config: YouTubeSearchConfig) -> str | None:
    if not config.yt_dlp_enabled:
        return None
    if not _yt_dlp_available():
        return None
    try:
        proc = subprocess.run(
            [
                "yt-dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=config.yt_dlp_timeout,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    channel_id = payload.get("channel_id")
    if isinstance(channel_id, str) and channel_id:
        return channel_id
    uploader_id = payload.get("uploader_id")
    if isinstance(uploader_id, str) and uploader_id.startswith("UC"):
        return uploader_id
    return None


def _youtube_url_exists(url: str, *, timeout: float = 6.0) -> bool:
    normalized = _normalize_url(url) or url
    if not normalized:
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(normalized, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return False
    if resp.status_code >= 400:
        return False
    text = (resp.text or "").lower()
    # YouTube uses a friendly error page for non-existent handles in many locales.
    if "this page isn't available" in text or "page isn't available" in text:
        return False
    if "not found" in text and "youtube" in text and "error" in text:
        return False
    return True


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


def _tokenize(text: str, *, min_len: int = 3) -> set[str]:
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) >= min_len and token not in _STOPWORDS}


def _extract_anchor_tokens(queries: list[str]) -> set[str]:
    suffixes = [
        "coaching",
        "consulting",
        "agency",
        "studio",
        "crm",
        "realty",
        "realestate",
        "marketing",
        "media",
        "ventures",
        "capital",
        "holdings",
        "group",
    ]

    def expand(token: str) -> set[str]:
        token = token.strip().lower()
        if not token or token in _STOPWORDS:
            return set()
        out = {token} if len(token) >= 4 else set()
        for suffix in suffixes:
            if token.endswith(suffix) and len(token) >= len(suffix) + 4:
                out.add(suffix)
                stem = token[: -len(suffix)]
                if len(stem) >= 4:
                    out.add(stem)
        return out

    anchors: set[str] = set()
    for query in queries:
        q = (query or "").strip()
        if not q:
            continue
        lowered = q.lower()
        # High-signal: domains.
        if "." in lowered and " " not in lowered:
            for part in lowered.split("."):
                anchors |= expand(part)
            continue
        # High-signal: query shaped like "<token> YouTube" (often email localpart / brand).
        if lowered.endswith(" youtube"):
            head = lowered[: -len(" youtube")].strip()
            if head and " " not in head:
                for tok in _tokenize(head, min_len=4):
                    anchors |= expand(tok)
    return anchors


def _lead_signals(queries: list[str]) -> LeadSignals:
    tokens: set[str] = set()
    for query in queries:
        if not query:
            continue
        tokens |= _tokenize(query, min_len=3)
        # Pull apart domain-like fragments that show up inside larger strings.
        for match in _DOMAIN_PATTERN.finditer(query):
            domain = match.group(0).lower()
            for part in domain.split("."):
                if part and len(part) >= 4 and part not in _STOPWORDS:
                    tokens.add(part)
    anchor_tokens = _extract_anchor_tokens(queries)
    return LeadSignals(tokens=tokens, anchor_tokens=anchor_tokens)


def _token_match_weight(token: str) -> int:
    # Avoid over-weighting short/common name tokens like "dan".
    if len(token) <= 3:
        return 10
    if len(token) == 4:
        return 20
    if len(token) <= 6:
        return 30
    return 40


def _fetch_recent_video_titles(candidate: YouTubeCandidate, *, limit: int = 6) -> list[str]:
    cache_key = _candidate_identity(candidate)
    cached = _CHANNEL_TITLES_CACHE.get(cache_key)
    if cached is not None:
        return cached[:limit]
    try:
        raw = _with_retry(
            lambda: list(
                scrapetube.get_channel(
                    channel_id=candidate.channel_id,
                    channel_url=candidate.url if candidate.channel_id is None else None,
                    limit=max(1, limit),
                    sleep=0.0,
                )
            ),
            attempts=1,
            backoff=0.0,
        )
    except Exception:
        _CHANNEL_TITLES_CACHE[cache_key] = []
        return []
    titles: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _extract_text(item.get("title"))
        if title:
            titles.append(title)
    _CHANNEL_TITLES_CACHE[cache_key] = titles
    return titles[:limit]


def _content_affinity(signals: LeadSignals, candidate: YouTubeCandidate) -> float | None:
    if not signals.anchor_tokens:
        return None
    content_tokens: set[str] = set()
    if candidate.title:
        content_tokens |= _tokenize(candidate.title, min_len=3)
    if candidate.handle:
        content_tokens |= _tokenize(candidate.handle.lstrip("@"), min_len=3)
    titles = _fetch_recent_video_titles(candidate, limit=6)
    for t in titles:
        content_tokens |= _tokenize(t, min_len=3)
    if len(content_tokens) < 3:
        return None
    overlap = len(signals.anchor_tokens & content_tokens)
    denom = max(1, len(signals.anchor_tokens))
    return overlap / denom


def _score_candidate(
    candidate: YouTubeCandidate,
    signals: LeadSignals,
    *,
    evidence_count: int = 1,
) -> int:
    score = 0
    if candidate.source.startswith("hint"):
        # Explicit user-provided evidence should dominate heuristic scoring.
        score += 1000
    if candidate.source.startswith("website"):
        # Company/personal website is a strong trust signal for canonical socials.
        score += 400
    title = (candidate.title or "").lower()
    handle = (candidate.handle or "").lower().lstrip("@")
    for token in signals.tokens:
        w = _token_match_weight(token)
        if handle and token in handle:
            score += w + 10
        if title and token in title:
            score += w
    # Stronger bonus for "anchor" tokens (domain / brand / email localpart), when present.
    for token in signals.anchor_tokens:
        if handle and token in handle:
            score += 120
        if title and token in title:
            score += 90
    if candidate.subscriber_count:
        score += min(10, int(math.log10(candidate.subscriber_count + 1)))
    if evidence_count > 1:
        score += min(120, 40 * (evidence_count - 1))
    return score


def _merge_candidates(
    candidates: list[YouTubeCandidate],
) -> tuple[list[YouTubeCandidate], dict[str, set[str]]]:
    merged: dict[str, YouTubeCandidate] = {}
    evidence: dict[str, set[str]] = {}
    for candidate in candidates:
        key = _candidate_identity(candidate)
        if key not in merged:
            merged[key] = candidate
            evidence[key] = {candidate.source}
            continue
        evidence[key].add(candidate.source)
        current = merged[key]
        # Prefer the richer record when merging.
        def richer(a: YouTubeCandidate, b: YouTubeCandidate) -> YouTubeCandidate:
            a_score = sum(1 for v in (a.title, a.handle, a.url, a.subscriber_count, a.channel_id) if v)
            b_score = sum(1 for v in (b.title, b.handle, b.url, b.subscriber_count, b.channel_id) if v)
            return b if b_score > a_score else a
        best = richer(current, candidate)
        sources = evidence[key]
        if any(s.startswith("hint") for s in sources):
            best_source = "hint"
        elif any(s.startswith("website") for s in sources):
            best_source = "website"
        else:
            # Keep a stable, informative label even when multiple methods agree.
            preferences = [
                "websearch-domain-first",
                "domain-first",
                "websearch",
                "youtube-api",
                "scrapetube",
                "yt-search-python",
                "hint-url",
                "hint-handle",
                "website",
            ]
            best_source = None
            for pref in preferences:
                for src in sources:
                    if src.startswith(pref):
                        best_source = pref
                        break
                if best_source:
                    break
            if not best_source:
                best_source = sorted(sources)[0] if sources else best.source
        merged[key] = YouTubeCandidate(
            title=best.title,
            handle=best.handle,
            url=best.url,
            subscriber_count=best.subscriber_count,
            channel_id=best.channel_id,
            source=best_source,
            published_at=best.published_at,
            uploads_playlist_id=best.uploads_playlist_id,
        )
    return list(merged.values()), evidence


def _openai_api_key(config: YouTubeSearchConfig) -> str | None:
    return config.openai_api_key or os.getenv("OPENAI_API_KEY")


def _llm_rerank(
    queries: list[str],
    candidates: list[YouTubeCandidate],
    scores: dict[str, int],
    config: YouTubeSearchConfig,
    *,
    evidence_sources: dict[str, set[str]] | None = None,
) -> tuple[YouTubeCandidate | None, bool]:
    api_key = _openai_api_key(config)
    if not config.llm_rerank or not api_key:
        return None, False
    if len(candidates) < 2:
        return None, False

    # Only consider the most plausible candidates (by heuristic score), and include any that
    # meet the acceptance threshold (LLM is primarily a tie-breaker between plausible hits).
    ranked_all = sorted(
        candidates,
        key=lambda c: scores.get(_candidate_identity(c), 0),
        reverse=True,
    )
    plausible = [
        c for c in ranked_all if scores.get(_candidate_identity(c), 0) >= config.score_threshold
    ]
    if len(plausible) < 2:
        return None, False
    ranked = plausible[: max(2, min(config.llm_max_candidates, 12))]

    payload_candidates: list[dict[str, object]] = []

    for idx, c in enumerate(ranked):
        identity = _candidate_identity(c)
        sources = sorted((evidence_sources or {}).get(identity, {c.source}))
        payload_candidates.append(
            {
                "index": idx,
                "title": c.title,
                "handle": c.handle,
                "url": c.url,
                "subscriber_count": c.subscriber_count,
                "channel_id": c.channel_id,
                "source": c.source,
                "evidence_sources": sources,
                "website_evidence": c.source.startswith("website"),
                "api_enriched": "youtube-api" in c.source or c.subscriber_count is not None or c.uploads_playlist_id is not None,
                "recent_video_titles": _fetch_recent_video_titles(c, limit=5),
            }
        )

    system = (
        "You select the best matching YouTube channel for a lead from multiple candidates. "
        "Prioritize relevance to the lead (name/company/domain), and trust explicit evidence sources "
        "(company website links, explicit handles/URLs). Avoid fake/nonexistent channels and unrelated channels."
    )
    user = json.dumps(
        {
            "lead_queries": queries,
            "candidates": payload_candidates,
            "instruction": (
                "Return decision=accept with best_index for the best candidate. "
                "If all look wrong or unrelated, return decision=reject."
            ),
        }
    )
    schema = {
        "name": "youtube_rerank",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "decision": {"type": "string", "enum": ["accept", "reject"]},
                "best_index": {"type": "integer", "minimum": 0, "maximum": len(payload_candidates) - 1},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "reason": {"type": "string"},
            },
            "required": ["decision", "best_index", "confidence", "reason"],
        },
    }

    def _is_model_or_format_error(payload: object, status_code: int) -> bool:
        # Only retry on likely "model doesn't exist / not allowed / incompatible response_format" errors.
        if status_code not in (400, 404):
            return False
        if not isinstance(payload, dict):
            return True
        err = payload.get("error")
        if not isinstance(err, dict):
            return True
        msg = err.get("message")
        if not isinstance(msg, str) or not msg.strip():
            return True
        lower = msg.lower()
        needles = (
            "model",
            "not found",
            "does not exist",
            "no such model",
            "not have access",
            "response_format",
            "json_schema",
            "structured",
            "unsupported",
        )
        return any(n in lower for n in needles)

    def _post_rerank(client: httpx.Client, model: str) -> tuple[dict[str, object] | None, object, int]:
        resp = client.post(
            config.openai_endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_schema", "json_schema": schema},
            },
        )
        try:
            payload: object = resp.json()
        except Exception:
            payload = None
        if resp.status_code >= 400:
            return None, payload, resp.status_code
        if not isinstance(payload, dict):
            return None, payload, resp.status_code
        return payload, payload, resp.status_code

    try:
        with httpx.Client(timeout=config.llm_timeout) as client:
            data: dict[str, object] | None = None
            fallback = "gpt-4o-mini"
            models_to_try = [config.llm_model]
            if config.llm_model != fallback:
                models_to_try.append(fallback)
            for i, model in enumerate(models_to_try):
                payload, raw, status = _post_rerank(client, model=model)
                if payload is not None:
                    data = payload
                    break
                if i == 0 and not _is_model_or_format_error(raw, status_code=status):
                    break
            if data is None:
                return None, False
    except Exception:
        return None, False

    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception:
        return None, False

    decision = parsed.get("decision")
    best_index = parsed.get("best_index")
    confidence = parsed.get("confidence")
    if decision == "reject":
        return None, True
    if not isinstance(best_index, int) or not (0 <= best_index < len(ranked)):
        return None, False
    if not isinstance(confidence, int):
        confidence = 0
    chosen = ranked[best_index]
    # Too uncertain: don't override heuristics.
    if confidence < 55:
        return None, False
    return chosen, False


def _youtube_api_key(config: YouTubeSearchConfig) -> str | None:
    key = config.youtube_api_key or os.getenv("YOUTUBE_API_KEY")
    if not key:
        return None
    if key in _INVALID_YOUTUBE_API_KEYS:
        return None
    # Heuristic guard: real YouTube API keys are typically 39 chars and start with "AIza".
    if key.startswith("AIza") and len(key) < 39:
        LOGGER.warning("YOUTUBE_API_KEY looks too short (len=%s); API calls will likely fail.", len(key))
    return key


def _maybe_disable_youtube_api_key(payload: dict[str, object], key: str) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    message = error.get("message")
    if not isinstance(message, str):
        return
    lower = message.lower()
    if "exceeded your quota" in lower or "quota" in lower and "exceeded" in lower:
        if key not in _INVALID_YOUTUBE_API_KEYS:
            _INVALID_YOUTUBE_API_KEYS.add(key)
            LOGGER.warning("Disabling YouTube API usage: quota exceeded (%s).", message)
        return
    if "api key not valid" in lower or ("api key" in lower and "not valid" in lower):
        if key not in _INVALID_YOUTUBE_API_KEYS:
            _INVALID_YOUTUBE_API_KEYS.add(key)
            LOGGER.warning("Disabling YouTube API usage: YOUTUBE_API_KEY is invalid (%s).", message)


def _youtube_api_channel_details(channel_id: str, config: YouTubeSearchConfig) -> dict[str, object] | None:
    api_key = _youtube_api_key(config)
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={
                        "part": "snippet,statistics,contentDetails",
                        "id": channel_id,
                        "key": api_key,
                    },
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            data = response.json()
            _maybe_disable_youtube_api_key(data, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def _youtube_api_channel_candidate_for_username(username: str, source: str, config: YouTubeSearchConfig) -> YouTubeCandidate | None:
    api_key = _youtube_api_key(config)
    if not api_key:
        return None
    username = username.strip()
    if not username:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={
                        "part": "snippet,statistics,contentDetails",
                        "forUsername": username,
                        "key": api_key,
                    },
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            payload = response.json()
            _maybe_disable_youtube_api_key(payload, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    if not isinstance(item, dict):
        return None
    channel_id = item.get("id")
    if not isinstance(channel_id, str) or not channel_id:
        return None
    return _youtube_api_channel_candidate(channel_id, source, config)


def _youtube_api_channel_candidate_for_handle(handle: str, source: str, config: YouTubeSearchConfig) -> YouTubeCandidate | None:
    api_key = _youtube_api_key(config)
    if not api_key:
        return None
    handle = _normalize_handle(handle).lstrip("@")
    if not handle:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={
                        "part": "snippet,statistics,contentDetails",
                        "forHandle": handle,
                        "key": api_key,
                    },
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            payload = response.json()
            _maybe_disable_youtube_api_key(payload, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    if not isinstance(item, dict):
        return None
    channel_id = item.get("id")
    if not isinstance(channel_id, str) or not channel_id:
        return None
    return _youtube_api_channel_candidate(channel_id, source, config)


def _youtube_api_channel_candidate(channel_id: str, source: str, config: YouTubeSearchConfig) -> YouTubeCandidate | None:
    item = _youtube_api_channel_details(channel_id, config)
    if not item:
        url = _build_channel_url(channel_id, None)
        if not url:
            return None
        return YouTubeCandidate(
            title=None,
            handle=None,
            url=url,
            subscriber_count=None,
            channel_id=channel_id,
            published_at=None,
            uploads_playlist_id=None,
            source=source,
        )
    snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
    statistics = item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
    content_details = item.get("contentDetails", {}) if isinstance(item.get("contentDetails"), dict) else {}
    related_playlists = (
        content_details.get("relatedPlaylists", {})
        if isinstance(content_details.get("relatedPlaylists"), dict)
        else {}
    )
    uploads_playlist_id = (
        related_playlists.get("uploads")
        if isinstance(related_playlists.get("uploads"), str)
        else None
    )
    custom_url = snippet.get("customUrl")
    handle = _normalize_handle(custom_url) if isinstance(custom_url, str) and custom_url.startswith("@") else None
    url = _build_channel_url(channel_id, handle)
    if not url:
        return None
    subs_raw = statistics.get("subscriberCount")
    subscriber_count = int(subs_raw) if isinstance(subs_raw, str) and subs_raw.isdigit() else None
    published_at = snippet.get("publishedAt") if isinstance(snippet.get("publishedAt"), str) else None
    title = snippet.get("title") if isinstance(snippet.get("title"), str) else None
    return YouTubeCandidate(
        title=title,
        handle=handle,
        url=url,
        subscriber_count=subscriber_count,
        channel_id=channel_id,
        published_at=published_at,
        uploads_playlist_id=uploads_playlist_id,
        source=source,
    )


def _youtube_api_resolve_channel_id_from_video_id(video_id: str, config: YouTubeSearchConfig) -> str | None:
    api_key = _youtube_api_key(config)
    if not api_key or not video_id:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "snippet", "id": video_id, "key": api_key},
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            data = response.json()
            _maybe_disable_youtube_api_key(data, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    if not isinstance(item, dict):
        return None
    snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
    channel_id = snippet.get("channelId")
    return channel_id if isinstance(channel_id, str) and channel_id else None


def _youtube_api_resolve_channel_id_from_handle(handle: str, config: YouTubeSearchConfig) -> str | None:
    api_key = _youtube_api_key(config)
    if not api_key:
        return None
    normalized = _normalize_handle(handle).lower()

    # Prefer the cheap, exact handle resolver.
    direct = _youtube_api_channel_candidate_for_handle(normalized, "handle+youtube-api", config)
    if direct and direct.channel_id:
        return direct.channel_id

    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "q": normalized,
                        "type": "channel",
                        "maxResults": config.youtube_api_max_results,
                        "key": api_key,
                    },
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            data = response.json()
            _maybe_disable_youtube_api_key(data, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    channel_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item.get("id", {})
        if isinstance(cid, dict):
            channel_id = cid.get("channelId")
            if isinstance(channel_id, str) and channel_id:
                channel_ids.append(channel_id)
    if not channel_ids:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            details = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "snippet", "id": ",".join(channel_ids), "key": api_key},
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            detail_payload = details.json()
            _maybe_disable_youtube_api_key(detail_payload, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
            detail_items = detail_payload.get("items", [])
    except Exception:
        return None
    if not isinstance(detail_items, list):
        return None
    for item in detail_items:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
        custom_url = snippet.get("customUrl")
        if isinstance(custom_url, str) and custom_url.lower() == normalized:
            cid = item.get("id")
            if isinstance(cid, str) and cid:
                return cid
    # Fall back to the first result if we can't confidently match by handle.
    return channel_ids[0]


def _youtube_api_uploads_cadence(uploads_playlist_id: str, config: YouTubeSearchConfig) -> str | None:
    api_key = _youtube_api_key(config)
    if not api_key:
        return None
    uploads_playlist_id = uploads_playlist_id.strip()
    if not uploads_playlist_id:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            response = _with_retry(
                lambda: client.get(
                    "https://www.googleapis.com/youtube/v3/playlistItems",
                    params={
                        "part": "contentDetails",
                        "playlistId": uploads_playlist_id,
                        "maxResults": max(2, min(config.videos_limit, 50)),
                        "key": api_key,
                    },
                ),
                attempts=config.retry_attempts,
                backoff=config.retry_backoff,
            )
            data = response.json()
            _maybe_disable_youtube_api_key(data, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return None
    except Exception:
        return None
    items = data.get("items", [])
    if not isinstance(items, list) or len(items) < 2:
        return None

    now = datetime.now(timezone.utc)
    days_list: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content_details = item.get("contentDetails", {}) if isinstance(item.get("contentDetails"), dict) else {}
        published_at = content_details.get("videoPublishedAt")
        if not isinstance(published_at, str):
            continue
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days_list.append(max(0, (now - dt).days))
    return _cadence_from_days(days_list)


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
        published_at=None,
        uploads_playlist_id=None,
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
    url = _normalize_url(url) or url
    return YouTubeCandidate(
        title=title or None,
        handle=handle,
        url=url,
        subscriber_count=None,
        channel_id=channel_id or None,
        published_at=None,
        uploads_playlist_id=None,
        source="yt-search-python",
    )


def _select_best_candidate(
    candidates: list[YouTubeCandidate],
    signals: LeadSignals,
    evidence_sources: dict[str, set[str]] | None,
    threshold: int,
) -> tuple[YouTubeCandidate | None, int | None, bool]:
    scored = [
        (
            candidate,
            _score_candidate(
                candidate,
                signals,
                evidence_count=len((evidence_sources or {}).get(_candidate_identity(candidate), {candidate.source})),
            ),
        )
        for candidate in candidates
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
    api_key = _youtube_api_key(config)
    if not api_key:
        return []
    candidates: list[YouTubeCandidate] = []
    with httpx.Client(timeout=10) as client:
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
                _maybe_disable_youtube_api_key(data, api_key)
                if api_key in _INVALID_YOUTUBE_API_KEYS:
                    return []
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
                            "part": "snippet,statistics,contentDetails",
                            "id": ",".join(channel_ids),
                            "key": api_key,
                        },
                    ),
                    attempts=config.retry_attempts,
                    backoff=config.retry_backoff,
                )
                detail_payload = details.json()
                _maybe_disable_youtube_api_key(detail_payload, api_key)
                if api_key in _INVALID_YOUTUBE_API_KEYS:
                    return []
                detail_items = detail_payload.get("items", [])
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
                content_details = item.get("contentDetails", {}) if isinstance(item.get("contentDetails"), dict) else {}
                related_playlists = (
                    content_details.get("relatedPlaylists", {})
                    if isinstance(content_details.get("relatedPlaylists"), dict)
                    else {}
                )
                uploads_playlist_id = (
                    related_playlists.get("uploads")
                    if isinstance(related_playlists.get("uploads"), str)
                    else None
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
                        published_at=snippet.get("publishedAt") if isinstance(snippet.get("publishedAt"), str) else None,
                        uploads_playlist_id=uploads_playlist_id,
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
    with httpx.Client(timeout=10) as client:
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
                if not isinstance(link, str):
                    continue
                if "youtube.com" not in link and "youtu.be" not in link:
                    continue
                if not _is_channelish_youtube_url(link):
                    continue
                handle = None
                if "/@" in link:
                    handle = _normalize_handle(link.split("/@")[-1].split("/")[0])
                url = link
                url = _normalize_url(url) or url
                candidates.append(
                    YouTubeCandidate(
                        title=title if isinstance(title, str) else None,
                        handle=handle,
                        url=url,
                        subscriber_count=None,
                        channel_id=None,
                        published_at=None,
                        uploads_playlist_id=None,
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
    with httpx.Client(timeout=10) as client:
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
                if not _is_channelish_youtube_url(link):
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
                        url=_normalize_url(link) or link,
                        subscriber_count=None,
                        channel_id=channel_id,
                        published_at=None,
                        uploads_playlist_id=None,
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
    candidates = _search_websearch_google_cse(queries, config)
    if candidates:
        return candidates
    return _search_websearch_duckduckgo(queries, config)


def _search_websearch_google_cse(
    queries: list[str],
    config: YouTubeSearchConfig,
) -> list[YouTubeCandidate]:
    api_key = config.google_cse_api_key or os.getenv("GOOGLE_CSE_API_KEY")
    cx = config.google_cse_cx or os.getenv("GOOGLE_CSE_CX")
    if not api_key or not cx:
        return []
    candidates: list[YouTubeCandidate] = []
    with httpx.Client(timeout=10) as client:
        for query in queries:
            try:
                response = _with_retry(
                    lambda: client.get(
                        config.google_cse_endpoint,
                        params={
                            "key": api_key,
                            "cx": cx,
                            "q": query,
                            "num": 5,
                        },
                    ),
                    attempts=config.retry_attempts,
                    backoff=config.retry_backoff,
                )
                data = response.json()
            except Exception:
                LOGGER.warning("Google CSE fallback failed for query: %s", query)
                continue
            items = data.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                link = item.get("link")
                title = item.get("title")
                if not isinstance(link, str):
                    continue
                if "youtube.com" not in link and "youtu.be" not in link:
                    continue
                if not _is_channelish_youtube_url(link):
                    continue
                normalized = _normalize_url(link) or link
                handle = None
                if "/@" in normalized:
                    handle = _normalize_handle(normalized.split("/@")[-1].split("/")[0])
                channel_id = _extract_channel_id_from_url(normalized)
                candidates.append(
                    YouTubeCandidate(
                        title=title if isinstance(title, str) else None,
                        handle=handle,
                        url=normalized,
                        subscriber_count=None,
                        channel_id=channel_id,
                        published_at=None,
                        uploads_playlist_id=None,
                        source="websearch-google-cse",
                    )
                )
    return candidates


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
                published_at=first.published_at,
                uploads_playlist_id=first.uploads_playlist_id,
                source="websearch-domain-first",
            )
    return None


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip()
    if raw.startswith("@"):
        # Treat handles as canonical YouTube URLs.
        handle = _normalize_handle(raw)
        return f"https://www.youtube.com/{handle}"
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if raw.startswith("www."):
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
    except Exception:
        normalized = raw.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        return normalized or None
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").split("?", 1)[0].split("#", 1)[0]
    if "youtube.com" not in host and "youtu.be" not in host:
        normalized = raw.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        return normalized or None
    # Normalize common YouTube channel URL variants by trimming trailing sections.
    parts = [part for part in path.split("/") if part]
    if "youtu.be" in host:
        video_id = parts[0] if parts else ""
        normalized = f"https://youtu.be/{video_id}".rstrip("/")
        return normalized or None
    if "youtube.com" in host and parts:
        head = parts[0]
        if head.startswith("@"):
            parts = [head.lower()]
        elif head in {"channel", "c", "user"} and len(parts) >= 2:
            parts = [head, parts[1]]
    normalized_path = "/" + "/".join(parts) if parts else ""
    normalized = f"https://www.youtube.com{normalized_path}".rstrip("/")
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
    api_key = _youtube_api_key(config)
    if not api_key:
        return candidate

    channel_id = candidate.channel_id or _extract_channel_id_from_url(candidate.url)
    if not channel_id:
        username = _extract_username_from_url(candidate.url)
        if username:
            resolved = _youtube_api_channel_candidate_for_username(username, f"{candidate.source}+youtube-api-user", config)
            if resolved:
                return resolved
        handle = candidate.handle or _extract_handle_from_url(candidate.url)
        if handle:
            resolved = _youtube_api_channel_candidate_for_handle(handle, f"{candidate.source}+youtube-api-handle", config)
            if resolved:
                return resolved
            resolved_id = _youtube_api_resolve_channel_id_from_handle(handle, config)
            if resolved_id:
                channel_id = resolved_id
    if not channel_id:
        return candidate

    try:
        with httpx.Client(timeout=10) as client:
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
            payload = response.json()
            _maybe_disable_youtube_api_key(payload, api_key)
            if api_key in _INVALID_YOUTUBE_API_KEYS:
                return candidate
            items = payload.get("items", [])
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
            content_details = item.get("contentDetails", {}) if isinstance(item.get("contentDetails"), dict) else {}
            related_playlists = (
                content_details.get("relatedPlaylists", {})
                if isinstance(content_details.get("relatedPlaylists"), dict)
                else {}
            )
            uploads_playlist_id = (
                related_playlists.get("uploads")
                if isinstance(related_playlists.get("uploads"), str)
                else candidate.uploads_playlist_id
            )
            return YouTubeCandidate(
                title=snippet.get("title") if isinstance(snippet.get("title"), str) else candidate.title,
                handle=api_handle,
                url=api_url,
                subscriber_count=api_subscribers,
                channel_id=api_channel_id,
                source=f"{candidate.source}+youtube-api",
                published_at=snippet.get("publishedAt") if isinstance(snippet.get("publishedAt"), str) else candidate.published_at,
                uploads_playlist_id=uploads_playlist_id,
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
    if candidate.source.startswith("hint"):
        return True
    if candidate.source.startswith("website"):
        return True

    # If the lead already contains explicit evidence, don't require corroboration.
    lowered_queries = " ".join(queries).lower()
    if candidate.handle and candidate.handle.lower() in lowered_queries:
        return True
    if candidate.url and _normalize_url(candidate.url) and _normalize_url(candidate.url) in lowered_queries:
        return True
    has_serper = bool(config.websearch_api_key or os.getenv("SERPER_API_KEY"))
    has_cse = bool(
        (config.google_cse_api_key or os.getenv("GOOGLE_CSE_API_KEY"))
        and (config.google_cse_cx or os.getenv("GOOGLE_CSE_CX"))
    )
    has_web_provider = has_serper or has_cse
    if not has_web_provider:
        LOGGER.info("No websearch key configured; skipping strict YouTube web validation.")
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


def _extract_youtube_urls_from_jsonld(payload: object) -> set[str]:
    urls: set[str] = set()
    if isinstance(payload, dict):
        values = payload.get("sameAs")
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and ("youtube.com" in item or "youtu.be" in item):
                    urls.add(item)
        # Some sites put social links in nested structures.
        for value in payload.values():
            urls |= _extract_youtube_urls_from_jsonld(value)
    elif isinstance(payload, list):
        for item in payload:
            urls |= _extract_youtube_urls_from_jsonld(item)
    return urls


def _discover_youtube_urls_from_website(url: str, config: YouTubeSearchConfig) -> list[str]:
    normalized = url.strip()
    if not normalized:
        return []
    cache_key = normalized.lower()
    cached = _WEBSITE_YOUTUBE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    urls: set[str] = set()
    try:
        with httpx.Client(timeout=config.website_discovery_timeout, follow_redirects=True) as client:
            response = client.get(normalized, headers={"User-Agent": "Mozilla/5.0"})
            html = response.text
    except Exception:
        _WEBSITE_YOUTUBE_CACHE[cache_key] = []
        return []

    for match in _HTML_HREF_PATTERN.finditer(html):
        href = match.group(1)
        if "youtube.com" not in href and "youtu.be" not in href:
            continue
        urls.add(href)

    for match in _JSONLD_PATTERN.finditer(html):
        body = match.group("body").strip()
        if not body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        urls |= _extract_youtube_urls_from_jsonld(data)

    normalized_urls: list[str] = []
    for raw in urls:
        candidate = raw.strip()
        if not candidate:
            continue
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        normalized_candidate = _normalize_url(candidate) or candidate
        if _is_channelish_youtube_url(normalized_candidate):
            if normalized_candidate not in normalized_urls:
                normalized_urls.append(normalized_candidate)
    _WEBSITE_YOUTUBE_CACHE[cache_key] = normalized_urls
    return normalized_urls


def _website_discovery_candidates(queries: list[str], config: YouTubeSearchConfig) -> list[YouTubeCandidate]:
    if not config.website_discovery:
        return []
    domains = _extract_domains(queries)
    candidates: list[YouTubeCandidate] = []
    for domain in domains[: max(0, config.website_discovery_max_domains)]:
        for base in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            urls = _discover_youtube_urls_from_website(base, config)
            for url in urls:
                handle = _extract_handle_from_url(url)
                channel_id = _extract_channel_id_from_url(url)
                if not channel_id and handle and _youtube_api_key(config):
                    channel_id = _youtube_api_resolve_channel_id_from_handle(handle, config)
                if not channel_id and _extract_custom_from_url(url):
                    channel_id = _yt_dlp_resolve_channel_id(url, config)
                if channel_id:
                    resolved = _youtube_api_channel_candidate(channel_id, "website+youtube-api", config)
                    if resolved:
                        candidates.append(resolved)
                        continue
                candidates.append(
                    YouTubeCandidate(
                        title=None,
                        handle=handle,
                        url=url,
                        subscriber_count=None,
                        channel_id=channel_id,
                        source="website",
                    )
                )
        if candidates:
            break
    return _dedupe_candidates(candidates)


def find_best_youtube_channel(
    queries: list[str],
    *,
    config: YouTubeSearchConfig | None = None,
) -> YouTubeChannelData | None:
    config = config or YouTubeSearchConfig()
    base_queries = _dedupe_queries(queries)
    expanded_queries = _expand_youtube_queries(base_queries)
    signals = _lead_signals(base_queries)

    candidates: list[YouTubeCandidate] = []
    candidates.extend(_hint_candidates_from_queries(base_queries, config))
    # Website evidence is cheap (cached) and high-signal when a company domain is present.
    candidates.extend(_website_discovery_candidates(expanded_queries, config))
    candidates.extend(_search_scrapetube(expanded_queries, config))
    candidates.extend(_search_yt_search_python(expanded_queries, config))
    candidates.extend(_search_youtube_api(expanded_queries, config))
    candidates, evidence_sources = _merge_candidates(candidates)

    score_map = {
        _candidate_identity(c): _score_candidate(
            c,
            signals,
            evidence_count=len(evidence_sources.get(_candidate_identity(c), {c.source})),
        )
        for c in candidates
    }

    best, best_score, accepted = _select_best_candidate(
        candidates, signals, evidence_sources, config.score_threshold
    )

    if best is None or not accepted:
        web_candidates = _search_websearch(expanded_queries, config)
        candidates.extend(web_candidates)
        domain_fallback = _search_domain_first_hit(expanded_queries, config)
        if domain_fallback is not None:
            candidates.append(domain_fallback)
        candidates, evidence_sources = _merge_candidates(candidates)
        score_map = {
            _candidate_identity(c): _score_candidate(
                c,
                signals,
                evidence_count=len(evidence_sources.get(_candidate_identity(c), {c.source})),
            )
            for c in candidates
        }
        best, best_score, accepted = _select_best_candidate(
            candidates, signals, evidence_sources, config.score_threshold
        )
        # NOTE: Don't auto-accept domain-first fallbacks. They can be very noisy (e.g., matching a popular
        # "Dan Vega" channel for a "Dan Wega" lead just because of a weak web hit).
        # It's better to return low-confidence than a wrong assignment.

    if best is None:
        return None

    # If there are multiple plausible hits, let an LLM break ties using lead intent signals.
    llm_choice, llm_reject = _llm_rerank(
        queries,
        candidates,
        score_map,
        config,
        evidence_sources=evidence_sources,
    )
    llm_used_choice = llm_choice is not None
    llm_used_reject = bool(llm_reject)
    if llm_reject:
        accepted = False
    elif llm_choice is not None:
        best = llm_choice
        best_score = score_map.get(_candidate_identity(best), best_score)
        accepted = (best_score or 0) >= config.score_threshold

    best = _enrich_candidate_with_youtube_api(best, config)
    best_identity = _candidate_identity(best)
    best_evidence = sorted(evidence_sources.get(best_identity, {best.source}))
    best_affinity = _content_affinity(signals, best)
    content_mismatch = False
    web_validation_failed = False
    url_missing = False
    api_required = False
    api_verified: bool | None = None

    # Content sanity check: if the lead has strong anchors (domain / brand / email localpart),
    # don't accept a channel whose recent titles are completely unrelated unless we have
    # explicit evidence (hint/website).
    if accepted and not best.source.startswith(("hint", "website")) and signals.anchor_tokens:
        affinity = best_affinity
        if affinity is not None and affinity <= 0.0 and len(signals.anchor_tokens) >= 2:
            accepted = False
            content_mismatch = True
            best = YouTubeCandidate(
                title=best.title,
                handle=best.handle,
                url=best.url,
                subscriber_count=best.subscriber_count,
                channel_id=best.channel_id,
                published_at=best.published_at,
                uploads_playlist_id=best.uploads_playlist_id,
                source=f"{best.source}+content-mismatch",
            )
            best_identity = _candidate_identity(best)
            best_evidence = sorted(evidence_sources.get(best_identity, {best.source}))
    if accepted and not _validate_with_websearch(best, queries, config):
        accepted = False
        web_validation_failed = True
        LOGGER.warning(
            "YouTube candidate failed web validation: url=%s handle=%s source=%s",
            best.url,
            best.handle,
            best.source,
        )

    if accepted and best.url and not _youtube_url_exists(best.url):
        accepted = False
        url_missing = True
    # If we have a working YouTube API key, require API-verified existence for acceptance
    # unless the candidate came from explicit website evidence/hints.
    if accepted and _youtube_api_key(config) and not best.source.startswith(("hint", "website")):
        api_verified = "youtube-api" in best.source or (
            best.channel_id is not None and best.subscriber_count is not None
        )
        if not api_verified:
            accepted = False

    if accepted is False and _youtube_api_key(config) and api_verified is False:
        api_required = True

    def _confidence_reason() -> str | None:
        tags: list[str] = []
        evidence = best_evidence or []
        if any(s.startswith("hint") for s in evidence) or best.source.startswith("hint"):
            tags.append("hint")
        if any(s.startswith("website") for s in evidence) or best.source.startswith("website"):
            tags.append("website-link")
        if len(evidence) >= 2:
            tags.append(f"multi-source({len(evidence)})")
        if llm_used_choice:
            tags.append("llm-pick")
        if llm_used_reject:
            tags.append("llm-reject")
        if signals.anchor_tokens and best_affinity is not None:
            if content_mismatch or best_affinity <= 0.0:
                tags.append("content-mismatch")
            elif best_affinity < 0.10:
                tags.append("content-weak")
            else:
                tags.append("content-ok")
        if web_validation_failed:
            tags.append("web-fail")
        if url_missing:
            tags.append("404")
        api_active = _youtube_api_key(config) is not None
        if api_active:
            if api_verified:
                tags.append("api-verified")
            elif api_required:
                tags.append("api-needed")
        if not tags and best.source:
            tags.append(best.source.split("+", 1)[0])
        if not tags:
            return None
        return ", ".join(tags[:5])

    if not accepted:
        api_active = _youtube_api_key(config) is not None
        recent_titles = None
        # For UI/auditing: include a small content sample for borderline/rejected candidates
        # when we already had enough signal to compute affinity.
        if best_affinity is not None:
            recent_titles = _fetch_recent_video_titles(best, limit=5)
        return YouTubeChannelData(
            handle=best.handle,
            url=best.url,
            subscriber_count=best.subscriber_count if api_active and "youtube-api" in best.source else None,
            source_url=best.url,
            confidence=best_score,
            confidence_reason=_confidence_reason(),
            source=best.source,
            evidence_sources=best_evidence,
            recent_video_titles=recent_titles,
            content_affinity=best_affinity,
            accepted=False,
        )

    LOGGER.info("YouTube source channel: %s", best.url)

    publishing_cadence = None
    channel_age = _age_from_published_at(best.published_at)

    days_list: list[int] = []
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
        video_results = _coerce_video_results(videos)
        days_list = [
            days
            for days in (_relative_time_to_days(video.publishedTimeText) for video in video_results)
            if days is not None
        ]
        publishing_cadence = _cadence_from_days(days_list)
    except Exception:
        LOGGER.warning("Failed to fetch YouTube videos for %s", best.url)

    if publishing_cadence is None and best.uploads_playlist_id and _youtube_api_key(config):
        # Cheap and stable cadence signal.
        publishing_cadence = _youtube_api_uploads_cadence(best.uploads_playlist_id, config)

    if channel_age is None:
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

    api_active = _youtube_api_key(config) is not None
    recent_titles = None
    # Only fetch content samples when we have a reason to believe they'll be useful.
    if config.llm_rerank or best_affinity is not None:
        recent_titles = _fetch_recent_video_titles(best, limit=5)
    return YouTubeChannelData(
        handle=best.handle,
        url=best.url,
        subscriber_count=best.subscriber_count if api_active and "youtube-api" in best.source else None,
        publishing_cadence=publishing_cadence,
        channel_age=channel_age,
        source_url=best.url,
        confidence=best_score,
        confidence_reason=_confidence_reason(),
        source=best.source,
        evidence_sources=best_evidence,
        recent_video_titles=recent_titles,
        content_affinity=best_affinity,
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
            LOGGER.debug("YouTube lookup retry (attempt %s/%s).", attempt + 1, attempts)
            time.sleep(backoff * (attempt + 1))
    if last_error:
        raise last_error
    return None
