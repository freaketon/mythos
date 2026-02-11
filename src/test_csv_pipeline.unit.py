from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.youtube import YouTubeChannelData
from src.adapters.instagram import InstagramProfileData
from src.csv_pipeline import copy_csv_rows


def test_copy_csv_rows_reports_valid_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nAlice,alice@example.com\nBob,bob@example.com\n",
        encoding="utf-8",
    )

    report = copy_csv_rows(input_csv, output_csv)

    assert report.total_rows == 2
    assert report.valid_rows == 2
    assert report.invalid_rows == 0
    assert report.issues == []
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Alice,alice@example.com,,,,,,,,,\n"
        "Bob,bob@example.com,,,,,,,,,\n"
    )


def test_copy_csv_rows_skips_invalid_rows_in_non_strict_mode(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nAlice,alice@example.com\nBob\n",
        encoding="utf-8",
    )

    report = copy_csv_rows(input_csv, output_csv, strict=False)

    assert report.total_rows == 2
    assert report.valid_rows == 1
    assert report.invalid_rows == 1
    assert len(report.issues) == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Alice,alice@example.com,,,,,,,,,\n"
    )


def test_copy_csv_rows_raises_in_strict_mode(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nAlice,alice@example.com\nBob\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Row 3"):
        copy_csv_rows(input_csv, output_csv, strict=True)


def test_copy_csv_rows_populates_youtube_fields(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email,Company URL\nAlice,alice@example.com,https://example.com\n",
        encoding="utf-8",
    )

    def fake_lookup(queries: list[str]) -> YouTubeChannelData:
        assert any("Alice" in query for query in queries)
        return YouTubeChannelData(
            handle="@alice",
            url="https://www.youtube.com/@alice",
            subscriber_count=1200,
            publishing_cadence="Weekly or more",
            channel_age="2 years",
            source_url="https://www.youtube.com/@alice",
        )

    report = copy_csv_rows(input_csv, output_csv, youtube_lookup=fake_lookup)

    assert report.valid_rows == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Company URL,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Alice,alice@example.com,https://example.com,@alice,"
        "https://www.youtube.com/@alice,1200,Weekly or more,2 years,,,,\n"
    )


def test_copy_csv_rows_uses_youtube_hint_when_lookup_fails(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Company URL\nMock Client,https://www.youtube.com/@MrBeast\n",
        encoding="utf-8",
    )

    def fake_lookup(_: list[str]) -> None:
        return None

    report = copy_csv_rows(input_csv, output_csv, youtube_lookup=fake_lookup)

    assert report.valid_rows == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Company URL,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Mock Client,https://www.youtube.com/@MrBeast,@MrBeast,"
        "https://www.youtube.com/@MrBeast,,,,,,,\n"
    )


def test_copy_csv_rows_resolves_handle_without_hint(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nMrBeast,mrbeast@example.com\n",
        encoding="utf-8",
    )

    def fake_lookup(queries: list[str]) -> YouTubeChannelData:
        assert any("MrBeast" in query for query in queries)
        return YouTubeChannelData(
            handle="@MrBeast",
            url="https://www.youtube.com/@MrBeast",
            subscriber_count=100_000_000,
            publishing_cadence="Weekly or more",
            channel_age="10 years",
            source_url="https://www.youtube.com/@MrBeast",
        )

    report = copy_csv_rows(input_csv, output_csv, youtube_lookup=fake_lookup)

    assert report.valid_rows == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "MrBeast,mrbeast@example.com,@MrBeast,https://www.youtube.com/@MrBeast,"
        "100000000,Weekly or more,10 years,,,,\n"
    )


def test_copy_csv_rows_populates_instagram_fields(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nMock Client,client@example.com\n",
        encoding="utf-8",
    )

    def fake_instagram_lookup(_: str) -> InstagramProfileData:
        return InstagramProfileData(
            handle="mockclient",
            followers=1234,
            publishing_cadence="Weekly or more",
            account_age="2 years",
            source_url="https://www.instagram.com/mockclient/",
        )

    report = copy_csv_rows(
        input_csv,
        output_csv,
        instagram_lookup=fake_instagram_lookup,
    )

    assert report.valid_rows == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Mock Client,client@example.com,,,,,,mockclient,1234,Weekly or more,2 years\n"
    )


def test_copy_csv_rows_respects_row_limit(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text(
        "Name,Email\nAlice,alice@example.com\nBob,bob@example.com\n",
        encoding="utf-8",
    )

    report = copy_csv_rows(input_csv, output_csv, row_limit=1)

    assert report.total_rows == 1
    assert report.valid_rows == 1
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Alice,alice@example.com,,,,,,,,,\n"
    )
