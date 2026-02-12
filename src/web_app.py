from __future__ import annotations

import csv
import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

CHECKPOINT_PATTERN = re.compile(
    r"Checkpoint:\s+processed=(?P<processed>\d+)/(?P<total>\d+)\s+remaining=(?P<remaining>\d+)\s+valid=(?P<valid>\d+)\s+invalid=(?P<invalid>\d+)\s+youtube=(?P<youtube>\d+)\s+instagram=(?P<instagram>\d+)\s+low_conf=(?P<low_conf>\d+)"
)

DEFAULT_INPUT = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.csv"
DEFAULT_OUTPUT = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.hydrated.full.csv"
DEFAULT_LOW_CONF = "MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.low-confidence.full.csv"
RUN_LOG_OUT = "run.full.out.log"
RUN_LOG_ERR = "run.full.err.log"
RUN_EVENTS = "run.events.jsonl"
RUN_STATE = "run.state.json"


class RunStartRequest(BaseModel):
    input_path: str = DEFAULT_INPUT
    output_path: str = DEFAULT_OUTPUT
    low_confidence_path: str = DEFAULT_LOW_CONF
    youtube: bool = True
    instagram: bool = True
    checkpoint_every: int = Field(default=10, ge=1)
    strict: bool = False
    limit: int | None = Field(default=None, ge=1)
    events_path: str = RUN_EVENTS


@dataclass
class RunPaths:
    base_dir: Path

    @property
    def out_log(self) -> Path:
        return self.base_dir / RUN_LOG_OUT

    @property
    def err_log(self) -> Path:
        return self.base_dir / RUN_LOG_ERR

    @property
    def state_file(self) -> Path:
        return self.base_dir / RUN_STATE

    @property
    def events_file(self) -> Path:
        return self.base_dir / RUN_EVENTS


def _count_rows(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return max(0, sum(1 for _ in file) - 1)


def _read_checkpoint(err_log: Path) -> dict[str, int]:
    if not err_log.exists():
        return {
            "processed": 0,
            "total": 0,
            "remaining": 0,
            "valid": 0,
            "invalid": 0,
            "hydrated_youtube": 0,
            "hydrated_instagram": 0,
            "low_confidence": 0,
        }
    lines = err_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        match = CHECKPOINT_PATTERN.search(line)
        if not match:
            continue
        return {
            "processed": int(match.group("processed")),
            "total": int(match.group("total")),
            "remaining": int(match.group("remaining")),
            "valid": int(match.group("valid")),
            "invalid": int(match.group("invalid")),
            "hydrated_youtube": int(match.group("youtube")),
            "hydrated_instagram": int(match.group("instagram")),
            "low_confidence": int(match.group("low_conf")),
        }
    return {
        "processed": 0,
        "total": 0,
        "remaining": 0,
        "valid": 0,
        "invalid": 0,
        "hydrated_youtube": 0,
        "hydrated_instagram": 0,
        "low_confidence": 0,
    }


def _read_state(paths: RunPaths) -> dict[str, Any]:
    if not paths.state_file.exists():
        return {}
    try:
        return json.loads(paths.state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_state(paths: RunPaths, payload: dict[str, Any]) -> None:
    paths.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _state_path(base: Path, state: dict[str, Any], key: str, fallback_name: str) -> Path:
    raw = state.get(key)
    if isinstance(raw, str) and raw:
        return base / raw
    return base / fallback_name


def _build_status(paths: RunPaths) -> dict[str, Any]:
    state = _read_state(paths)
    pid = state.get("pid")
    running = _is_pid_alive(pid if isinstance(pid, int) else None)
    run_state = "running" if running else ("completed" if state else "idle")
    checkpoint = {
        "processed": 0,
        "total": 0,
        "remaining": 0,
        "valid": 0,
        "invalid": 0,
        "hydrated_youtube": 0,
        "hydrated_instagram": 0,
        "low_confidence": 0,
    }
    if state:
        err_log_path = _state_path(paths.base_dir, state, "err_log_path", RUN_LOG_ERR)
        checkpoint = _read_checkpoint(err_log_path)
    return {
        "state": run_state,
        "pid": pid if running else None,
        "started_at": state.get("started_at"),
        **checkpoint,
    }


def _tail_lines(path: Path, limit: int = 200) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-limit:]


def _filter_log_lines(lines: list[str]) -> list[str]:
    keywords = ("ERROR", "HIT", "NO_HIT", "Checkpoint:")
    filtered = [line for line in lines if any(token in line for token in keywords)]
    return filtered


def _read_events(path: Path, offset: int = 0, limit: int = 200) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    events: list[dict[str, Any]] = []
    next_offset = 0
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        for index, line in enumerate(file):
            if index < offset:
                continue
            if len(events) >= limit:
                break
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            next_offset = index + 1
    if next_offset == 0 and offset > 0:
        next_offset = offset
    return events, next_offset


def _input_preview(path: Path, limit: int = 30) -> dict[str, Any]:
    if not path.exists():
        return {"headers": [], "rows": []}
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        for _, row in zip(range(limit), reader):
            rows.append(row)
    return {"headers": headers, "rows": rows}


def _output_preview(path: Path, limit: int = 30) -> dict[str, Any]:
    if not path.exists():
        return {"headers": [], "rows": []}
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        rows = list(reader)
    if not rows:
        return {"headers": headers, "rows": []}
    return {"headers": headers, "rows": rows[-limit:]}


def create_app(*, base_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Contact Enrichment Control")
    base = base_dir or Path.cwd()
    paths = RunPaths(base)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Contact Enrichment Control</title>
    <style>
      :root {
        --bg: #f3f6fb;
        --panel: #ffffff;
        --panel-soft: #f8faff;
        --text: #1b2430;
        --muted: #5b6778;
        --line: #d9e2ef;
        --line-strong: #c4d2e5;
        --accent: #2e6fd6;
        --accent-soft: #e8f0ff;
        --shadow: 0 8px 24px rgba(27, 36, 48, 0.08);
      }
      body {
        font-family: "Manrope", "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
        margin: 20px;
        background:
          radial-gradient(circle at top right, #e8f0ff 0%, transparent 40%),
          radial-gradient(circle at top left, #eef4ff 0%, transparent 35%),
          var(--bg);
        color: var(--text);
        line-height: 1.4;
      }
      h2 { margin: 0 0 14px 0; font-weight: 700; letter-spacing: 0.1px; }
      h3 { margin: 18px 0 10px 0; font-weight: 650; color: #273345; }
      .grid { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 10px; }
      .card {
        background: linear-gradient(180deg, #fff 0%, var(--panel-soft) 100%);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 10px;
        box-shadow: var(--shadow);
      }
      .status {
        margin-top: 10px;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 10px;
        background: linear-gradient(180deg, #fff 0%, var(--panel-soft) 100%);
        box-shadow: var(--shadow);
      }
      .activity-wrap { display: flex; align-items: center; gap: 10px; }
      .spinner {
        width: 14px;
        height: 14px;
        border: 2px solid #c9d7ea;
        border-top: 2px solid var(--accent);
        border-radius: 50%;
        display: inline-block;
      }
      .spinner.running { animation: spin 0.8s linear infinite; }
      @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      .tables { display: grid; grid-template-columns: 1fr; gap: 12px; }
      table {
        border-collapse: separate;
        border-spacing: 0;
        width: 100%;
        font-size: 12px;
        background: #fff;
      }
      th, td {
        border-right: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
        padding: 7px 8px;
        text-align: left;
      }
      th {
        background: #f4f8ff;
        color: #334258;
        font-weight: 650;
        position: sticky;
        top: 0;
        z-index: 1;
      }
      tr td:first-child, tr th:first-child { border-left: 1px solid var(--line); }
      tr:first-child th { border-top: 1px solid var(--line); }
      tr:hover td { background: #f8fbff; }
      .scroll { max-height: 280px; overflow: auto; }
      .tabs { display: flex; gap: 8px; margin-bottom: 8px; }
      .tab-btn {
        border: 1px solid var(--line-strong);
        background: #fff;
        border-radius: 999px;
        padding: 6px 12px;
        cursor: pointer;
        color: #304055;
        transition: all 120ms ease;
      }
      .tab-btn:hover { background: #f8fbff; }
      .tab-btn.active {
        background: var(--accent-soft);
        color: #134ea9;
        border-color: #b9cdf0;
        font-weight: 650;
      }
      .tab-pane { display: none; }
      .tab-pane.active { display: block; }
      .resizable {
        resize: both;
        overflow: auto;
        min-height: 220px;
        min-width: 500px;
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 6px;
        box-shadow: var(--shadow);
      }
      tr.row-active td { background: #fff5cf; }
      button {
        margin-right: 8px;
        border: 1px solid #c2d1e7;
        background: #fff;
        color: #24354c;
        border-radius: 10px;
        padding: 7px 12px;
        cursor: pointer;
        transition: all 120ms ease;
      }
      button:hover { background: #f2f7ff; border-color: #afc4e4; }
      progress {
        width: 100%;
        height: 18px;
        border-radius: 999px;
        overflow: hidden;
      }
      progress::-webkit-progress-bar { background: #e8edf7; border-radius: 999px; }
      progress::-webkit-progress-value {
        background: linear-gradient(90deg, #6aa7ff 0%, #2e6fd6 100%);
        border-radius: 999px;
      }
      #state { color: var(--muted); margin-left: 6px; }
    </style>
  </head>
  <body>
    <h2>Contact Enrichment Control</h2>
    <div>
      <button onclick="startRun()">Start</button>
      <button onclick="stopRun()">Stop</button>
      <span id="state"></span>
    </div>
    <div style="margin-top:10px"><progress id="bar" value="0" max="100"></progress></div>
    <div class="grid" style="margin-top:10px">
      <div class="card"><b>Processed</b><div id="processed">0</div></div>
      <div class="card"><b>Total</b><div id="total">0</div></div>
      <div class="card"><b>Remaining</b><div id="remaining">0</div></div>
      <div class="card"><b>Low Confidence</b><div id="low">0</div></div>
      <div class="card"><b>YouTube Hydrated</b><div id="yt">0</div></div>
      <div class="card"><b>Instagram Hydrated</b><div id="ig">0</div></div>
      <div class="card"><b>Invalid</b><div id="invalid">0</div></div>
      <div class="card"><b>PID</b><div id="pid">-</div></div>
    </div>
    <div class="status">
      <b>Current Activity</b>
      <div class="activity-wrap">
        <span id="activitySpinner" class="spinner"></span>
        <span id="activity">Idle</span>
      </div>
    </div>
    <h3>History (Hit / No Hit)</h3>
    <div class="resizable">
      <div class="scroll"><table id="historyTable"></table></div>
    </div>
    <h3>CSV Visualizer</h3>
    <div class="tabs">
      <button id="tab-original" class="tab-btn active" onclick="setTab('original')">Original CSV</button>
      <button id="tab-hydrated" class="tab-btn" onclick="setTab('hydrated')">Hydrated CSV</button>
    </div>
    <div id="pane-original" class="tab-pane active">
      <div class="resizable"><div class="scroll"><table id="inputTable"></table></div></div>
    </div>
    <div id="pane-hydrated" class="tab-pane">
      <div class="resizable"><div class="scroll"><table id="outputTable"></table></div></div>
    </div>
    <script>
      function renderTable(elId, headers, rows, rowClassFn = null) {
        const el = document.getElementById(elId);
        const head = '<tr>' + headers.map(h => '<th>'+h+'</th>').join('') + '</tr>';
        const body = rows.map(r => {
          const rowClass = rowClassFn ? rowClassFn(r) : '';
          return '<tr class="' + rowClass + '">' + r.map(c => '<td>' + String(c ?? '') + '</td>').join('') + '</tr>';
        }).join('');
        el.innerHTML = head + body;
      }
      function setTab(tab) {
        const originalActive = tab === 'original';
        document.getElementById('tab-original').classList.toggle('active', originalActive);
        document.getElementById('tab-hydrated').classList.toggle('active', !originalActive);
        document.getElementById('pane-original').classList.toggle('active', originalActive);
        document.getElementById('pane-hydrated').classList.toggle('active', !originalActive);
      }
      let eventOffset = 0;
      const historyRows = new Map();
      const outputRows = new Map();
      let activeRowKey = '';
      let currentState = 'idle';
      function outcome(yt, ig) {
        if (yt.startsWith('hit') || ig.startsWith('hit')) return 'hit';
        if (yt === 'low_confidence') return 'low_confidence';
        if (yt.includes('no_') && ig.includes('no_')) return 'no_hit';
        return 'partial';
      }
      function setActivity(text, running) {
        document.getElementById('activity').textContent = text;
        document.getElementById('activitySpinner').classList.toggle('running', Boolean(running));
      }
      async function fetchStatus() {
        const r = await fetch('/run/status'); const s = await r.json();
        document.getElementById('state').textContent = 'State: ' + s.state;
        currentState = s.state;
        document.getElementById('processed').textContent = s.processed;
        document.getElementById('total').textContent = s.total;
        document.getElementById('remaining').textContent = s.remaining;
        document.getElementById('low').textContent = s.low_confidence;
        document.getElementById('yt').textContent = s.hydrated_youtube;
        document.getElementById('ig').textContent = s.hydrated_instagram;
        document.getElementById('invalid').textContent = s.invalid;
        document.getElementById('pid').textContent = s.pid ?? '-';
        const pct = s.total > 0 ? Math.floor((s.processed / s.total) * 100) : 0;
        const bar = document.getElementById('bar'); bar.max = 100; bar.value = pct;
        if (s.state === 'running') {
          document.getElementById('activitySpinner').classList.add('running');
        } else {
          setActivity('Idle', false);
        }
      }
      async function fetchInputPreview() {
        const r = await fetch('/run/input-preview?limit=20'); const p = await r.json();
        const headers = p.headers.length ? p.headers : ['No input'];
        const rows = p.rows.length ? p.rows : [['-']];
        renderTable('inputTable', headers, rows);
      }
      async function preloadOutputPreview() {
        const r = await fetch('/run/output-preview?limit=200'); const p = await r.json();
        if (!p.rows || !p.rows.length) {
          renderOutputTable();
          return;
        }
        const idx = {};
        p.headers.forEach((h, i) => { idx[h] = i; });
        for (const row of p.rows) {
          const rowNumber = row[idx['row_number']] || '';
          const key = String(rowNumber || outputRows.size + 1);
          outputRows.set(key, {
            row_number: rowNumber,
            name: row[idx['Name']] || '',
            youtube_handle: row[idx['Youtube handle']] || '',
            youtube_url: row[idx['Youtube URL']] || '',
            youtube_subs_count: row[idx['Youtube Subs count']] || '',
            youtube_status: (row[idx['Youtube URL']] || row[idx['Youtube handle']]) ? 'hit' : '',
            instagram_handle: row[idx['Instagram handle']] || '',
            instagram_followers: row[idx['Instagram followers']] || '',
            instagram_status: (row[idx['Instagram handle']] || row[idx['Instagram followers']]) ? 'hit' : '',
          });
        }
        renderOutputTable();
      }
      function renderHistoryTable() {
        const rows = Array.from(historyRows.values()).sort((a, b) => Number(a[0]) - Number(b[0])).slice(-500);
        renderTable(
          'historyTable',
          ['row', 'name', 'youtube', 'instagram', 'outcome'],
          rows,
          (r) => String(r[0]) === activeRowKey ? 'row-active' : ''
        );
      }
      function renderOutputTable() {
        const rows = Array.from(outputRows.values())
          .sort((a, b) => Number(a.row_number) - Number(b.row_number))
          .slice(-500)
          .map((v) => [
            v.row_number,
            v.name,
            v.youtube_handle,
            v.youtube_url,
            v.youtube_subs_count,
            v.youtube_status,
            v.instagram_handle,
            v.instagram_followers,
            v.instagram_status,
          ]);
        renderTable(
          'outputTable',
          [
            'row',
            'name',
            'youtube_handle',
            'youtube_url',
            'youtube_subs',
            'youtube_status',
            'instagram_handle',
            'instagram_followers',
            'instagram_status',
          ],
          rows,
          (r) => String(r[0]) === activeRowKey ? 'row-active' : ''
        );
      }
      async function fetchEvents() {
        const r = await fetch('/run/events?offset=' + eventOffset + '&limit=200');
        const p = await r.json();
        eventOffset = p.next_offset;
        for (const e of p.events) {
          const item = e.item || e.name || ('row ' + (e.row_number ?? '?'));
          const method = e.method || 'default';
          const rowKey = String(e.row_number ?? '');
          const existing = outputRows.get(rowKey) || {
            row_number: e.row_number ?? '',
            name: e.name || '',
            youtube_handle: '',
            youtube_url: '',
            youtube_subs_count: '',
            youtube_status: '',
            instagram_handle: '',
            instagram_followers: '',
            instagram_status: '',
          };
          if (e.name) {
            existing.name = e.name;
          }
          if (e.type === 'row_start') {
            activeRowKey = rowKey;
            setActivity(item + ': Preparing enrichment through method ' + method, true);
          }
          if (e.type === 'youtube_searching') {
            activeRowKey = rowKey;
            setActivity(item + ': Fetching youtube through method ' + method, true);
          }
          if (e.type === 'instagram_searching') {
            activeRowKey = rowKey;
            setActivity(item + ': Fetching instagram through method ' + method, true);
          }
          if (e.type === 'youtube_result') {
            existing.youtube_handle = e.youtube_handle || existing.youtube_handle;
            existing.youtube_url = e.youtube_url || existing.youtube_url;
            existing.youtube_subs_count = e.youtube_subs_count || existing.youtube_subs_count;
            existing.youtube_status = e.status || existing.youtube_status;
            outputRows.set(rowKey, existing);
          }
          if (e.type === 'instagram_result') {
            existing.instagram_handle = e.instagram_handle || existing.instagram_handle;
            existing.instagram_followers = e.instagram_followers || existing.instagram_followers;
            existing.instagram_status = e.status || existing.instagram_status;
            outputRows.set(rowKey, existing);
          }
          if (e.type === 'row_complete') {
            const yt = e.youtube || 'disabled';
            const ig = e.instagram || 'disabled';
            historyRows.set(String(e.row_number), [e.row_number, e.name || '', yt, ig, outcome(yt, ig)]);
            existing.youtube_handle = e.youtube_handle || existing.youtube_handle;
            existing.youtube_url = e.youtube_url || existing.youtube_url;
            existing.youtube_subs_count = e.youtube_subs_count || existing.youtube_subs_count;
            existing.instagram_handle = e.instagram_handle || existing.instagram_handle;
            existing.instagram_followers = e.instagram_followers || existing.instagram_followers;
            existing.youtube_status = yt;
            existing.instagram_status = ig;
            outputRows.set(rowKey, existing);
            setActivity(item + ': Completed via method ' + method + ' (YT ' + yt + ', IG ' + ig + ')', currentState === 'running');
            if (activeRowKey === rowKey) {
              activeRowKey = '';
            }
          }
          if (e.type === 'invalid_row') {
            historyRows.set(String(e.row_number), [e.row_number, '', 'invalid', 'invalid', 'invalid']);
            existing.youtube_status = 'invalid';
            existing.instagram_status = 'invalid';
            outputRows.set(rowKey, existing);
            setActivity('Row ' + e.row_number + ': Invalid input row', currentState === 'running');
            if (activeRowKey === rowKey) {
              activeRowKey = '';
            }
          }
        }
        renderHistoryTable();
        renderOutputTable();
      }
      async function startRun() {
        const response = await fetch('/run/start', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          const detail = payload.detail || ('start failed with status ' + response.status);
          setActivity('Start failed: ' + detail, false);
          return;
        }
        setActivity('Run starting...', true);
      }
      async function stopRun() { await fetch('/run/stop', { method: 'POST' }); }
      async function tick() { await fetchStatus(); await fetchEvents(); }
      fetchInputPreview(); preloadOutputPreview(); tick(); setInterval(tick, 3000);
    </script>
  </body>
</html>
"""

    @app.get("/run/status")
    def run_status() -> dict[str, Any]:
        return _build_status(paths)

    @app.post("/run/start")
    def run_start(payload: RunStartRequest) -> dict[str, Any]:
        state = _read_state(paths)
        if _is_pid_alive(state.get("pid") if isinstance(state.get("pid"), int) else None):
            raise HTTPException(status_code=409, detail="A run is already active.")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_log_path = base / f"run.{run_id}.out.log"
        err_log_path = base / f"run.{run_id}.err.log"
        events_path = base / f"run.{run_id}.events.jsonl"
        output_path = base / payload.output_path
        low_confidence_path = base / payload.low_confidence_path
        for artifact in (output_path, low_confidence_path):
            if artifact.exists():
                try:
                    artifact.unlink()
                except OSError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail=f"File in use: {artifact.name}. Stop previous run first.",
                    ) from exc

        cmd = [
            sys.executable,
            "-u",
            "-m",
            "src.main",
            "--input",
            payload.input_path,
            "--output",
            payload.output_path,
            "--checkpoint-every",
            str(payload.checkpoint_every),
            "--low-confidence-report",
            payload.low_confidence_path,
            "--events-file",
            events_path.name,
        ]
        if payload.youtube:
            cmd.append("--youtube")
        if payload.instagram:
            cmd.append("--instagram")
        if payload.strict:
            cmd.append("--strict")
        if payload.limit is not None:
            cmd.extend(["--limit", str(payload.limit)])

        stdout = out_log_path.open("w", encoding="utf-8")
        stderr = err_log_path.open("w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(base),
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            # Avoid parent-held file handles causing lock/teardown side effects on Windows.
            stdout.close()
            stderr.close()

        _write_state(
            paths,
            {
                "pid": proc.pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "command": cmd,
                "out_log_path": out_log_path.name,
                "err_log_path": err_log_path.name,
                "events_path": events_path.name,
                "output_path": output_path.name,
                "low_confidence_path": low_confidence_path.name,
                "input_path": payload.input_path,
            },
        )
        return {"state": "running", "pid": proc.pid}

    @app.post("/run/stop")
    def run_stop() -> dict[str, Any]:
        state = _read_state(paths)
        pid = state.get("pid") if isinstance(state.get("pid"), int) else None
        if not _is_pid_alive(pid):
            return {"state": "idle", "stopped": False}
        os.kill(pid, signal.SIGTERM)
        return {"state": "stopping", "stopped": True}

    @app.get("/run/logs")
    def run_logs(tail: int = 200) -> dict[str, Any]:
        state = _read_state(paths)
        err_log_path = _state_path(base, state, "err_log_path", RUN_LOG_ERR)
        lines = _tail_lines(err_log_path, limit=max(1, min(tail, 2000)))
        lines = _filter_log_lines(lines)
        return {"lines": lines}

    @app.get("/run/events")
    def run_events(offset: int = 0, limit: int = 200) -> dict[str, Any]:
        state = _read_state(paths)
        events_path = _state_path(base, state, "events_path", RUN_EVENTS)
        events, next_offset = _read_events(events_path, offset=max(0, offset), limit=max(1, min(limit, 500)))
        return {"events": events, "next_offset": next_offset}

    @app.get("/run/input-preview")
    def run_input_preview(limit: int = 30) -> dict[str, Any]:
        state = _read_state(paths)
        input_path = _state_path(base, state, "input_path", DEFAULT_INPUT)
        return _input_preview(input_path, limit=max(1, min(limit, 200)))

    @app.get("/run/output-preview")
    def run_output_preview(limit: int = 30) -> dict[str, Any]:
        state = _read_state(paths)
        output_path = _state_path(base, state, "output_path", DEFAULT_OUTPUT)
        return _output_preview(output_path, limit=max(1, min(limit, 200)))

    @app.get("/run/files")
    def run_files() -> dict[str, Any]:
        state = _read_state(paths)
        output_path = _state_path(base, state, "output_path", DEFAULT_OUTPUT)
        low_conf_path = _state_path(base, state, "low_confidence_path", DEFAULT_LOW_CONF)
        return {
            "output": {
                "path": str(output_path),
                "exists": output_path.exists(),
                "rows": _count_rows(output_path),
            },
            "low_confidence": {
                "path": str(low_conf_path),
                "exists": low_conf_path.exists(),
                "rows": _count_rows(low_conf_path),
            },
        }

    return app
