# PRD: Contact Enrichment Skill + Frontend Controller

## Summary
Build and operate a personal-use Python enrichment tool that reads a contact CSV, enriches YouTube and Instagram fields, writes a hydrated CSV, and exposes a lightweight frontend for run control and live monitoring.

## Scope
- Personal, small-scale usage.
- Best-effort enrichment and validation.
- Fast iteration over enterprise architecture.

## Core Goals
- Read CSV input and preserve original columns.
- Append hydrated social fields.
- Use layered search strategies to improve match quality.
- Emit progress and per-row events for live UI feedback.
- Minimize data loss via frequent checkpoints.

## Input Columns (Preserve As-Is)
- `fDan`
- `Name`
- `Email`
- `Claimed by`
- `Do Not Contact Flag`
- `Last Contacted`
- `Days Since Last Contact`
- `First name`
- `Last name`
- `City`
- `What's your QST number?`
- `Timezone`
- `Other`
- `Kids?`
- `Age`
- `What's the most important thing you would like to get help from the program?`
- `Company URL`
- `Headcount`
- `What's your Twitter bio? (Describe who you help and how you help them in 3 sentences or less).`
- `What industry are you in?`
- `What would make this program a 10/10 for you?`
- `What are the biggest roadblocks holding you back today?`
- `What was your revenue the last 12 months? (USD)`
- `What is your target revenue over the next 12 months?`
- `Any final context you think we should know about?`
- `Phone number`
- `Email`
- `Company`
- `state`
- `Response Type`
- `Start Date (UTC)`
- `Stage Date (UTC)`
- `Submit Date (UTC)`
- `Network ID`
- `Tags`

## Hydrated Columns (Append In Order)
- `Youtube handle`
- `Youtube URL`
- `Youtube Subs count`
- `Youtube Publishing cadence`
- `Youtube Channel Age`
- `Instagram handle`
- `Instagram followers`
- `Instagram publishing cadence`
- `Instagram Account Age`

## Data Source Strategy
- YouTube base: `scrapetube`.
- YouTube fallback chain: `yt-search-python`, YouTube Data API (if `YOUTUBE_API_KEY`), web search validation/fallback, domain-first web fallback (`<domain> youtube` first hit).
- Instagram base: `instaloader`.
- Instagram validation/discovery: web search corroboration (Serper, then DDG fallback).
- Record source URLs where available.

## Backend/Skill Requirements
- Entry point: `src.main`.
- Required args: input/output.
- Optional args: `--youtube`, `--instagram`, `--strict`, `--limit`, `--checkpoint-every`, `--low-confidence-report`, `--events-file`.
- Checkpoint writes every N rows (current default target: 10 from UI control).
- Invalid rows: continue in non-strict mode, summarize issues.
- Low-confidence YouTube matches: include in dedicated report.

## Frontend Requirements
- Serve from `src.web_main` / `src.web_app`.
- Start/stop runs.
- Live metrics cards:
- processed, total, remaining
- hydrated youtube, hydrated instagram
- invalid, low-confidence
- Progress bar.
- Current activity line:
- item + process + method (example: `Alice: Fetching youtube through method multi-source-candidate-search`)
- animated spinner while active.
- Visualizer tabs:
- `Original CSV`
- `Hydrated CSV`
- Streaming behavior:
- hydrated row updates immediately on YouTube result
- same row updates again on Instagram result
- active row highlight color while processing.
- Historical outcomes table:
- row-level hit/no-hit/low-confidence/invalid status.
- Resizable data panels via drag.

## Non-Goals
- Multi-user auth/roles.
- Production-grade orchestration.
- Database persistence.
- Heavy frontend framework migration.

## Current Status (Consolidated)
- Implemented:
- CSV pipeline with validation and enrichment.
- YouTube + Instagram adapters with fallback strategy.
- Checkpointing and event stream emission.
- Frontend controller with tabs, status cards, activity spinner, history, active-row highlight, and streaming hydrated updates.
- Run scripts for app, fresh-test, and trial modes.
- Not yet implemented:
- dedicated low-confidence review UI table with sort/filter/open actions.
- durable run history persistence across sessions.

## Acceptance Criteria
- Running enrichment produces hydrated CSV with appended fields in required order.
- Frontend can start/stop and reflect progress continuously.
- Current activity and row highlight change as work advances.
- Hydrated tab updates incrementally during the run.
- Full test suite and lint pass in current worktree.


