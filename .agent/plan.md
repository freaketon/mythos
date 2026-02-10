# Plan: Contact Enrichment Skill

## Goal
Deliver a small-scale Python skill that reads a contact CSV, hydrates YouTube and Instagram fields using `scrapetube` and `instaloader`, and writes a new hydrated CSV.

## Working Rule
Each step must end with a complete, functioning application state that can run end-to-end for its current scope.

## Step 1: Bootstrap a minimal runnable app (Completed)
- Create project skeleton (`src/`, `tests/`, `pyproject.toml`, entry module).
- Add core dependencies: `pydantic`, CSV handling, logging.
- Implement a no-op pipeline: read CSV rows and write the same rows to output.
- Add a basic skill runner interface (input path, output path).
- Add one smoke test for end-to-end read/write.
- Exit criteria:
- `uv run python -m src.main --input <file> --output <file>` runs successfully.
- Output file exists and matches input columns/rows.

## Step 2: Add schema validation and error reporting (Completed)
- Define Pydantic models for required input fields and hydrated output fields.
- Validate rows at ingestion.
- Implement non-strict mode (skip bad rows, log row-level errors).
- Add tests for valid rows, invalid rows, strict vs non-strict behavior.
- Exit criteria:
- Application runs end-to-end with validation enabled.
- Validation summary is produced and tested.

## Step 3: Implement YouTube adapter (`scrapetube`) (Completed)
- Create adapter module for YouTube lookup and field extraction.
- Map to hydrated fields:
- `Youtube handle`
- `Youtube URL`
- `Youtube Subs count` (best-effort)
- `Youtube Publishing cadence` (best-effort from recent posts)
- `Youtube Channel Age` (best-effort)
- Add source URL logging for each populated YouTube field.
- Add adapter tests using recorded fixtures for deterministic small-scale runs.
- Exit criteria:
- End-to-end run hydrates YouTube fields when a match is found.
- No-match rows stay valid with blank YouTube fields.

## Step 4: Implement Instagram adapter (`instaloader`) (Completed)
- Create adapter module for Instagram lookup and field extraction.
- Map to hydrated fields:
- `Instagram handle`
- `Instagram followers`
- `Instagram publishing cadence` (best-effort)
- `Instagram Account Age` (best-effort)
- Add source URL logging for each populated Instagram field.
- Add adapter tests using recorded fixtures.
- Exit criteria:
- End-to-end run hydrates Instagram fields when a match is found.
- No-match rows stay valid with blank Instagram fields.

## Step 5: Compose hydration pipeline (Next)
- Combine validation + YouTube + Instagram adapters in one deterministic pipeline.
- Preserve all original columns exactly; append hydrated columns in PRD order.
- Ensure duplicate input columns (e.g., repeated `Email`) are handled consistently.
- Add row-level processing summary (processed, hydrated, warnings, errors).
- Add integration test with mixed match/no-match/invalid rows.
- Exit criteria:
- One command processes a sample input and writes a fully hydrated output file.
- Output column order is correct and stable.

## Step 5a: Automated YouTube Handle Discovery + Fallback Research (Completed)
- Implement multi-query automated search (name/company/domain) with scoring + threshold.
- Use direct hints (`youtube.com`, `youtu.be`, `@handle`) as high-confidence matches.
- Add a fallback adapter strategy: try `scrapetube`, then a secondary search tool, then YouTube Data API if configured.
- Add an integration test that exercises scoring + fallback selection.
- Document the research sources and fallback tools in `.agent/plan.md`.

### Fallback Tool Candidates (Research Notes)
- YouTube Data API v3: `search.list` for channel discovery + `channels.list` for channel metadata and subscriber stats (quota-based). citeturn0search0turn0search1turn2search0
- `yt-search-python` (PyPI package name `yt-search-python`): search YouTube without API key; provides channels/videos/playlists. citeturn3search0turn4search3
- `youtube-search-python` (GitHub repo, legacy): similar capabilities but maintenance concerns noted in docs. citeturn4search4turn4search5
- `yt-dlp`: robust extractor; can be used for metadata via URL-based lookups; heavier dependency. citeturn1search1
- `py-yt-search`: async YouTube search library with channels/videos/playlists. citeturn3search1turn4search0

## Step 6: Hardening for personal-use reliability
- Add retry/backoff and request throttling controls for external lookups.
- Add optional row limit for batch processing.
- Ensure graceful degradation when third-party lookups fail.
- Add tests for timeout/failure paths and fallback behavior.
- Exit criteria:
- Tool completes successfully under partial external failures.
- Failures are reported without corrupting output.

## Step 7: Finalize docs and runbook
- Write usage docs with required inputs, options, and example command.
- Document known limits and best-effort nature of social metrics.
- Add troubleshooting notes for common `scrapetube`/`instaloader` issues.
- Add sample input/output fixtures for quick verification.
- Exit criteria:
- A new user can run the tool from docs only.
- Final checks pass: `uv run ruff check .` and `uv run pytest -q`.

## Debug Notes
- Pytest import errors occurred with dotted test filenames (`test_*.unit.py`, `test_*.int.py`).
- Fix: set pytest `--import-mode=importlib` and explicit `python_files` patterns to allow dotted filenames.
- Added `conftest.py` in `src/` to ensure project root is on `sys.path` for dotted test imports.
