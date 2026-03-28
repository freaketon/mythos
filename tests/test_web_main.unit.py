from __future__ import annotations

import runpy
import sys

import src.web_main as web_main


def test_web_main_uses_env_host_port(monkeypatch) -> None:
    called = {}

    def fake_load_dotenv() -> None:
        called["dotenv"] = True

    def fake_run(app, *, factory, host, port):  # type: ignore[no-untyped-def]
        called["app"] = app
        called["factory"] = factory
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(web_main, "load_dotenv", fake_load_dotenv)
    monkeypatch.setattr(web_main.uvicorn, "run", fake_run)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8123")

    web_main.main()

    assert called["dotenv"] is True
    assert called["app"] == "src.web_app:create_app"
    assert called["factory"] is True
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 8123


def test_web_main_defaults(monkeypatch) -> None:
    called = {}

    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    monkeypatch.setattr(web_main, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        web_main.uvicorn,
        "run",
        lambda app, *, factory, host, port: called.update(
            {"app": app, "factory": factory, "host": host, "port": port}
        ),
    )

    web_main.main()
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8000


def test_web_main_dunder_main(monkeypatch) -> None:
    called = {}

    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8001")

    # Ensure we execute a fresh module so the __main__ guard is covered without warnings.
    sys.modules.pop("src.web_main", None)

    import src.env as env
    import uvicorn

    monkeypatch.setattr(env, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, *, factory, host, port: called.update(
            {"app": app, "factory": factory, "host": host, "port": port}
        ),
    )

    # Execute the module as a script to cover the guard.
    runpy.run_module("src.web_main", run_name="__main__")
    assert called["port"] == 8001
