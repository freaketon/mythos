from __future__ import annotations

import importlib
import sys


def test_src_conftest_inserts_project_root_when_missing(monkeypatch) -> None:
    import src.conftest as c

    root = str(c.PROJECT_ROOT)
    # Ensure the branch is taken.
    while root in sys.path:
        sys.path.remove(root)

    importlib.reload(c)
    assert root in sys.path

