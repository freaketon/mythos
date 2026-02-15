from __future__ import annotations

from typing import Iterable

import scrapetube
from youtubesearchpython import ChannelsSearch

import src.adapters.youtube as youtube_adapter
from src.adapters.youtube import (
    YouTubeChannelData,
    YouTubeSearchConfig,
    find_best_youtube_channel,
    find_youtube_channel,
)

import pytest


@pytest.fixture(autouse=True)
def _disable_website_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests hermetic: website discovery performs live HTTP fetches.
    monkeypatch.setattr(youtube_adapter, "_website_discovery_candidates", lambda *_a, **_k: [])
    # Keep tests hermetic: existence checks perform live HTTP fetches.
    monkeypatch.setattr(youtube_adapter, "_youtube_url_exists", lambda *_a, **_k: True)
    # Keep tests hermetic: video sampling performs live HTTP fetches via scrapetube.
    monkeypatch.setattr(scrapetube, "get_channel", lambda *_a, **_k: [])


def _fake_search_results() -> Iterable[dict[str, str]]:
    return [
        {
            "channelId": "UC123",
            "channelTitle": "MrBeast",
            "channelHandle": "@MrBeast",
            "subscriberCountText": "100M subscribers",
        }
    ]


def _fake_channel_results(limit: int, sort_by: str | None) -> Iterable[dict[str, str]]:
    if sort_by == "oldest":
        return [{"publishedTimeText": "10 years ago"}]
    return [
        {"publishedTimeText": "2 days ago"},
        {"publishedTimeText": "9 days ago"},
        {"publishedTimeText": "15 days ago"},
    ][:limit]


def test_find_youtube_channel_integration(monkeypatch) -> None:
    def fake_get_search(*_args, **_kwargs):
        return _fake_search_results()

    def fake_get_channel(*_args, **kwargs):
        limit = kwargs.get("limit", 12)
        sort_by = kwargs.get("sort_by")
        return _fake_channel_results(limit, sort_by)

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)

    result = find_youtube_channel(
        "MrBeast",
        config=YouTubeSearchConfig(web_validation=False),
    )

    assert isinstance(result, YouTubeChannelData)
    assert result.handle == "@MrBeast"
    assert result.url == "https://www.youtube.com/@MrBeast"
    assert result.subscriber_count == 100_000_000
    assert result.subscriber_count_source == "scrapetube"
    assert result.publishing_cadence == "Weekly or more"
    assert result.channel_age == "10 years"


def test_find_best_youtube_channel_falls_back_to_yt_search(monkeypatch) -> None:
    def fake_get_search(*_args, **_kwargs):
        return []

    def fake_get_channel(*_args, **_kwargs):
        return [{"publishedTimeText": "2 years ago"}]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UC999",
                        "title": "Mock Client",
                        "subscribers": "@MockClient",
                        "link": "https://www.youtube.com/channel/UC999",
                    }
                ]
            }

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)

    result = find_best_youtube_channel(
        ["Mock Client YouTube"],
        config=YouTubeSearchConfig(web_validation=False),
    )

    assert result is not None
    assert result.handle == "@MockClient"
    assert result.url == "https://www.youtube.com/channel/UC999"
    assert result.accepted is True


def test_find_best_youtube_channel_keeps_searching_when_first_source_is_weak(
    monkeypatch,
) -> None:
    def fake_get_search(*_args, **_kwargs):
        return [
            {
                "channelId": "UCWRONG",
                "channelTitle": "Unrelated Channel",
                "channelHandle": "@unrelated",
                "subscriberCountText": "1K subscribers",
            }
        ]

    def fake_get_channel(*_args, **_kwargs):
        return [{"publishedTimeText": "2 years ago"}]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UCGBS",
                        "title": "GBS Arbeitsschutz",
                        "subscribers": "@gbs_arbeitsschutz",
                        "link": "https://www.youtube.com/@gbs_arbeitsschutz",
                    }
                ]
            }

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)

    result = find_best_youtube_channel(
        ["gbs-arbeitsschutz"],
        config=YouTubeSearchConfig(web_validation=False),
    )

    assert result is not None
    assert result.handle == "@gbs_arbeitsschutz"
    assert result.url == "https://www.youtube.com/@gbs_arbeitsschutz"
    assert result.accepted is True


def test_find_best_youtube_channel_survives_scrapetube_error(monkeypatch) -> None:
    def fake_get_search(*_args, **_kwargs):
        raise RuntimeError("network ssl failure")

    def fake_get_channel(*_args, **_kwargs):
        return [{"publishedTimeText": "2 years ago"}]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UC404",
                        "title": "Fallback Channel",
                        "subscribers": "@FallbackChannel",
                        "link": "https://www.youtube.com/channel/UC404",
                    }
                ]
            }

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)

    result = find_best_youtube_channel(
        ["Fallback Channel YouTube"],
        config=YouTubeSearchConfig(web_validation=False),
    )

    assert result is not None
    assert result.url == "https://www.youtube.com/channel/UC404"
    assert result.accepted is True


def test_find_best_youtube_channel_survives_scrapetube_generator_error(
    monkeypatch,
) -> None:
    def fake_get_search(*_args, **_kwargs):
        def _generator():
            raise RuntimeError("generator ssl failure")
            yield {}  # pragma: no cover

        return _generator()

    def fake_get_channel(*_args, **_kwargs):
        return [{"publishedTimeText": "2 years ago"}]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UC405",
                        "title": "Fallback Channel 2",
                        "subscribers": "@FallbackChannel2",
                        "link": "https://www.youtube.com/channel/UC405",
                    }
                ]
            }

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)

    result = find_best_youtube_channel(
        ["Fallback Channel 2 YouTube"],
        config=YouTubeSearchConfig(web_validation=False),
    )

    assert result is not None
    assert result.url == "https://www.youtube.com/channel/UC405"
    assert result.accepted is True


def test_find_best_youtube_channel_marks_unvalidated_candidate_low_confidence(
    monkeypatch,
) -> None:
    def fake_get_search(*_args, **_kwargs):
        return _fake_search_results()

    def fake_get_channel(*_args, **_kwargs):
        return _fake_channel_results(12, None)

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(youtube_adapter, "_search_websearch", lambda *_args, **_kwargs: [])

    result = find_best_youtube_channel(
        ["MrBeast YouTube"],
        config=YouTubeSearchConfig(websearch_api_key="fake-key"),
    )

    assert result is not None
    assert result.accepted is False
    assert result.url == "https://www.youtube.com/@MrBeast"


def test_find_best_youtube_channel_accepts_when_no_api_key_and_no_web_results(
    monkeypatch,
) -> None:
    # Deterministic behavior: local dev machines may have SERPER/YOUTUBE keys set (or loaded from .env).
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    def fake_get_search(*_args, **_kwargs):
        return _fake_search_results()

    def fake_get_channel(*_args, **_kwargs):
        return _fake_channel_results(12, None)

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(youtube_adapter, "_search_websearch", lambda *_args, **_kwargs: [])

    result = find_best_youtube_channel(
        ["MrBeast YouTube"],
        config=YouTubeSearchConfig(web_validation=True),
    )

    assert result is not None
    assert result.accepted is True
    assert result.url == "https://www.youtube.com/@MrBeast"


def test_find_best_youtube_channel_enriches_from_youtube_api_when_key_present(
    monkeypatch,
) -> None:
    def fake_get_search(*_args, **_kwargs):
        return _fake_search_results()

    def fake_get_channel(*_args, **kwargs):
        limit = kwargs.get("limit", 12)
        sort_by = kwargs.get("sort_by")
        return _fake_channel_results(limit, sort_by)

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, params: dict | None = None):
            assert params is not None
            if "youtube/v3/channels" in url:
                return FakeResponse(
                    {
                        "items": [
                            {
                                "id": "UC123",
                                "snippet": {"title": "MrBeast", "customUrl": "@MrBeastOfficial"},
                                "statistics": {"subscriberCount": "101234567"},
                            }
                        ]
                    }
                )
            return FakeResponse({"items": []})

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(scrapetube, "get_channel", fake_get_channel)
    monkeypatch.setattr(youtube_adapter.httpx, "Client", FakeClient)
    monkeypatch.setattr(youtube_adapter, "_search_websearch", lambda *_args, **_kwargs: [])

    result = find_best_youtube_channel(
        ["MrBeast YouTube"],
        config=YouTubeSearchConfig(
            youtube_api_key="fake-key",
            web_validation=False,
        ),
    )

    assert result is not None
    assert result.accepted is True
    assert result.subscriber_count == 101_234_567
    assert result.handle == "@MrBeastOfficial"


def test_youtube_web_validation_falls_back_to_duckduckgo(monkeypatch) -> None:
    candidate = youtube_adapter.YouTubeCandidate(
        title="Example Channel",
        handle="@ExampleChannel",
        url="https://www.youtube.com/@ExampleChannel",
        subscriber_count=1000,
        channel_id=None,
        published_at=None,
        source="yt-search-python",
    )
    monkeypatch.setattr(youtube_adapter, "_search_websearch_serper", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        youtube_adapter,
        "_search_websearch_duckduckgo",
        lambda *_args, **_kwargs: [
            youtube_adapter.YouTubeCandidate(
                title=None,
                handle="@ExampleChannel",
                url="https://www.youtube.com/@ExampleChannel",
                subscriber_count=None,
                channel_id=None,
                published_at=None,
                source="websearch-ddg",
            )
        ],
    )
    assert (
        youtube_adapter._validate_with_websearch(
            candidate,
            ["Example Channel YouTube"],
            YouTubeSearchConfig(web_validation=True),
        )
        is True
    )


def test_youtube_domain_fallback_uses_first_web_hit(monkeypatch) -> None:
    monkeypatch.setattr(youtube_adapter, "_search_scrapetube", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_yt_search_python", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_youtube_api", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        youtube_adapter,
        "_search_websearch",
        lambda queries, *_args, **_kwargs: [
            youtube_adapter.YouTubeCandidate(
                title="Gov Kid Method",
                handle="@govkidmethod",
                url="https://www.youtube.com/@govkidmethod",
                subscriber_count=None,
                channel_id=None,
                published_at=None,
                source="websearch",
            )
        ]
        if any("govkidmethod.com youtube" in q for q in queries)
        else [],
    )
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda c, *_args, **_kwargs: c)

    result = find_best_youtube_channel(["Derek James govkidmethod.com"])
    assert result is not None
    assert result.accepted is True
    assert result.url == "https://www.youtube.com/@govkidmethod"
    assert result.source in {"websearch-domain-first", "websearch"}


def test_domain_first_fallback_is_not_auto_accepted(monkeypatch) -> None:
    # Regression guard: domain-first is noisy; it must not be forced accepted when below threshold.
    monkeypatch.setattr(youtube_adapter, "_hint_candidates_from_queries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_scrapetube", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_yt_search_python", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_youtube_api", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(youtube_adapter, "_search_websearch", lambda *_args, **_kwargs: [])

    monkeypatch.setattr(
        youtube_adapter,
        "_search_domain_first_hit",
        lambda *_args, **_kwargs: youtube_adapter.YouTubeCandidate(
            title="Popular Channel",
            handle="@popular",
            url="https://www.youtube.com/@popular",
            subscriber_count=None,
            channel_id=None,
            published_at=None,
            uploads_playlist_id=None,
            source="websearch-domain-first",
        ),
    )
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda c, *_a, **_k: c)

    result = find_best_youtube_channel(
        ["example.com youtube"],
        config=YouTubeSearchConfig(web_validation=False, score_threshold=999),
    )
    assert result is not None
    assert result.url == "https://www.youtube.com/@popular"
    assert result.accepted is False


def test_llm_rerank_picks_better_candidate(monkeypatch) -> None:
    def fake_get_search(*_args, **_kwargs):
        return [
            {
                "channelId": "UC123",
                "channelTitle": "Right Channel",
                "channelHandle": "@right",
                "subscriberCountText": "100K subscribers",
            }
        ]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UC999",
                        "title": "Right Channel",
                        "subscribers": "@right",
                        "link": "https://www.youtube.com/@right",
                    }
                ]
            }

    class FakeResponse:
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"decision":"accept","best_index": 0, "confidence": 90, "reason": "Better match."}'
                        }
                    }
                ]
            }

    def fake_post(self, url, headers=None, json=None):  # type: ignore[no-untyped-def]
        assert "chat/completions" in url
        return FakeResponse()

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)
    monkeypatch.setattr(youtube_adapter.httpx.Client, "post", fake_post, raising=False)
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda c, *_a, **_k: c)

    result = find_best_youtube_channel(
        ["Right Channel"],
        config=YouTubeSearchConfig(llm_rerank=True, openai_api_key="fake"),
    )
    assert result is not None
    assert result.url == "https://www.youtube.com/@right"


def test_llm_rerank_can_reject_all_candidates(monkeypatch) -> None:
    def fake_get_search(*_args, **_kwargs):
        return [
            {
                "channelId": "UC123",
                "channelTitle": "Wrong Channel",
                "channelHandle": "@wrong",
                "subscriberCountText": "100K subscribers",
            }
        ]

    class FakeChannelsSearch:
        def __init__(self, *_args, **_kwargs):
            pass

        def result(self):
            return {
                "result": [
                    {
                        "id": "UC999",
                        "title": "Also Wrong",
                        "subscribers": "@also_wrong",
                        "link": "https://www.youtube.com/@also_wrong",
                    }
                ]
            }

    class FakeResponse:
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"decision":"reject","best_index": 0, "confidence": 80, "reason": "Unrelated."}'
                        }
                    }
                ]
            }

    def fake_post(self, url, headers=None, json=None):  # type: ignore[no-untyped-def]
        assert "chat/completions" in url
        return FakeResponse()

    monkeypatch.setattr(scrapetube, "get_search", fake_get_search)
    monkeypatch.setattr(ChannelsSearch, "__init__", FakeChannelsSearch.__init__)
    monkeypatch.setattr(ChannelsSearch, "result", FakeChannelsSearch.result)
    monkeypatch.setattr(youtube_adapter.httpx.Client, "post", fake_post, raising=False)
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda c, *_a, **_k: c)

    result = find_best_youtube_channel(
        ["Some Lead"],
        config=YouTubeSearchConfig(llm_rerank=True, openai_api_key="fake", web_validation=False),
    )
    assert result is not None
    assert result.accepted is False
