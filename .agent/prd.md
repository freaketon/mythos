# PRD: Contact List Enrichment Skill

## Summary
Build an agent skill that reads a contact list file, enriches each contact with YouTube and Instagram data via search, and writes a new hydrated contact list file.

## Goals
- Read contacts from a supported input format (CSV).
- Enrich contacts using a search tool to find YouTube channels and Instagram accounts.
- Write a new output file containing original + hydrated fields.
- Validate input/output at boundaries with Pydantic.

## Tooling Baseline
- YouTube enrichment baseline: `scrapetube` (`https://github.com/dermasmid/scrapetube`).
- Instagram enrichment baseline: `instaloader` (`https://github.com/instaloader/instaloader`).
- Implement integrations behind adapter modules so tooling can be swapped later without touching core enrichment logic.

## Non-Goals
- No UI.
- No database persistence.
- No direct YouTube/Instagram API integrations in v1 (search-only).

## User Stories
- As a user, I can run a skill to enrich `contacts.csv` into `contacts.hydrated.csv`.
- As a user, I get helpful errors for invalid files or formats.

## Input Columns
The input CSV contains the following columns (preserve all):
- fDan
- Name
- Email
- Claimed by
- Do Not Contact Flag
- Last Contacted
- Days Since Last Contact
- First name
- Last name
- City
- What's your QST number?
- Timezone
- Other
- Kids?
- Age
- What’s the most important thing you would like to get help from the program?
- Company URL
- Headcount
- What's your Twitter bio? (Describe who you help and how you help them in 3 sentences or less).
- What industry are you in?
- What would make this program a 10/10 for you?
- What are the biggest roadblocks holding you back today?
- What was your revenue the last 12 months? (USD)
- What is your target revenue over the next 12 months?
- Any final context you think we should know about?
- Phone number
- Email
- Company
- state
- Response Type
- Start Date (UTC)
- Stage Date (UTC)
- Submit Date (UTC)
- Network ID
- Tags

## Hydrated Columns
Add the following columns (appended after original columns):
- Youtube handle
- Youtube URL
- Youtube Subs count
- Youtube Publishing cadence
- Youtube Channel Age
- Instagram handle
- Instagram followers
- Instagram publishing cadence
- Instagram Account Age

## Functional Requirements
- Skill reads a CSV input file and writes a hydrated CSV output file.
- Use `scrapetube` and `instaloader` as primary tooling to find YouTube channels and Instagram accounts per contact.
- Determine YouTube handle/URL/subscriber count/publishing cadence/channel age from search results.
- Determine Instagram handle/followers/publishing cadence/account age from search results.
- Output schema: original fields + hydrated fields in the order listed above.
- Best-effort output for small-scale personal use; log source URLs used for enrichment when available.

## Validation & Error Handling
- Validate input row shape with Pydantic at ingestion.
- If a row fails validation, record error and continue; report summary at end.
- Fail fast for missing input file or unsupported format.
- If no match is found, leave hydrated fields blank and record a warning.

## Skill Spec
- Accepts input path and output path parameters.
- Accepts optional strict mode to fail on validation errors.
- Accepts optional row limit for small batch processing.

## Acceptance Criteria
- Running the skill on a sample CSV produces an output file with hydrated fields.
- Invalid rows are reported with row number and error message.
- Hydrated fields include logged source URLs when available.

## Tech Constraints
- Python 3.12+.
- Use `uv` for scripts/deps.
- Use Pydantic for schema validation at boundaries.
- Avoid `Any` unless justified.

## Open Questions
- Do we need to support JSON input/output in v1? NO
- Should enrichment use official APIs in v2 for more reliable stats? NO
