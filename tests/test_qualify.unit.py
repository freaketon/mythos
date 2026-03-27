from __future__ import annotations

import json
from pathlib import Path

from src.qualify import JSONLCache, QualifyConfig, qualify_rows


def test_qualify_rows_ranks_and_emits_ig_dm_message(tmp_path: Path) -> None:
    rows = [
        {"Name": "Low Fit", "Youtube URL": "https://www.youtube.com/@low"},
        {"Name": "High Fit", "Youtube URL": "https://www.youtube.com/@high"},
    ]

    def fake_fetch_titles(row, limit):  # noqa: ANN001
        assert limit == 5
        url = (row.get("Youtube URL") or "")
        return ["Outbound messaging", "Cold outreach"] if "high" in url else ["Minecraft speedrun"]

    calls: list[str] = []

    def fake_llm(payload):  # noqa: ANN001
        calls.append(str(payload.get("name") or ""))
        if payload.get("name") == "High Fit":
            return {
                "fit_score": 92,
                "theme": "B2B marketing",
                "recent_video_topic": "Outbound messaging",
                "icp_fit_summary": "Strong fit.",
                "pitch_angle": "Personalized outbound at scale.",
                "ig_dm_message": "Loved your latest on outbound. Quick idea...",
            }
        return {
            "fit_score": 20,
            "theme": "Gaming",
            "recent_video_topic": "Speedrun",
            "icp_fit_summary": "Not a fit.",
            "pitch_angle": "",
            "ig_dm_message": "",
        }

    out = qualify_rows(
        rows,
        icp_prompt="ICP",
        product_prompt="PRODUCT",
        config=QualifyConfig(cache_path=tmp_path / "cache.jsonl"),
        llm_call=fake_llm,
        fetch_titles=fake_fetch_titles,
    )

    assert [r["Name"] for r in out] == ["High Fit", "Low Fit"]
    assert out[0]["qual_fit_score"] == "92"
    assert out[0]["qual_ig_dm_message"].startswith("Loved")
    assert json.loads(out[0]["qual_youtube_titles_json"]) == ["Outbound messaging", "Cold outreach"]
    assert len(calls) == 2


def test_qualify_rows_uses_cache_to_skip_llm_calls(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    cache = JSONLCache(cache_path)
    cache.put(
        "Youtube URL:https://www.youtube.com/@cached",
        {
            "fit_score": 77,
            "theme": "Creator ops",
            "recent_video_topic": "Workflow",
            "icp_fit_summary": "Fit.",
            "pitch_angle": "Automation",
            "ig_dm_message": "Hi",
        },
    )

    rows = [{"Name": "Cached", "Youtube URL": "https://www.youtube.com/@cached"}]
    calls = 0

    def fake_llm(_payload):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return {}

    out = qualify_rows(
        rows,
        icp_prompt="ICP",
        product_prompt="PRODUCT",
        config=QualifyConfig(cache_path=cache_path),
        llm_call=fake_llm,
        fetch_titles=lambda _row, _limit: [],
    )
    assert out[0]["qual_fit_score"] == "77"
    assert calls == 0


def test_qualify_rows_continues_on_llm_failure(tmp_path: Path) -> None:
    rows = [
        {"Name": "A", "Youtube URL": "https://www.youtube.com/@a"},
        {"Name": "B", "Youtube URL": "https://www.youtube.com/@b"},
    ]

    def fake_llm(payload):  # noqa: ANN001
        if payload.get("name") == "A":
            return {
                "fit_score": 80,
                "theme": "X",
                "recent_video_topic": "Y",
                "icp_fit_summary": "Z",
                "pitch_angle": "P",
                "ig_dm_message": "M",
            }
        raise ValueError("boom")

    out = qualify_rows(
        rows,
        icp_prompt="ICP",
        product_prompt="PRODUCT",
        config=QualifyConfig(cache_path=tmp_path / "cache.jsonl", max_retries=1),
        llm_call=fake_llm,
        fetch_titles=lambda _row, _limit: [],
    )
    assert len(out) == 2
    # One ok, one error.
    assert any(r["Name"] == "A" and r["qual_status"] == "ok" for r in out)
    assert any(r["Name"] == "B" and r["qual_status"] == "error" for r in out)

