# Contact Enrichment Skill Usage

## Quick Start
```bash
uv run python -m src.main --input contacts.csv --output contacts.hydrated.csv
```

## Optional Enrichment
```bash
uv run python -m src.main --input contacts.csv --output contacts.hydrated.csv --youtube --instagram
```

## Flags
- `--input`: Path to the input CSV.
- `--output`: Path to the hydrated CSV.
- `--strict`: Fail fast on validation errors.
- `--youtube`: Enable YouTube enrichment via `scrapetube` + `yt-search-python`.
- `--instagram`: Enable Instagram enrichment via `instaloader`.
- `--limit`: Limit number of data rows processed.
- `--low-confidence-report`: Write a CSV report of low-confidence YouTube matches.
- `--checkpoint-every`: Flush output and low-confidence files every N rows (default `100`).

## Notes
- Enrichment is best-effort and may return blanks if no match is found.
- Source URLs are logged for traceability when available.
- Set `YOUTUBE_API_KEY` to enable YouTube Data API fallback.
- Set `SERPER_API_KEY` to enable web search validation for YouTube and Instagram candidates.
- When web validation is enabled and a candidate is not corroborated by search results, the candidate is rejected as low-confidence.
- If Serper is unavailable, the tool falls back to DuckDuckGo HTML search for corroboration.
