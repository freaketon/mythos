from __future__ import annotations

from pathlib import Path

from src.adapters.instagram import InstagramProfileData
from src.adapters.youtube import YouTubeChannelData
from src.csv_pipeline import copy_csv_rows


def test_pipeline_mixed_rows_summary(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email,Company URL\n"
        "MrBeast,mrbeast@example.com,https://www.youtube.com/@MrBeast\n"
        "NoMatch,nomatch@example.com,https://example.com\n"
        "BadRow\n",
        encoding="utf-8",
    )

    def fake_youtube_lookup(queries: list[str]) -> YouTubeChannelData | None:
        if any("MrBeast" in query for query in queries):
            return YouTubeChannelData(
                handle="@MrBeast",
                url="https://www.youtube.com/@MrBeast",
                subscriber_count=100_000_000,
                publishing_cadence="Weekly or more",
                channel_age="10 years",
                source_url="https://www.youtube.com/@MrBeast",
            )
        return None

    def fake_instagram_lookup(query: str) -> InstagramProfileData | None:
        if "MrBeast" in query:
            return InstagramProfileData(
                handle="mrbeast",
                followers=1234,
                publishing_cadence="Monthly",
                account_age="2 years",
                source_url="https://www.instagram.com/mrbeast/",
            )
        return None

    report = copy_csv_rows(
        input_csv,
        output_csv,
        youtube_lookup=fake_youtube_lookup,
        instagram_lookup=fake_instagram_lookup,
    )

    assert report.total_rows == 3
    assert report.valid_rows == 2
    assert report.invalid_rows == 1
    assert report.hydrated_youtube_rows == 1
    assert report.hydrated_instagram_rows == 1
    assert report.warning_rows == 2
    assert report.low_confidence_rows == []

    output_text = output_csv.read_text(encoding="utf-8")
    assert "MrBeast" in output_text
    assert "NoMatch" in output_text
