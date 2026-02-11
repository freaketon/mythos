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

## Notes
- Enrichment is best-effort and may return blanks if no match is found.
- Source URLs are logged for traceability when available.
