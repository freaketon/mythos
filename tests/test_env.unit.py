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


def test_load_dotenv_discovers_sibling_env_for_new_feature_worktree(tmp_path: Path, monkeypatch) -> None:
    """
    Repo commonly uses sibling worktrees:
    - contact-enrichment/.env (has secrets)
    - contact-enrichment-new-feature/ (branch)

    When the new-feature worktree lacks its own .env, load_dotenv() should still
    pick up the sibling .env by default.
    """

    old_root = tmp_path / "contact-enrichment"
    new_root = tmp_path / "contact-enrichment-new-feature"
    old_root.mkdir()
    new_root.mkdir()
    (old_root / ".env").write_text("OPENAI_API_KEY=test\nFOO=bar\n", encoding="utf-8")

    monkeypatch.chdir(new_root)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FOO", raising=False)

    load_dotenv()
    assert os.environ["OPENAI_API_KEY"] == "test"
    assert os.environ["FOO"] == "bar"
