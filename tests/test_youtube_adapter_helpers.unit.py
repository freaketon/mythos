from __future__ import annotations

import src.adapters.youtube as youtube


def test_normalize_url_channel_variants() -> None:
    assert (
        youtube._normalize_url("https://www.youtube.com/@DanVega/featured?x=1")
        == "https://www.youtube.com/@danvega"
    )
    assert (
        youtube._normalize_url("https://www.youtube.com/channel/UC123/videos")
        == "https://www.youtube.com/channel/UC123"
    )
    assert (
        youtube._normalize_url("https://www.youtube.com/user/SomeUser/about")
        == "https://www.youtube.com/user/SomeUser"
    )
    assert (
        youtube._normalize_url("https://www.youtube.com/c/CustomName/videos")
        == "https://www.youtube.com/c/CustomName"
    )
    assert youtube._normalize_url("@SomeHandle") == "https://www.youtube.com/@SomeHandle"


def test_extract_video_id_variants() -> None:
    assert youtube._extract_video_id("https://youtu.be/abc123") == "abc123"
    assert youtube._extract_video_id("https://www.youtube.com/watch?v=xyz789") == "xyz789"
    assert youtube._extract_video_id("https://example.com/watch?v=xyz789") is None


def test_parse_subscriber_count() -> None:
    assert youtube._parse_subscriber_count("1.2K subscribers") == 1200
    assert youtube._parse_subscriber_count("3M subscribers") == 3_000_000
    assert youtube._parse_subscriber_count("987 subscribers") == 987
    assert youtube._parse_subscriber_count("nope") is None


def test_relative_time_to_days() -> None:
    assert youtube._relative_time_to_days("2 days ago") == 2
    assert youtube._relative_time_to_days("3 weeks ago") == 21
    assert youtube._relative_time_to_days("2 months ago") == 60
    assert youtube._relative_time_to_days("1 year ago") == 365
    assert youtube._relative_time_to_days("yesterday") is None


def test_youtube_url_exists_rejects_error_pages(monkeypatch) -> None:
    class FakeResp:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    class FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def get(self, url, headers=None):  # noqa: ANN001
            if "missing" in url:
                return FakeResp(404, "not found")
            if "friendly" in url:
                return FakeResp(200, "This page isn't available")
            return FakeResp(200, "<html>ok</html>")

    monkeypatch.setattr(youtube.httpx, "Client", FakeClient)

    assert youtube._youtube_url_exists("https://www.youtube.com/@missing") is False
    assert youtube._youtube_url_exists("https://www.youtube.com/@friendly") is False
    assert youtube._youtube_url_exists("https://www.youtube.com/@real") is True


def test_merge_candidates_keeps_evidence_sources() -> None:
    a = youtube.YouTubeCandidate(
        title="A",
        handle="@a",
        url="https://www.youtube.com/@a",
        subscriber_count=None,
        channel_id=None,
        published_at=None,
        uploads_playlist_id=None,
        source="scrapetube",
    )
    b = youtube.YouTubeCandidate(
        title="A Channel",
        handle="@a",
        url="https://www.youtube.com/@a",
        subscriber_count=123,
        channel_id="UC123",
        published_at="2020-01-01T00:00:00Z",
        uploads_playlist_id=None,
        source="websearch-domain-first",
    )
    merged, evidence = youtube._merge_candidates([a, b])
    assert len(merged) == 1
    ident = youtube._candidate_identity(merged[0])
    assert evidence[ident] == {"scrapetube", "websearch-domain-first"}
    # Prefer a stable source label when multiple sources agree.
    assert merged[0].source == "websearch-domain-first"
    # And keep richer fields.
    assert merged[0].channel_id == "UC123"
    assert merged[0].subscriber_count == 123


def test_extract_anchor_tokens_splits_brand_suffixes() -> None:
    anchors = youtube._extract_anchor_tokens(
        ["danrichardscoaching youtube", "example.com youtube"]
    )
    assert "danrichardscoaching" in anchors
    assert "danrichards" in anchors
    assert "coaching" in anchors
    assert "example" in anchors


def test_content_mismatch_downgrades_when_multiple_anchors(monkeypatch) -> None:
    # Force a plausible but wrong match (accepted due to low threshold), then ensure
    # content mismatch rejects it when anchors exist.
    monkeypatch.setattr(youtube, "_hint_candidates_from_queries", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube, "_website_discovery_candidates", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube, "_search_scrapetube", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube, "_search_yt_search_python", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube, "_search_youtube_api", lambda *_a, **_k: [])
    monkeypatch.setattr(
        youtube,
        "_search_websearch",
        lambda *_a, **_k: [
            youtube.YouTubeCandidate(
                title="Dan Vega",
                handle="@danvega",
                url="https://www.youtube.com/@danvega",
                subscriber_count=None,
                channel_id=None,
                published_at=None,
                uploads_playlist_id=None,
                source="websearch",
            )
        ],
    )
    monkeypatch.setattr(youtube, "_search_domain_first_hit", lambda *_a, **_k: None)
    monkeypatch.setattr(youtube, "_validate_with_websearch", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube, "_enrich_candidate_with_youtube_api", lambda c, *_a, **_k: c)
    monkeypatch.setattr(youtube, "_youtube_url_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube, "_fetch_recent_video_titles", lambda *_a, **_k: ["Totally unrelated topic"])

    result = youtube.find_best_youtube_channel(
        ["Dan Wega youtube", "danwega youtube", "premierpaintingmi.com youtube"],
        config=youtube.YouTubeSearchConfig(web_validation=False, score_threshold=15),
    )
    assert result is not None
    assert result.accepted is False
    assert result.url == "https://www.youtube.com/@danvega"
    assert result.source is not None and "content-mismatch" in result.source
