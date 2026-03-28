from __future__ import annotations

from pathlib import Path


def test_skill_copies_csv_end_to_end(tmp_path: Path, monkeypatch) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    input_csv.write_text("Name,Email\nAlice,alice@example.com\n", encoding="utf-8")

    from src.main import run  # pylint: disable=import-outside-toplevel

    # Avoid leaking repo-level .env into the global test process environment.
    monkeypatch.chdir(tmp_path)

    exit_code = run(
        [
            "--input",
            str(input_csv),
            "--output",
            str(output_csv),
        ]
    )

    assert exit_code == 0
    assert output_csv.exists()
    assert output_csv.read_text(encoding="utf-8") == (
        "Name,Email,Youtube handle,Youtube URL,Youtube Subs count,"
        "Youtube Upload count,Youtube Publishing cadence,Youtube Channel Age,Instagram handle,"
        "Instagram followers,Instagram publishing cadence,Instagram Account Age\n"
        "Alice,alice@example.com,,,,,,,,,,\n"
    )
