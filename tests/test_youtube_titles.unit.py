from __future__ import annotations

from src.adapters import youtube as youtube_adapter


def test_fetch_recent_video_titles_extracts_titles(monkeypatch) -> None:
    # scrapetube returns heterogeneous title payloads depending on endpoint.
    monkeypatch.setattr(
        youtube_adapter.scrapetube,
        "get_channel",
        lambda **_kwargs: [
            {"title": {"runs": [{"text": "Most Recent Video"}]}},
            {"title": {"simpleText": "Second Video"}},
            {"title": "Third Video"},
            {"title": {"runs": [{"text": "  Fourth  "}]}}
        ],
    )

    titles = youtube_adapter.fetch_recent_video_titles(channel_url="https://www.youtube.com/@acme", limit=10)
    assert titles == ["Most Recent Video", "Second Video", "Third Video", "Fourth"]


def test_fetch_recent_video_titles_dedupes_and_limits(monkeypatch) -> None:
    monkeypatch.setattr(
        youtube_adapter.scrapetube,
        "get_channel",
        lambda **_kwargs: [
            {"title": {"simpleText": "A"}},
            {"title": {"simpleText": "A"}},
            {"title": {"simpleText": "B"}},
        ],
    )
    titles = youtube_adapter.fetch_recent_video_titles(channel_id="UC123", limit=2)
    assert titles == ["A", "B"]

