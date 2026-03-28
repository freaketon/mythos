from __future__ import annotations

from src.adapters import youtube as youtube_adapter
from src.adapters.youtube import YouTubeCandidate, YouTubeSearchConfig, find_best_youtube_channel


def _fake_merge(candidates: list[YouTubeCandidate]):  # noqa: ANN001
    evidence: dict[str, set[str]] = {}
    for c in candidates:
        ident = youtube_adapter._candidate_identity(c)
        evidence.setdefault(ident, set()).add(c.source)
    return candidates, evidence


def test_youtube_rejects_candidate_conflicting_with_single_website_link(monkeypatch) -> None:
    website = YouTubeCandidate(
        title="Acme Official",
        handle="@acmeofficial",
        url="https://www.youtube.com/@acmeofficial",
        subscriber_count=None,
        channel_id="UCACME",
        source="website:https://acme.com",
    )
    other = YouTubeCandidate(
        title="Popular Unrelated",
        handle="@popular",
        url="https://www.youtube.com/@popular",
        subscriber_count=123456,
        channel_id="UCPOPULAR",
        source="scrapetube",
    )

    monkeypatch.setattr(youtube_adapter, "_hint_candidates_from_queries", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_website_discovery_candidates", lambda *_a, **_k: [website])
    monkeypatch.setattr(youtube_adapter, "_search_scrapetube", lambda *_a, **_k: [other])
    monkeypatch.setattr(youtube_adapter, "_search_yt_search_python", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_search_youtube_api", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_merge_candidates", lambda cands: _fake_merge(cands))
    monkeypatch.setattr(youtube_adapter, "_select_best_candidate", lambda *_a, **_k: (other, 90, True))
    monkeypatch.setattr(youtube_adapter, "_llm_rerank", lambda *_a, **_k: (None, False))
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda cand, _cfg: cand)
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube_adapter, "_youtube_url_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube_adapter, "_channel_metrics_from_html", lambda *_a, **_k: {})
    monkeypatch.setattr(youtube_adapter.scrapetube, "get_channel", lambda **_k: [])
    monkeypatch.setattr(youtube_adapter, "_fetch_recent_video_titles", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_content_affinity", lambda *_a, **_k: 0.5)

    result = find_best_youtube_channel(["Acme Inc acme.com"], config=YouTubeSearchConfig(web_validation=False))
    assert result is not None
    assert result.accepted is False
    assert result.confidence_reason is not None
    assert "website-conflict" in result.confidence_reason


def test_youtube_accepts_when_best_matches_website_link(monkeypatch) -> None:
    website = YouTubeCandidate(
        title="Acme Official",
        handle="@acmeofficial",
        url="https://www.youtube.com/@acmeofficial",
        subscriber_count=1000,
        channel_id="UCACME",
        source="website:https://acme.com",
    )

    monkeypatch.setattr(youtube_adapter, "_hint_candidates_from_queries", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_website_discovery_candidates", lambda *_a, **_k: [website])
    monkeypatch.setattr(youtube_adapter, "_search_scrapetube", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_search_yt_search_python", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_search_youtube_api", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_merge_candidates", lambda cands: _fake_merge(cands))
    monkeypatch.setattr(youtube_adapter, "_select_best_candidate", lambda *_a, **_k: (website, 90, True))
    monkeypatch.setattr(youtube_adapter, "_llm_rerank", lambda *_a, **_k: (None, False))
    monkeypatch.setattr(youtube_adapter, "_enrich_candidate_with_youtube_api", lambda cand, _cfg: cand)
    monkeypatch.setattr(youtube_adapter, "_validate_with_websearch", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube_adapter, "_youtube_url_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(youtube_adapter, "_channel_metrics_from_html", lambda *_a, **_k: {})
    monkeypatch.setattr(youtube_adapter.scrapetube, "get_channel", lambda **_k: [])
    monkeypatch.setattr(youtube_adapter, "_fetch_recent_video_titles", lambda *_a, **_k: [])
    monkeypatch.setattr(youtube_adapter, "_content_affinity", lambda *_a, **_k: 0.5)

    result = find_best_youtube_channel(["Acme Inc acme.com"], config=YouTubeSearchConfig(web_validation=False))
    assert result is not None
    assert result.accepted is True
    assert result.evidence_sources is not None
    assert any(s.startswith("website:https://acme.com") for s in result.evidence_sources)

