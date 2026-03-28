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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.tabular_input import count_data_rows, preview_rows

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

_EVENT_STATS_CACHE: dict[str, dict[str, object]] = {}


def _safe_relpath(value: str) -> Path:
    """
    Convert a user-supplied path into a safe, base-dir-relative path.
    Browsers cannot provide local absolute paths; this prevents path traversal.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("path is required")
    if raw.startswith(("/", "\\")):
        raise ValueError("absolute paths are not allowed")
    if ".." in raw.replace("\\", "/").split("/"):
        raise ValueError("parent path segments are not allowed")
    return Path(raw)


def _safe_upload_filename(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "input.csv"
    raw = raw.split("/")[-1].split("\\")[-1]
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch in (" ", "-", "_", "."):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    out = "".join(cleaned).strip().replace("  ", " ")
    lower = out.lower()
    if lower.endswith(".xlsx"):
        # Keep as-is.
        pass
    else:
        if not lower.endswith(".csv"):
            out = out + ".csv"
        # Prevent degenerate names.
        if out in (".csv",):
            out = "input.csv"
    return out


class RunStartRequest(BaseModel):
    input_path: str = DEFAULT_INPUT
    output_path: str = DEFAULT_OUTPUT
    low_confidence_path: str = DEFAULT_LOW_CONF
    youtube: bool = True
    instagram: bool = True
    llm_rerank: bool = True
    # Default to a modern structured-output-capable model; the reranker will
    # fall back to gpt-4o-mini if the chosen model isn't available.
    llm_model: str = "gpt-5-mini"
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


def _count_input_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return count_data_rows(path)


def _count_rows(csv_path: Path) -> int:
    """Count rows in a CSV file (excluding header)."""
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


def _read_event_stats(events_path: Path) -> dict[str, int]:
    """
    Compute progress directly from the event stream, so UI updates don't depend on checkpoints.
    Uses incremental parsing with a simple in-memory cache keyed by file path.
    """

    if not events_path.exists():
        return {
            "processed": 0,
            "invalid": 0,
            "hydrated_youtube": 0,
            "hydrated_instagram": 0,
            "low_confidence": 0,
        }

    cache_key = str(events_path)
    stat = events_path.stat()
    cached = _EVENT_STATS_CACHE.get(cache_key)
    if cached and cached.get("inode") == stat.st_ino and cached.get("size", 0) == stat.st_size:
        return cached["stats"]  # type: ignore[return-value]

    # Reset if file changed/truncated.
    pos = 0
    stats = {
        "processed": 0,
        "invalid": 0,
        "hydrated_youtube": 0,
        "hydrated_instagram": 0,
        "low_confidence": 0,
    }
    if cached and cached.get("inode") == stat.st_ino and isinstance(cached.get("pos"), int):
        cached_pos = int(cached["pos"])
        if cached_pos <= stat.st_size:
            pos = cached_pos
            stats = dict(cached.get("stats", stats))  # type: ignore[arg-type]

    with events_path.open("r", encoding="utf-8", errors="ignore") as file:
        file.seek(pos)
        for line in file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type == "invalid_row":
                stats["processed"] += 1
                stats["invalid"] += 1
                continue
            if event_type == "row_complete":
                stats["processed"] += 1
                yt = event.get("youtube")
                ig = event.get("instagram")
                if isinstance(yt, str):
                    if yt.startswith("hit"):
                        stats["hydrated_youtube"] += 1
                    if yt == "low_confidence":
                        stats["low_confidence"] += 1
                if isinstance(ig, str) and ig.startswith("hit"):
                    stats["hydrated_instagram"] += 1
        new_pos = file.tell()

    _EVENT_STATS_CACHE[cache_key] = {
        "inode": stat.st_ino,
        "size": stat.st_size,
        "pos": new_pos,
        "stats": stats,
    }
    return stats


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
    # On Unix, zombies still pass os.kill(pid, 0); treat them as not alive.
    try:
        ps_result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
        if ps_result.returncode == 0 and "Z" in ps_result.stdout.strip():
            return False
    except Exception:
        pass
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
    stop_requested = bool(state.get("stop_requested_at"))
    if running and stop_requested:
        run_state = "stopping"
    elif running:
        run_state = "running"
    else:
        run_state = "completed" if state else "idle"
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
        events_path = _state_path(paths.base_dir, state, "events_path", RUN_EVENTS)
        event_stats = _read_event_stats(events_path)
        # Prefer checkpoint totals when present, but use events for low-latency progress and counts.
        checkpoint["processed"] = max(checkpoint["processed"], event_stats["processed"])
        checkpoint["invalid"] = max(checkpoint["invalid"], event_stats["invalid"])
        checkpoint["hydrated_youtube"] = max(checkpoint["hydrated_youtube"], event_stats["hydrated_youtube"])
        checkpoint["hydrated_instagram"] = max(checkpoint["hydrated_instagram"], event_stats["hydrated_instagram"])
        checkpoint["low_confidence"] = max(checkpoint["low_confidence"], event_stats["low_confidence"])
        planned_total = state.get("planned_total")
        if checkpoint["total"] == 0 and isinstance(planned_total, int) and planned_total > 0:
            checkpoint["total"] = planned_total
            checkpoint["remaining"] = max(0, planned_total - checkpoint["processed"])
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


def _csv_preview_paged(path: Path, *, offset: int = 0, limit: int = 200) -> dict[str, Any]:
    if not path.exists():
        return {"headers": [], "rows": [], "next_offset": 0}
    rows: list[list[str]] = []
    next_offset = 0
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        for index, row in enumerate(reader):
            if index < offset:
                continue
            if len(rows) >= limit:
                break
            rows.append(row)
            next_offset = index + 1
    if next_offset == 0 and offset > 0:
        next_offset = offset
    return {"headers": headers, "rows": rows, "next_offset": next_offset}


def _input_preview(path: Path, limit: int = 30) -> dict[str, Any]:
    return preview_rows(path, limit=limit)  # type: ignore[return-value]


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
      * { box-sizing: border-box; }
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
      tr.row-selected td { background: #e9f2ff; }
      .insights { display:grid; grid-template-columns: repeat(2, minmax(240px, 1fr)); gap: 10px; }
      .insight-box { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 10px; box-shadow: var(--shadow); }
      .k { color: var(--muted); font-size: 12px; }
      .v { font-weight: 650; }
      .pill { display:inline-block; padding: 2px 8px; border-radius: 999px; background: var(--accent-soft); color: #134ea9; border: 1px solid #b9cdf0; font-size: 11px; margin-right: 6px; }
      .mono { font-family: ui-monospace, Menlo, SFMono-Regular, Consolas, monospace; font-size: 12px; }
      .inspector { margin-top: 12px; }
      .inspector pre { margin: 6px 0 0 0; white-space: pre-wrap; }
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
      .run-settings-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top:10px; }
      .run-settings-compact { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
      @media (max-width: 980px) {
        .grid { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
        .run-settings-grid { grid-template-columns: 1fr; }
        .run-settings-compact { grid-template-columns: 1fr; }
        .resizable { min-width: 0; }
      }
    </style>
  </head>
  <body>
    <h2>Contact Enrichment Control</h2>
    <div class="status">
      <b>Run Settings</b>
      <div class="run-settings-grid">
	        <div>
	          <div class="k">Input File (CSV/XLSX)</div>
	          <div style="display:flex; gap:8px; align-items:center">
	            <input id="inputPath" class="mono" type="text" value="MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.csv"
	              style="flex:1; width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" oninput="fetchInputPreview()" />
	            <button type="button" onclick="browseInputCsv()">Browse...</button>
	          </div>
	          <input id="inputBrowse" type="file" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" style="display:none" />
	        </div>
        <div>
          <div class="k">Output CSV (Hydrated)</div>
          <input id="outputPath" class="mono" type="text" value="MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.hydrated.full.csv"
            style="width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" />
        </div>
        <div>
          <div class="k">Low Confidence CSV</div>
          <input id="lowConfPath" class="mono" type="text" value="MVI - Elite Outreach List & Tracker - Master List - Elite - Intake - 3009 - 11_16_2025.low-confidence.full.csv"
            style="width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" />
        </div>
        <div class="run-settings-compact">
	          <div>
	            <div class="k" title="Flush output files + emit a progress checkpoint line every N processed rows.">Checkpoint Every</div>
	            <input id="checkpointEvery" class="mono" type="number" min="1" value="10"
	              style="width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" />
	          </div>
          <div>
            <div class="k">Limit (blank = all)</div>
            <input id="limit" class="mono" type="number" min="1" placeholder=""
              style="width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" />
          </div>
          <div>
            <div class="k">LLM Model</div>
            <select id="llmModelSelect" class="mono"
              style="width:100%; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px; background:#fff">
              <optgroup label="GPT-5 (recommended)">
                <option value="gpt-5-mini" selected>gpt-5-mini (best default)</option>
                <option value="gpt-5-nano">gpt-5-nano (fastest/cheapest)</option>
                <option value="gpt-5">gpt-5</option>
                <option value="gpt-5.1">gpt-5.1 (higher quality)</option>
                <option value="gpt-5.2">gpt-5.2 (highest quality)</option>
              </optgroup>
              <optgroup label="GPT-4 (fallback)">
                <option value="gpt-4o-mini">gpt-4o-mini</option>
                <option value="gpt-4o">gpt-4o</option>
                <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                <option value="gpt-4.1">gpt-4.1</option>
              </optgroup>
              <option value="custom">Custom...</option>
            </select>
            <input id="llmModelCustom" class="mono" type="text" value=""
              placeholder="custom-model-name"
              style="display:none; width:100%; margin-top:6px; padding:7px 10px; border:1px solid var(--line-strong); border-radius:10px" />
          </div>
        </div>
      </div>
      <div style="display:flex; flex-wrap:wrap; align-items:center; gap: 14px; margin-top:10px">
        <label style="user-select:none"><input id="youtubeEnabled" type="checkbox" checked /> YouTube</label>
        <label style="user-select:none"><input id="instagramEnabled" type="checkbox" checked /> Instagram</label>
        <label style="user-select:none"><input id="llmRerank" type="checkbox" checked /> LLM rerank</label>
        <label style="user-select:none"><input id="strict" type="checkbox" /> Strict</label>
        <span id="state" style="margin-left:auto"></span>
      </div>
      <div style="margin-top:10px">
        <button onclick="startRun()">Start</button>
        <button onclick="stopRun()">Stop</button>
      </div>
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
    <h3>Insights</h3>
    <div class="insights">
      <div class="insight-box">
        <div class="v">Duplicate YouTube Channels</div>
        <div class="k">Same channel assigned to multiple leads (can indicate false positives).</div>
        <div id="insightDupes" style="margin-top:8px">-</div>
      </div>
      <div class="insight-box">
        <div class="v">Low Confidence Breakdown</div>
        <div class="k">Why matches were downgraded or rejected.</div>
        <div id="insightLow" style="margin-top:8px">-</div>
      </div>
    </div>
    <h3>History (Hit / No Hit)</h3>
    <div style="margin: 6px 0 10px 0">
      <span class="k">Filter:</span>
      <input id="filterText" type="text" placeholder="name / handle / url / domain" style="padding:6px 10px; border:1px solid var(--line-strong); border-radius:10px; min-width: 320px" oninput="setFilter(this.value)" />
      <span class="k" style="margin-left:10px">Click a row to inspect details.</span>
    </div>
    <div class="resizable">
      <div class="scroll"><table id="historyTable"></table></div>
    </div>
    <div class="inspector">
      <h3>Row Inspector</h3>
      <div class="insight-box" id="inspectorBox">Select a row in History/Output/Low Confidence to inspect.</div>
    </div>
    <h3>CSV Visualizer</h3>
    <div class="tabs">
      <button id="tab-original" class="tab-btn active" onclick="setTab('original')">Original CSV</button>
      <button id="tab-hydrated" class="tab-btn" onclick="setTab('hydrated')">Hydrated CSV</button>
      <button id="tab-lowconf" class="tab-btn" onclick="setTab('lowconf')">Low Confidence</button>
    </div>
    <div id="pane-original" class="tab-pane active">
      <div class="resizable"><div class="scroll"><table id="inputTable"></table></div></div>
    </div>
    <div id="pane-hydrated" class="tab-pane">
      <div class="resizable"><div class="scroll"><table id="outputTable"></table></div></div>
    </div>
    <div id="pane-lowconf" class="tab-pane">
      <div class="resizable"><div class="scroll"><table id="lowConfTable"></table></div></div>
    </div>
    <script>
      function esc(v) {
        return String(v ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }
      function safeUrl(u) {
        try {
          const url = new URL(String(u));
          if (url.protocol === 'http:' || url.protocol === 'https:') return url.toString();
        } catch {}
        return '';
      }
      function renderTable(elId, headers, rows, rowClassFn = null, cellHtmlFn = null, rowKeyFn = null) {
        const el = document.getElementById(elId);
        const head = '<tr>' + headers.map(h => '<th>'+esc(h)+'</th>').join('') + '</tr>';
        const body = rows.map(r => {
          const rowClass = rowClassFn ? rowClassFn(r) : '';
          const rowKey = rowKeyFn ? rowKeyFn(r) : '';
          const rowAttr = rowKey ? (' data-rowkey=\"' + esc(rowKey) + '\"') : '';
          return '<tr class="' + rowClass + '">' + r.map((c, i) => {
            if (cellHtmlFn) {
              const maybe = cellHtmlFn(c, i, r);
              if (typeof maybe === 'string') return '<td>' + maybe + '</td>';
            }
            return '<td>' + esc(c) + '</td>';
          }).join('') + '</tr>'.replace('<tr', '<tr' + rowAttr);
        }).join('');
        el.innerHTML = head + body;
      }
      function wireRowClicks(elId) {
        const el = document.getElementById(elId);
        if (!el) return;
        const rows = el.querySelectorAll('tr[data-rowkey]');
        for (const tr of rows) {
          const key = tr.getAttribute('data-rowkey');
          tr.style.cursor = 'pointer';
          tr.onclick = () => selectRow(key || '');
        }
      }
      let currentTab = 'original';
      function setTab(tab) {
        currentTab = tab;
        const tabs = ['original', 'hydrated', 'lowconf'];
        for (const t of tabs) {
          document.getElementById('tab-' + t).classList.toggle('active', tab === t);
          document.getElementById('pane-' + t).classList.toggle('active', tab === t);
        }
      }
      let eventOffset = 0;
      const historyRows = new Map();
      const outputRows = new Map();
      let lowConfOffset = 0;
      let lowConfRows = [];
      let activeRowKey = '';
      let selectedRowKey = '';
      let filterText = '';
      let lastStatus = null;
      function setFilter(v) {
        filterText = String(v || '').toLowerCase();
        renderHistoryTable();
        renderOutputTable();
        renderInsights();
      }
      function selectRow(key) {
        selectedRowKey = String(key || '');
        renderHistoryTable();
        renderOutputTable();
        renderInspector();
      }
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
        lastStatus = s;
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
        } else if (s.state === 'stopping') {
          setActivity('Stopping run...', false);
        } else if (s.state === 'completed') {
          setActivity('Completed', false);
        } else {
          setActivity('Idle', false);
        }
      }
	      async function fetchInputPreview() {
	        const input_path = String(document.getElementById('inputPath')?.value || '').trim();
	        const qp = input_path ? ('&path=' + encodeURIComponent(input_path)) : '';
	        const r = await fetch('/run/input-preview?limit=20' + qp); const p = await r.json();
	        const headers = p.headers.length ? p.headers : ['No input'];
	        const rows = p.rows.length ? p.rows : [['-']];
	        renderTable('inputTable', headers, rows);
	      }
	      function browseInputCsv() {
	        const el = document.getElementById('inputBrowse');
	        if (el) el.click();
	      }
	      async function uploadInputCsv(file) {
	        if (!file) return;
	        setActivity('Uploading input file: ' + (file.name || '(unnamed)'), false);
	        const buf = await file.arrayBuffer();
          const lower = String(file.name || '').toLowerCase();
          const contentType = lower.endsWith('.xlsx')
            ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            : 'text/csv';
	        const resp = await fetch('/run/upload-input', {
	          method: 'POST',
	          headers: {
	            'Content-Type': contentType,
	            'X-Filename': String(file.name || (lower.endsWith('.xlsx') ? 'input.xlsx' : 'input.csv')),
	          },
	          body: buf
	        });
	        if (!resp.ok) {
	          const payload = await resp.json().catch(() => ({}));
	          const detail = payload.detail || ('upload failed with status ' + resp.status);
	          setActivity('Upload failed: ' + detail, false);
	          return;
	        }
	        const payload = await resp.json().catch(() => ({}));
	        const saved = String(payload.saved_as || '');
	        if (saved) {
	          const input = document.getElementById('inputPath');
	          if (input) input.value = saved;
	        }
	        await fetchInputPreview();
	        setActivity('Uploaded input file: ' + (saved || file.name), false);
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
	            youtube_upload_count: row[idx['Youtube Upload count']] || '',
	            youtube_publishing_cadence: row[idx['Youtube Publishing cadence']] || '',
	            youtube_channel_age: row[idx['Youtube Channel Age']] || '',
	            youtube_status: (row[idx['Youtube URL']] || row[idx['Youtube handle']]) ? 'hit' : '',
	            instagram_handle: row[idx['Instagram handle']] || '',
	            instagram_followers: row[idx['Instagram followers']] || '',
	            instagram_status: (row[idx['Instagram handle']] || row[idx['Instagram followers']]) ? 'hit' : '',
	          });
	        }
	        renderOutputTable();
	      }
      function renderLowConfTable() {
        const headers = ['row_number', 'confidence', 'candidate_handle', 'candidate_url', 'source', 'queries'];
        const rows = lowConfRows
          .slice()
          .sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0))
          .slice(0, 500)
          .map((r) => [
            r.row_number || '',
            r.confidence || '',
            r.candidate_handle || '',
            r.candidate_url || '',
            r.source || '',
            r.queries || '',
          ]);
        renderTable(
          'lowConfTable',
          headers,
          rows,
          (r) => {
            const key = String(r[0] || '');
            const parts = [];
            if (key && key === selectedRowKey) parts.push('row-selected');
            if (key && key === activeRowKey) parts.push('row-active');
            return parts.join(' ');
          },
          (cell, colIndex, row) => {
            // candidate_url column
            if (colIndex !== 3) return null;
            const u = safeUrl(cell);
            if (!u) return esc(cell);
            return '<a href="' + esc(u) + '" target="_blank" rel="noreferrer">open</a> <span style="color:#5b6778">' + esc(u) + '</span>';
          },
          (r) => String(r[0] || '')
        );
        wireRowClicks('lowConfTable');
      }
      async function fetchLowConfidence() {
        // Read from the start; file is typically much smaller than hydrated output.
        if (lowConfOffset === 0) lowConfRows = [];
        const r = await fetch('/run/low-confidence-preview?offset=' + lowConfOffset + '&limit=200');
        const p = await r.json();
        lowConfOffset = p.next_offset || lowConfOffset;
        if (p.headers && p.headers.length && p.rows && p.rows.length) {
          const idx = {};
          p.headers.forEach((h, i) => { idx[h] = i; });
          for (const row of p.rows) {
            lowConfRows.push({
              row_number: row[idx['row_number']] || '',
              queries: row[idx['queries']] || '',
              candidate_url: row[idx['candidate_url']] || '',
              candidate_handle: row[idx['candidate_handle']] || '',
              confidence: row[idx['confidence']] || '',
              source: row[idx['source']] || '',
            });
          }
        }
        renderLowConfTable();
      }
      function renderHistoryTable() {
        const rows = Array.from(historyRows.values())
          .sort((a, b) => Number(a[0]) - Number(b[0]))
          .filter((r) => {
            if (!filterText) return true;
            const blob = (String(r[1] || '') + ' ' + String(r[2] || '') + ' ' + String(r[3] || '')).toLowerCase();
            return blob.includes(filterText);
          })
          .slice(-500);
        renderTable(
          'historyTable',
          ['row', 'name', 'youtube', 'instagram', 'outcome'],
          rows,
          (r) => {
            const key = String(r[0] || '');
            const parts = [];
            if (key && key === selectedRowKey) parts.push('row-selected');
            if (key && key === activeRowKey) parts.push('row-active');
            return parts.join(' ');
          },
          null,
          (r) => String(r[0] || '')
        );
        wireRowClicks('historyTable');
      }
      function renderOutputTable() {
        const rows = Array.from(outputRows.values())
          .sort((a, b) => Number(a.row_number) - Number(b.row_number))
          .filter((v) => {
            if (!filterText) return true;
            const blob = (
              String(v.name || '') + ' ' +
              String(v.youtube_handle || '') + ' ' +
              String(v.youtube_url || '') + ' ' +
              String(v.youtube_source || '') + ' ' +
              String(v.youtube_confidence_reason || '') + ' ' +
              String(v.youtube_queries || '')
            ).toLowerCase();
            return blob.includes(filterText);
          })
          .slice(-500)
          .map((v) => [
            v.row_number,
            v.name,
            v.youtube_handle,
            v.youtube_url,
            v.youtube_source || '',
            v.youtube_confidence ?? '',
            v.youtube_confidence_reason || '',
            (Array.isArray(v.youtube_evidence_sources) ? v.youtube_evidence_sources.join(', ') : (v.youtube_evidence_sources || '')),
            (typeof v.youtube_content_affinity === 'number' ? v.youtube_content_affinity.toFixed(2) : (v.youtube_content_affinity || '')),
            v.youtube_subs_count,
            v.youtube_upload_count || '',
            v.youtube_publishing_cadence || '',
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
            'youtube_source',
            'youtube_conf',
            'yt_conf_why',
            'youtube_evidence',
            'yt_affinity',
            'youtube_subs',
            'youtube_uploads',
            'yt_cadence',
            'youtube_status',
            'instagram_handle',
            'instagram_followers',
            'instagram_status',
          ],
          rows,
          (r) => {
            const key = String(r[0] || '');
            const parts = [];
            if (key && key === selectedRowKey) parts.push('row-selected');
            if (key && key === activeRowKey) parts.push('row-active');
            return parts.join(' ');
          },
          (cell, colIndex, row) => {
            // youtube_url column
            if (colIndex !== 3) return null;
            const u = safeUrl(cell);
            if (!u) return esc(cell);
            return '<a href="' + esc(u) + '" target="_blank" rel="noreferrer">open</a> <span style="color:#5b6778">' + esc(u) + '</span>';
          },
          (r) => String(r[0] || '')
        );
        wireRowClicks('outputTable');
      }
	      function renderInsights() {
	        function lowConfExplain(src) {
	          const raw = String(src || '').trim();
	          const s = raw.toLowerCase();
	          if (!s) return 'Needs review.';
	          if (s === 'duplicate-guard') return 'Same channel assigned across unrelated leads/domains.';
	          const tokens = raw.split(',').map(t => String(t || '').trim()).filter(Boolean);
	          const phrases = [];
	          for (const t of tokens) {
	            const tl = t.toLowerCase();
	            if (tl.startsWith('hint')) phrases.push('Came from a hint field.');
	            else if (tl.startsWith('website-link') || tl.startsWith('website')) phrases.push('Found on the website.');
	            else if (tl.startsWith('multi-source')) phrases.push('Seen via multiple sources.');
	            else if (tl.startsWith('llm-reject')) phrases.push('LLM rejected the candidates.');
	            else if (tl.startsWith('llm-pick')) phrases.push('LLM had to pick between candidates.');
	            else if (tl.startsWith('content-mismatch')) phrases.push('Channel content looks unrelated.');
	            else if (tl.startsWith('content-weak')) phrases.push('Channel content match is weak.');
	            else if (tl.startsWith('web-fail')) phrases.push('Web validation did not confirm it.');
	            else if (tl === '404') phrases.push('Channel URL did not load.');
	            else if (tl.startsWith('api-needed')) phrases.push('Not API-verified.');
	          }
	          if (!phrases.length) {
	            if (s.includes('content-mismatch')) return 'Channel content looks unrelated.';
	            return 'Needs review.';
	          }
	          return phrases.slice(0, 2).join(' ');
	        }

	        // Duplicate channels among current outputRows.
	        const counts = new Map();
	        const names = new Map();
	        for (const v of outputRows.values()) {
          const url = String(v.youtube_url || '').trim();
          if (!url) continue;
          const key = url.toLowerCase().split('?', 1)[0].replace(/\\/+$/, '');
          counts.set(key, (counts.get(key) || 0) + 1);
          if (!names.has(key)) names.set(key, []);
          names.get(key).push(String(v.name || '').trim() || ('row ' + v.row_number));
        }
        const dupes = Array.from(counts.entries()).filter(([, c]) => c > 1).sort((a, b) => b[1] - a[1]).slice(0, 8);
        const dupEl = document.getElementById('insightDupes');
        if (!dupes.length) {
          dupEl.textContent = 'None so far.';
        } else {
          dupEl.innerHTML = dupes.map(([u, c]) => {
            const open = safeUrl(u) ? ('<a href=\"' + esc(u) + '\" target=\"_blank\" rel=\"noreferrer\">open</a>') : esc(u);
            const who = (names.get(u) || []).slice(0, 5).map(esc).join(', ');
            return '<div style=\"margin:6px 0\"><span class=\"pill\">' + c + 'x</span> ' + open + '<div class=\"k\">' + who + '</div></div>';
          }).join('');
        }

        const lowEl = document.getElementById('insightLow');
        if (!lowConfRows.length) {
          const expected = Number(lastStatus?.low_confidence || 0);
          if (expected > 0) {
            // Fallback: show count even if the CSV hasn't been loaded yet.
            const fromHistory = Array.from(historyRows.values()).filter(r => String(r[4] || '') === 'low_confidence').length;
            const count = Math.max(expected, fromHistory);
            lowEl.textContent = 'Loading low-confidence report... (' + count + ' rows)';
          } else {
            lowEl.textContent = 'None so far.';
          }
	        } else {
	          const reasonCounts = new Map();
	          for (const r of lowConfRows) {
	            const src = String(r.source || 'unknown');
	            reasonCounts.set(src, (reasonCounts.get(src) || 0) + 1);
	          }
	          const top = Array.from(reasonCounts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 10);
	          lowEl.innerHTML = top.map(([src, c]) => {
	            const explain = lowConfExplain(src);
	            return '<div style=\"margin:6px 0\">' +
	              '<span class=\"pill\">' + c + '</span> ' +
	              '<span class=\"mono\">' + esc(src) + '</span>' +
	              (explain ? ('<div class=\"k\" style=\"margin-left: 34px\">' + esc(explain) + '</div>') : '') +
	            '</div>';
	          }).join('');
	        }
	      }
      function renderInspector() {
        const box = document.getElementById('inspectorBox');
        if (!selectedRowKey) {
          box.textContent = 'Select a row in History/Output/Low Confidence to inspect.';
          return;
        }
        const v = outputRows.get(String(selectedRowKey));
        const low = lowConfRows.find(r => String(r.row_number || '') === String(selectedRowKey));
        const name = (v && v.name) ? v.name : (low ? ('row ' + low.row_number) : ('row ' + selectedRowKey));
	        const url = v ? (v.youtube_url || '') : '';
	        const handle = v ? (v.youtube_handle || '') : '';
	        const status = v ? (v.youtube_status || '') : '';
	        const source = v ? (v.youtube_source || '') : (low ? (low.source || '') : '');
	        const conf = v ? (v.youtube_confidence ?? '') : (low ? (low.confidence || '') : '');
	        const confWhy = v ? (v.youtube_confidence_reason || '') : '';
	        const subs = v ? (v.youtube_subs_count || '') : '';
	        const subsSrc = v ? (v.youtube_subscriber_count_source || '') : '';
	        const uploads = v ? (v.youtube_upload_count || '') : '';
	        const uploadsSrc = v ? (v.youtube_upload_count_source || '') : '';
	        const cadence = v ? (v.youtube_publishing_cadence || '') : '';
	        const cadenceSrc = v ? (v.youtube_cadence_source || '') : '';
	        const age = v ? (v.youtube_channel_age || '') : '';
	        const affinity = v ? v.youtube_content_affinity : null;
	        const evidence = v && v.youtube_evidence_sources ? (Array.isArray(v.youtube_evidence_sources) ? v.youtube_evidence_sources.join(', ') : String(v.youtube_evidence_sources)) : '';
	        const queries = v && v.youtube_queries ? (Array.isArray(v.youtube_queries) ? v.youtube_queries.join('\\n') : String(v.youtube_queries)) : (low ? (low.queries || '') : '');
	        const titles = v && Array.isArray(v.youtube_recent_titles) ? v.youtube_recent_titles : [];
	        const open = safeUrl(url) ? ('<a href=\"' + esc(url) + '\" target=\"_blank\" rel=\"noreferrer\">open</a>') : '';

        box.innerHTML = '' +
          '<div style=\"display:grid; grid-template-columns: 140px 1fr; gap: 6px 10px\">' +
          '<div class=\"k\">Row</div><div class=\"v\">' + esc(selectedRowKey) + '</div>' +
          '<div class=\"k\">Name</div><div class=\"v\">' + esc(name) + '</div>' +
          '<div class=\"k\">YouTube status</div><div class=\"mono\">' + esc(status) + '</div>' +
	          '<div class=\"k\">YouTube URL</div><div class=\"mono\">' + (open ? open + ' ' : '') + esc(url) + '</div>' +
	          '<div class=\"k\">YouTube handle</div><div class=\"mono\">' + esc(handle) + '</div>' +
	          '<div class=\"k\">Source</div><div class=\"mono\">' + esc(source) + '</div>' +
	          '<div class=\"k\">Confidence</div><div class=\"mono\">' + esc(conf) + '</div>' +
	          '<div class=\"k\">Conf why</div><div class=\"mono\">' + esc(confWhy || '') + '</div>' +
	          '<div class=\"k\">Subscribers</div><div class=\"mono\">' + esc(subs) + (subsSrc ? (' <span class=\"k\">(' + esc(subsSrc) + ')</span>') : '') + '</div>' +
	          '<div class=\"k\">Uploads</div><div class=\"mono\">' + esc(uploads) + (uploadsSrc ? (' <span class=\"k\">(' + esc(uploadsSrc) + ')</span>') : '') + '</div>' +
	          '<div class=\"k\">Cadence</div><div class=\"mono\">' + esc(cadence) + (cadenceSrc ? (' <span class=\"k\">(' + esc(cadenceSrc) + ')</span>') : '') + '</div>' +
	          '<div class=\"k\">Channel age</div><div class=\"mono\">' + esc(age) + '</div>' +
	          '<div class=\"k\">Evidence</div><div class=\"mono\">' + esc(evidence) + '</div>' +
	          '<div class=\"k\">Content affinity</div><div class=\"mono\">' + esc((typeof affinity === 'number') ? affinity.toFixed(2) : (affinity || '')) + '</div>' +
	          '</div>' +
          '<div style=\"margin-top:10px\"><div class=\"k\">Queries</div><pre class=\"mono\">' + esc(queries) + '</pre></div>' +
          '<div style=\"margin-top:10px\"><div class=\"k\">Recent video titles</div>' +
            (titles.length ? ('<ul style=\"margin:6px 0 0 16px\">' + titles.map(t => '<li class=\"mono\">' + esc(t) + '</li>').join('') + '</ul>') : '<div class=\"k\">(not available)</div>') +
          '</div>';
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
            existing.youtube_upload_count = e.youtube_upload_count || existing.youtube_upload_count;
            existing.youtube_publishing_cadence = e.youtube_publishing_cadence || existing.youtube_publishing_cadence;
            existing.youtube_channel_age = e.youtube_channel_age || existing.youtube_channel_age;
            existing.youtube_status = e.status || existing.youtube_status;
            existing.youtube_source = e.youtube_source || e.method || existing.youtube_source;
            existing.youtube_confidence = e.youtube_confidence ?? existing.youtube_confidence;
            existing.youtube_confidence_reason = e.youtube_confidence_reason ?? existing.youtube_confidence_reason;
            existing.youtube_subscriber_count_source = e.youtube_subscriber_count_source ?? existing.youtube_subscriber_count_source;
            existing.youtube_upload_count_source = e.youtube_upload_count_source ?? existing.youtube_upload_count_source;
            existing.youtube_cadence_source = e.youtube_cadence_source ?? existing.youtube_cadence_source;
            existing.youtube_evidence_sources = e.youtube_evidence_sources || existing.youtube_evidence_sources;
            existing.youtube_content_affinity = e.youtube_content_affinity ?? existing.youtube_content_affinity;
            existing.youtube_recent_titles = e.youtube_recent_video_titles || existing.youtube_recent_titles;
            existing.youtube_queries = e.queries || existing.youtube_queries;
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
        renderInsights();
        renderInspector();
      }
      async function startRun() {
        const input_path = String(document.getElementById('inputPath')?.value || '').trim();
        const output_path = String(document.getElementById('outputPath')?.value || '').trim();
        const low_confidence_path = String(document.getElementById('lowConfPath')?.value || '').trim();
        const youtube = Boolean(document.getElementById('youtubeEnabled')?.checked);
        const instagram = Boolean(document.getElementById('instagramEnabled')?.checked);
        const llm_rerank = Boolean(document.getElementById('llmRerank')?.checked);
        const selected = String(document.getElementById('llmModelSelect')?.value || 'gpt-5-mini');
        const llm_model = (selected === 'custom')
          ? (String(document.getElementById('llmModelCustom')?.value || '').trim() || 'gpt-5-mini')
          : selected;
        const strict = Boolean(document.getElementById('strict')?.checked);
        const checkpoint_every_raw = String(document.getElementById('checkpointEvery')?.value || '').trim();
        const checkpoint_every = Math.max(1, Number(checkpoint_every_raw || 10));
        const limit_raw = String(document.getElementById('limit')?.value || '').trim();
        const limit = limit_raw ? Math.max(1, Number(limit_raw)) : null;

        if (!input_path) {
          setActivity('Start failed: input_path is required', false);
          return;
        }
        if (!output_path) {
          setActivity('Start failed: output_path is required', false);
          return;
        }
        if (!low_confidence_path) {
          setActivity('Start failed: low_confidence_path is required', false);
          return;
        }
        const response = await fetch('/run/start', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            input_path,
            output_path,
            low_confidence_path,
            youtube,
            instagram,
            llm_rerank,
            llm_model,
            strict,
            checkpoint_every,
            limit
          })
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          const detail = payload.detail || ('start failed with status ' + response.status);
          setActivity('Start failed: ' + detail, false);
          return;
        }
        eventOffset = 0;
        lowConfOffset = 0;
        lowConfRows = [];
        historyRows.clear();
        outputRows.clear();
        activeRowKey = '';
        renderHistoryTable();
        renderOutputTable();
        renderLowConfTable();
        fetchInputPreview();
        setActivity('Run starting...', true);
      }
      async function stopRun() {
        const response = await fetch('/run/stop', { method: 'POST' });
        if (!response.ok) {
          setActivity('Stop failed', false);
          return;
        }
        currentState = 'stopping';
        setActivity('Stopping run...', false);
      }
      async function tick() {
        await fetchStatus();
        await fetchEvents();
        const expected = Number(lastStatus?.low_confidence || 0);
        if (currentTab === 'lowconf' || expected > lowConfRows.length || (currentState === 'running' && expected > 0)) {
          await fetchLowConfidence();
        }
        renderInsights();
        renderInspector();
      }
	      document.getElementById('llmModelSelect')?.addEventListener('change', (e) => {
	        const v = String(e?.target?.value || '');
	        const custom = document.getElementById('llmModelCustom');
	        if (!custom) return;
	        custom.style.display = (v === 'custom') ? 'block' : 'none';
	      });
	      document.getElementById('inputBrowse')?.addEventListener('change', (e) => {
	        const file = e?.target?.files?.[0];
	        uploadInputCsv(file);
	        // Reset so picking the same file twice re-triggers change.
	        try { e.target.value = ''; } catch {}
	      });
	      fetchInputPreview(); preloadOutputPreview(); renderLowConfTable(); tick(); setInterval(tick, 3000);
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
        if payload.llm_rerank:
            cmd.append("--llm-rerank")
            if payload.llm_model:
                cmd.extend(["--llm-model", payload.llm_model])
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
                # Enables immediate progress reporting even before the first checkpoint log line.
                "planned_total": payload.limit
                if payload.limit is not None
                else _count_input_rows(base / payload.input_path),
            },
        )
        return {"state": "running", "pid": proc.pid}

    @app.post("/run/stop")
    def run_stop() -> dict[str, Any]:
        state = _read_state(paths)
        pid = state.get("pid") if isinstance(state.get("pid"), int) else None
        if not _is_pid_alive(pid):
            return {"state": "idle", "stopped": False}
        state["stop_requested_at"] = datetime.now(timezone.utc).isoformat()
        _write_state(paths, state)
        try:
            if hasattr(os, "killpg"):
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return {"state": "idle", "stopped": False}
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
    def run_input_preview(limit: int = 30, path: str | None = None) -> dict[str, Any]:
        state = _read_state(paths)
        if path:
            try:
                input_path = base / _safe_relpath(path)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            input_path = _state_path(base, state, "input_path", DEFAULT_INPUT)
        return _input_preview(input_path, limit=max(1, min(limit, 200)))

    @app.post("/run/upload-input")
    async def run_upload_input(request: Request) -> dict[str, Any]:
        filename = _safe_upload_filename(request.headers.get("x-filename", "input.csv"))
        # Keep this permissive; different browsers can send odd content types.
        _content_type = (request.headers.get("content-type") or "").lower()
        body = await request.body()
        max_bytes = 50 * 1024 * 1024
        if len(body) > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large (max {max_bytes} bytes).")

        dest = base / filename
        # Avoid clobbering an existing file by accident: if it exists, create a unique name.
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix or ".csv"
            for i in range(1, 200):
                candidate = base / f"{stem}.{i}{suffix}"
                if not candidate.exists():
                    dest = candidate
                    filename = dest.name
                    break

        dest.write_bytes(body)

        # Update state so previews work immediately and the default run input is correct.
        state = _read_state(paths)
        state["input_path"] = filename
        state["planned_total"] = _count_input_rows(dest)
        _write_state(paths, state)

        return {"saved_as": filename, "bytes": len(body)}

    @app.get("/run/output-preview")
    def run_output_preview(limit: int = 30) -> dict[str, Any]:
        state = _read_state(paths)
        output_path = _state_path(base, state, "output_path", DEFAULT_OUTPUT)
        return _output_preview(output_path, limit=max(1, min(limit, 200)))

    @app.get("/run/low-confidence-preview")
    def run_low_confidence_preview(offset: int = 0, limit: int = 200) -> dict[str, Any]:
        state = _read_state(paths)
        low_conf_path = _state_path(base, state, "low_confidence_path", DEFAULT_LOW_CONF)
        return _csv_preview_paged(
            low_conf_path,
            offset=max(0, offset),
            limit=max(1, min(limit, 500)),
        )

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
