# Troubleshooting

## YouTube lookups return blanks
- Verify `--youtube` flag is set.
- Try smaller batches to avoid throttling.
- Ensure name/company fields are present to build queries.

## Instagram lookups return blanks
- Verify `--instagram` flag is set.
- Some profiles block scraping; blanks are expected in those cases.

## Validation errors
- Run with `--strict` to fail fast and locate invalid rows quickly.
- Check that every row has the same number of columns as the header.
