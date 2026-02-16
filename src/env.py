from __future__ import annotations

import os
from pathlib import Path


def _discover_dotenv(start_dir: Path) -> Path | None:
    """
    Best-effort .env discovery for local ergonomics.

    Order:
    1) `start_dir/.env`, then parent directories
    2) If this looks like a branch worktree named `*-new-feature`, also try a sibling
       directory without the suffix (common in this repo's worktree setup).
    """

    cur = start_dir
    for _ in range(0, 12):
        candidate = cur / ".env"
        if candidate.exists():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent

    name = start_dir.name
    if name.endswith("-new-feature"):
        sibling = start_dir.parent / name[: -len("-new-feature")]
        candidate = sibling / ".env"
        if candidate.exists():
            return candidate

    return None


def load_dotenv(path: str | Path = ".env") -> None:
    """
    Minimal .env loader to keep local runs ergonomic without adding dependencies.

    - Ignores missing files.
    - Does not override variables already present in the process environment.
    - Supports simple KEY=VALUE lines (no export keyword, no quoted escaping).
    """

    env_path = Path(path)
    if not env_path.exists():
        # If the caller explicitly requested a non-default path, do not guess.
        if str(path) not in (".env", "./.env"):
            return
        discovered = _discover_dotenv(Path.cwd())
        if not discovered:
            return
        env_path = discovered

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip()
