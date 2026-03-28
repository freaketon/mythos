from __future__ import annotations

import csv
from pathlib import Path

from src.adapters.youtube import YouTubeChannelData
from src.csv_pipeline import copy_csv_rows


def test_duplicate_guard_ignores_free_email_domain(tmp_path: Path) -> None:
    input_csv = tmp_path / "in.csv"
    output_csv = tmp_path / "out.csv"
    low_csv = tmp_path / "low.csv"

    headers = ["Name", "Email", "Company URL", "Company"]
    rows = [
        ["Alice A", "alice@gmail.com", "https://a.example", "A Co"],
        ["Bob B", "bob@gmail.com", "https://b.example", "B Co"],
    ]

    input_csv.write_text(
        ",".join(headers) + "\n" + "\n".join(",".join(r) for r in rows) + "\n",
        encoding="utf-8",
    )

    def fake_youtube_lookup(_queries: list[str]) -> YouTubeChannelData:
        return YouTubeChannelData(
            handle="@shared",
            url="https://www.youtube.com/@shared",
            confidence=90,
            source="scrapetube",
            accepted=True,
        )

    report = copy_csv_rows(
        input_csv,
        output_csv,
        youtube_lookup=fake_youtube_lookup,
        instagram_lookup=None,
        low_confidence_report_path=low_csv,
        checkpoint_every=0,
        strict=True,
    )

    # First row can hydrate; second should be downgraded due to disjoint company domains.
    assert report.hydrated_youtube_rows == 1
    assert len(report.low_confidence_rows) == 1
    assert report.low_confidence_rows[0].row_number == 3
    assert report.low_confidence_rows[0].source == "duplicate-guard"

    with output_csv.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        out_rows = list(r)

    assert out_rows[0]["Youtube URL"] == "https://www.youtube.com/@shared"
    assert out_rows[1]["Youtube URL"] == ""
    assert out_rows[1]["Youtube handle"] == ""

