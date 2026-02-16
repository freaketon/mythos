from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

import src.web_app as web_app
from src.web_app import create_app


def test_status_reports_idle_when_no_run(tmp_path: Path) -> None:
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "idle"
    assert payload["processed"] == 0
    assert payload["total"] == 0
    assert payload["remaining"] == 0


def test_status_parses_checkpoint_progress(tmp_path: Path) -> None:
    err_log = tmp_path / "run.20260212-120000.err.log"
    err_log.write_text(
        "INFO: Checkpoint: processed=120/3006 remaining=2886 valid=120 invalid=0 youtube=84 instagram=31 low_conf=22\n",
        encoding="utf-8",
    )
    state = tmp_path / "run.state.json"
    state.write_text(json.dumps({"err_log_path": err_log.name}), encoding="utf-8")
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["processed"] == 120
    assert payload["total"] == 3006
    assert payload["remaining"] == 2886
    assert payload["hydrated_youtube"] == 84
    assert payload["hydrated_instagram"] == 31
    assert payload["low_confidence"] == 22


def test_status_ignores_stale_default_logs_without_state(tmp_path: Path) -> None:
    err_log = tmp_path / "run.full.err.log"
    err_log.write_text(
        "INFO: Checkpoint: processed=999/1000 remaining=1 valid=999 invalid=0 youtube=500 instagram=400 low_conf=10\n",
        encoding="utf-8",
    )
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "idle"
    assert payload["processed"] == 0
    assert payload["total"] == 0


def test_files_endpoint_reports_row_counts(tmp_path: Path) -> None:
    output = tmp_path / "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.hydrated.full.csv"
    low_conf = tmp_path / "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.low-confidence.full.csv"
    output.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    low_conf.write_text("x,y\n9,8\n", encoding="utf-8")

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/files")
    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["rows"] == 2
    assert payload["low_confidence"]["rows"] == 1


def test_input_preview_returns_headers_and_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "sample.csv"
    input_csv.write_text("A,B\n1,2\n3,4\n", encoding="utf-8")
    state = tmp_path / "run.state.json"
    state.write_text(
        json.dumps(
            {
                "pid": 123,
                "input_path": "sample.csv",
                "command": ["python", "-m", "src.main", "--input", "sample.csv"],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/input-preview?limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["headers"] == ["A", "B"]
    assert payload["rows"] == [["1", "2"]]

def test_qualify_prompts_roundtrip(tmp_path: Path) -> None:
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    get1 = client.get("/qualify/prompts")
    assert get1.status_code == 200
    assert get1.json() == {"icp_prompt": "", "product_prompt": ""}

    set_resp = client.post(
        "/qualify/prompts",
        json={"icp_prompt": "ICP here", "product_prompt": "Product here"},
    )
    assert set_resp.status_code == 200

    get2 = client.get("/qualify/prompts")
    assert get2.status_code == 200
    assert get2.json()["icp_prompt"] == "ICP here"
    assert get2.json()["product_prompt"] == "Product here"

    assert (tmp_path / "qualify.icp.txt").read_text(encoding="utf-8") == "ICP here"
    assert (tmp_path / "qualify.product.txt").read_text(encoding="utf-8") == "Product here"


def test_qualify_start_uses_current_python_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Save prompts (required).
    (tmp_path / "qualify.icp.txt").write_text("ICP", encoding="utf-8")
    (tmp_path / "qualify.product.txt").write_text("PRODUCT", encoding="utf-8")
    input_csv = tmp_path / "hydrated.csv"
    input_csv.write_text("Name,Youtube URL\nAlice,https://www.youtube.com/@alice\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeProc:
        pid = 12345

    def fake_popen(cmd, cwd, stdout, stderr, start_new_session, close_fds):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["start_new_session"] = start_new_session
        captured["close_fds"] = close_fds
        return FakeProc()

    monkeypatch.setattr("src.web_app.subprocess.Popen", fake_popen)

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/qualify/start",
        json={
            "input_path": "hydrated.csv",
            "output_path": "qualified.csv",
            "model": "gpt-5-mini",
            "sort": True,
            "limit": 1,
        },
    )
    assert response.status_code == 200
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-u", "-m", "src.qualify"]
    assert "--icp" in cmd and "@qualify.icp.txt" in cmd
    assert "--product" in cmd and "@qualify.product.txt" in cmd
    assert "--sort" in cmd
    assert captured["cwd"] == str(tmp_path)


def test_input_preview_reads_xlsx(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")

    input_xlsx = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["A", "B"])
    ws.append([1, 2])
    ws.append([3, 4])
    wb.save(input_xlsx)
    wb.close()

    state = tmp_path / "run.state.json"
    state.write_text(
        json.dumps(
            {
                "pid": 123,
                "input_path": "sample.xlsx",
                "command": ["python", "-m", "src.main", "--input", "sample.xlsx"],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/input-preview?limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["headers"] == ["A", "B"]
    assert payload["rows"] == [["1", "2"]]


def test_upload_input_accepts_xlsx_and_updates_state(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["A", "B"])
    ws.append([1, 2])
    ws.append([3, 4])
    from io import BytesIO

    buf = BytesIO()
    wb.save(buf)
    wb.close()
    body = buf.getvalue()

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    resp = client.post(
        "/run/upload-input",
        content=body,
        headers={
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "x-filename": "contacts.xlsx",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["saved_as"].endswith(".xlsx")

    # State is updated for preview + run defaults.
    state = json.loads((tmp_path / "run.state.json").read_text(encoding="utf-8"))
    assert state["input_path"] == payload["saved_as"]
    assert state["planned_total"] == 2

    preview = client.get("/run/input-preview?limit=10")
    assert preview.status_code == 200
    assert preview.json()["headers"] == ["A", "B"]


def test_events_endpoint_streams_from_offset(tmp_path: Path) -> None:
    events = tmp_path / "run.events.jsonl"
    events.write_text(
        '{"row_number":2,"name":"Alice","youtube":"hit","instagram":"no_hit"}\n'
        '{"row_number":3,"name":"Bob","youtube":"no_hit","instagram":"hit"}\n',
        encoding="utf-8",
    )
    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/run/events?offset=1&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["next_offset"] == 2
    assert payload["events"] == [
        {"row_number": 3, "name": "Bob", "youtube": "no_hit", "instagram": "hit"}
    ]


def test_output_preview_reads_hydrated_csv(tmp_path: Path) -> None:
    output_csv = tmp_path / "hydrated.csv"
    output_csv.write_text("X,Y\na,b\nc,d\n", encoding="utf-8")
    state = tmp_path / "run.state.json"
    state.write_text(json.dumps({"output_path": "hydrated.csv"}), encoding="utf-8")

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)
    response = client.get("/run/output-preview?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["headers"] == ["X", "Y"]
    assert payload["rows"] == [["c", "d"]]


def test_low_confidence_preview_pages_rows(tmp_path: Path) -> None:
    low_conf = tmp_path / "low.csv"
    low_conf.write_text(
        "row_number,queries,candidate_url,candidate_handle,confidence,source\n"
        "2,a | b,https://example.com/@a,a,40,ddg\n"
        "3,c,https://example.com/@c,c,10,serper\n",
        encoding="utf-8",
    )
    state = tmp_path / "run.state.json"
    state.write_text(json.dumps({"low_confidence_path": "low.csv"}), encoding="utf-8")

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    page1 = client.get("/run/low-confidence-preview?offset=0&limit=1")
    assert page1.status_code == 200
    payload1 = page1.json()
    assert payload1["headers"][0] == "row_number"
    assert payload1["rows"] == [["2", "a | b", "https://example.com/@a", "a", "40", "ddg"]]
    assert payload1["next_offset"] == 1

    page2 = client.get(f"/run/low-confidence-preview?offset={payload1['next_offset']}&limit=10")
    assert page2.status_code == 200
    payload2 = page2.json()
    assert payload2["rows"] == [["3", "c", "https://example.com/@c", "c", "10", "serper"]]
    assert payload2["next_offset"] == 2


def test_run_start_returns_409_when_artifact_unlink_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.hydrated.full.csv"
    output.write_text("a,b\n", encoding="utf-8")
    low_conf = tmp_path / "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.low-confidence.full.csv"
    low_conf.write_text("a,b\n", encoding="utf-8")

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("sharing violation")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)
    response = client.post("/run/start", json={})

    assert response.status_code == 409
    assert "File in use" in response.json()["detail"]


def test_run_start_uses_current_python_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_csv = tmp_path / "input.csv"
    input_csv.write_text("Name,Email\nAlice,alice@example.com\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeProc:
        pid = 99999

    def fake_popen(cmd, cwd, stdout, stderr, start_new_session, close_fds):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["start_new_session"] = start_new_session
        captured["close_fds"] = close_fds
        return FakeProc()

    monkeypatch.setattr("src.web_app.subprocess.Popen", fake_popen)

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/run/start",
        json={
            "input_path": "input.csv",
            "output_path": "out.csv",
            "low_confidence_path": "low.csv",
            "checkpoint_every": 1,
            "limit": 1,
            "llm_rerank": True,
            "llm_model": "gpt-4o-mini",
        },
    )

    assert response.status_code == 200
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-u", "-m", "src.main"]
    assert "--llm-rerank" in cmd
    assert captured["start_new_session"] is True
    assert captured["close_fds"] is True


def test_run_start_keeps_web_endpoints_responsive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_csv = tmp_path / "input.csv"
    input_csv.write_text("Name,Email\nAlice,alice@example.com\n", encoding="utf-8")

    class FakeProc:
        pid = 54321

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        return FakeProc()

    monkeypatch.setattr("src.web_app.subprocess.Popen", fake_popen)
    monkeypatch.setattr("src.web_app._is_pid_alive", lambda pid: bool(pid))

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    start_response = client.post(
        "/run/start",
        json={
            "input_path": "input.csv",
            "output_path": "out.csv",
            "low_confidence_path": "low.csv",
            "youtube": False,
            "instagram": False,
            "checkpoint_every": 1,
            "limit": 1,
        },
    )
    assert start_response.status_code == 200

    status_response = client.get("/run/status")
    assert status_response.status_code == 200
    state = status_response.json()["state"]
    assert state == "running"

    # Regression guard: app process remains responsive after starting a run.
    preview_response = client.get("/run/input-preview?limit=5")
    assert preview_response.status_code == 200


def test_run_stop_marks_state_stopping_and_signals_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "run.state.json"
    state_file.write_text(
        json.dumps(
            {
                "pid": 42424,
                "started_at": "2026-02-12T00:00:00+00:00",
                "command": ["python", "-m", "src.main"],
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, int] = {}

    def fake_killpg(pid: int, sig: int) -> None:
        captured["pid"] = pid
        captured["sig"] = sig

    monkeypatch.setattr("src.web_app._is_pid_alive", lambda pid: bool(pid))
    monkeypatch.setattr("src.web_app.os.killpg", fake_killpg, raising=False)

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    stop_response = client.post("/run/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["state"] == "stopping"
    assert captured["pid"] == 42424

    status_response = client.get("/run/status")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "stopping"

    persisted_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "stop_requested_at" in persisted_state


def test_run_stop_returns_idle_when_process_is_not_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "run.state.json"
    state_file.write_text(json.dumps({"pid": 51515}), encoding="utf-8")
    monkeypatch.setattr("src.web_app._is_pid_alive", lambda pid: False)

    app = create_app(base_dir=tmp_path)
    client = TestClient(app)

    response = client.post("/run/stop")
    assert response.status_code == 200
    assert response.json() == {"state": "idle", "stopped": False}


def test_is_pid_alive_treats_zombie_as_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_app.os, "kill", lambda *_args, **_kwargs: None)

    class FakeCompletedProcess:
        returncode = 0
        stdout = "Z\n"

    monkeypatch.setattr(web_app.subprocess, "run", lambda *_args, **_kwargs: FakeCompletedProcess())

    assert web_app._is_pid_alive(99999) is False
