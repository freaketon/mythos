from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """
    Minimal .env loader to keep local runs ergonomic without adding dependencies.

    - Ignores missing files.
    - Does not override variables already present in the process environment.
    - Supports simple KEY=VALUE lines (no export keyword, no quoted escaping).
    """

    env_path = Path(path)
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip()

