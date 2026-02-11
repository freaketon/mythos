from __future__ import annotations

from typing import Iterable

import scrapetube
from youtubesearchpython import ChannelsSearch

from src.adapters.youtube import YouTubeChannelData, find_best_youtube_channel, find_youtube_channel


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

    result = find_youtube_channel("MrBeast")

    assert isinstance(result, YouTubeChannelData)
    assert result.handle == "@MrBeast"
    assert result.url == "https://www.youtube.com/@MrBeast"
    assert result.subscriber_count == 100_000_000
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

    result = find_best_youtube_channel(["Mock Client YouTube"])

    assert result is not None
    assert result.handle == "@MockClient"
    assert result.url == "https://www.youtube.com/channel/UC999"
    assert result.accepted is True
