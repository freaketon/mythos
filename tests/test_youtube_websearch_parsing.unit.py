from __future__ import annotations

import src.adapters.youtube as youtube


def test_hint_candidates_from_queries_parses_handle_and_url(monkeypatch) -> None:
    monkeypatch.setattr(youtube, "_youtube_url_exists", lambda *_a, **_k: True)

    candidates = youtube._hint_candidates_from_queries(
        ["@SomeHandle", "https://www.youtube.com/@OtherHandle/featured"],
        youtube.YouTubeSearchConfig(),
    )

    assert any(c.source == "hint-handle" and c.handle == "@SomeHandle" for c in candidates)
    assert any(c.source == "hint-url" and c.url == "https://www.youtube.com/@otherhandle" for c in candidates)


def test_search_websearch_duckduckgo_extracts_channel(monkeypatch) -> None:
    html = (
        '<html><body>'
        '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.youtube.com%2F%40GovKidMethod">x</a>'
        "</body></html>"
    )

    class FakeResp:
        def __init__(self, text: str):
            self.text = text

    class FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def get(self, url, params=None, headers=None, follow_redirects=None):  # noqa: ANN001
            return FakeResp(html)

    monkeypatch.setattr(youtube.httpx, "Client", FakeClient)

    config = youtube.YouTubeSearchConfig(websearch_api_key=None, google_cse_api_key=None, google_cse_cx=None)
    out = youtube._search_websearch_duckduckgo(["govkidmethod youtube"], config)
    assert out
    assert out[0].url == "https://www.youtube.com/@govkidmethod"
    assert out[0].source == "websearch-ddg"


def test_search_websearch_serper_extracts_channelish_links(monkeypatch) -> None:
    class FakeResp:
        def json(self):
            return {
                "organic": [
                    {"link": "https://example.com/not-youtube", "title": "x"},
                    {"link": "https://www.youtube.com/watch?v=abc123", "title": "video"},
                    {"link": "https://www.youtube.com/@RealChannel", "title": "Real Channel"},
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def post(self, url, headers=None, json=None):  # noqa: ANN001
            return FakeResp()

    monkeypatch.setattr(youtube.httpx, "Client", FakeClient)

    config = youtube.YouTubeSearchConfig(websearch_api_key="fake")
    out = youtube._search_websearch_serper(["q"], config)
    assert len(out) == 1
    assert out[0].url == "https://www.youtube.com/@realchannel"
    assert out[0].handle in {"@realchannel", "@RealChannel"}
    assert out[0].source == "websearch"
