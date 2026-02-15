from __future__ import annotations

import os
from pathlib import Path

from src.env import load_dotenv


def test_load_dotenv_ignores_missing_file(tmp_path: Path) -> None:
    load_dotenv(tmp_path / "missing.env")
    # No exception; no side effects.


def test_load_dotenv_sets_vars_without_overriding(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "EMPTY=",
                "FOO=bar",
                "SPACED = value ",
                "BADLINE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.setenv("KEEP", "original")
    monkeypatch.setenv("SPACED", "dont_override")

    load_dotenv(env_file)

    assert os.environ["FOO"] == "bar"
    assert os.environ["KEEP"] == "original"
    assert os.environ["SPACED"] == "dont_override"

