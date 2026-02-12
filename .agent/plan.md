# Plan: Contact Enrichment Skill + Frontend

## Goal
- Keep the enrichment pipeline and frontend aligned with current behavior, and finish the remaining operator-focused gaps.

## Constraints
- Python + `uv` only.
- Personal/small-scale priorities: simple, maintainable, best-effort reliable.
- No regression to existing run flow.

## Definition of Done
- [x] Pipeline enriches CSV and writes hydrated output.
- [x] Frontend controls runs and shows live progress.
- [x] Hydrated tab streams row updates during processing.
- [x] Activity indicator shows item + method + active spinner.
- [x] Active row is visually highlighted.
- [ ] Low-confidence rows are directly reviewable in frontend.
- [ ] Lightweight run-history persistence is available across restarts (optional if explicitly deferred).

## Completed Milestones
- [x] 1) Bootstrap and CLI/skill runner.
  - Verify: `uv run python -m src.main --help`
- [x] 2) Row validation and non-strict error handling.
  - Verify: `uv run pytest -q tests/test_pipeline.int.py`
- [x] 3) YouTube adapter with multi-source fallback and validation chain.
  - Verify: `uv run pytest -q tests/test_youtube_adapter.int.py`
- [x] 4) Instagram adapter with validation and fallback web discovery.
  - Verify: `uv run pytest -q src/test_instagram_adapter.unit.py`
- [x] 5) Checkpointing + low-confidence reporting + events stream.
  - Verify: `uv run pytest -q tests/test_pipeline.int.py`
- [x] 6) Frontend run controls and status API.
  - Verify: `uv run pytest -q tests/test_frontend_api.int.py`
- [x] 7) Frontend UX upgrades (tabs, resizable panels, activity spinner, row highlight, streaming output updates).
  - Verify: `uv run pytest -q tests/test_frontend_api.int.py`
- [x] 8) Run mode scripts (`app`, `fresh-test`, `trial`) and unified launcher.
  - Verify: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch_mode.ps1 -Mode app`

## Remaining Work (Prioritized)
- [ ] 9) Add low-confidence review table in frontend.
  - Include row number, candidate URL, handle, confidence, source.
  - Add basic sort and quick open action.
  - Verify: `uv run pytest -q tests/test_frontend_api.int.py`
- [ ] 10) Clarify and document fallback method taxonomy in UI labels.
  - Ensure method names shown in activity line are stable and user-facing.
  - Verify: manual run + event inspection.
- [ ] 11) Optional: persist run summaries (timestamp + counts + file paths) in local JSON history.
  - Keep minimal and append-only.
  - Verify: restart app and confirm history remains.

## Operational Commands
- Start app: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch_mode.ps1 -Mode app`
- Fresh test session: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch_mode.ps1 -Mode fresh-test`
- Trial session (no tests): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch_mode.ps1 -Mode trial`

## Verification Baseline
- `uv run ruff check .`
- `uv run pytest -q`
