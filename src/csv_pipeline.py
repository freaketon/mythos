from __future__ import annotations

import csv
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from src.adapters.instagram import InstagramProfileData
from src.adapters.youtube import YouTubeChannelData

LOGGER = logging.getLogger(__name__)

_YOUTUBE_HANDLE_PATTERN = re.compile(r"(?:youtube\.com/@|@)([A-Za-z0-9._-]+)")
_YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com/[^\s]+|youtu\.be/[^\s]+))",
    re.IGNORECASE,
)

YOUTUBE_HYDRATED_FIELDS = [
    "Youtube handle",
    "Youtube URL",
    "Youtube Subs count",
    "Youtube Publishing cadence",
    "Youtube Channel Age",
]
INSTAGRAM_HYDRATED_FIELDS = [
    "Instagram handle",
    "Instagram followers",
    "Instagram publishing cadence",
    "Instagram Account Age",
]


class RowValidationIssue(BaseModel):
    row_number: int
    message: str


class ValidationReport(BaseModel):
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    issues: list[RowValidationIssue] = Field(default_factory=list)


def _normalize_headers(headers: list[str]) -> list[str]:
    counts: Counter[str] = Counter()
    normalized: list[str] = []
    for header in headers:
        counts[header] += 1
        if counts[header] == 1:
            normalized.append(header)
        else:
            normalized.append(f"{header}__dup{counts[header]}")
    return normalized


def _build_row_model(headers: list[str]) -> type[BaseModel]:
    fields = {header: (str, ...) for header in headers}
    return create_model(
        "InputRow",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _first_value(headers: list[str], row: list[str], target: str) -> str:
    for index, header in enumerate(headers):
        if header == target:
            return row[index].strip()
    return ""


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    return host.replace("www.", "").strip()


def _build_youtube_query(headers: list[str], row: list[str]) -> str | None:
    name = _first_value(headers, row, "Name")
    if not name:
        first_name = _first_value(headers, row, "First name")
        last_name = _first_value(headers, row, "Last name")
        name = " ".join(part for part in [first_name, last_name] if part)
    company = _first_value(headers, row, "Company")
    company_url = _first_value(headers, row, "Company URL")
    domain = _domain_from_url(company_url)

    parts = [name, company, domain]
    query = " ".join(part for part in parts if part)
    return query or None


def _build_youtube_queries(headers: list[str], row: list[str]) -> list[str]:
    hint_handle, hint_url = _extract_youtube_hint(headers, row)
    base_query = _build_youtube_query(headers, row)
    name = _first_value(headers, row, "Name")
    if not name:
        first_name = _first_value(headers, row, "First name")
        last_name = _first_value(headers, row, "Last name")
        name = " ".join(part for part in [first_name, last_name] if part)
    company = _first_value(headers, row, "Company")
    company_url = _first_value(headers, row, "Company URL")
    domain = _domain_from_url(company_url)

    queries: list[str] = []
    for value in [hint_handle, hint_url]:
        if value:
            queries.append(value)
    if name:
        queries.append(f"{name} YouTube")
    if company:
        queries.append(f"{company} YouTube")
    if domain:
        queries.append(f"{domain} YouTube")
    if base_query:
        queries.append(base_query)

    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped


def _extract_youtube_hint(headers: list[str], row: list[str]) -> tuple[str | None, str | None]:
    values = [value.strip() for value in row if value.strip()]
    values.extend(
        [
            _first_value(headers, row, "Company URL"),
            _first_value(headers, row, "Other"),
            _first_value(
                headers,
                row,
                "What's your Twitter bio? (Describe who you help and how you help them in 3 sentences or less).",
            ),
        ]
    )
    handle = None
    channel_url = None
    for value in values:
        lower = value.lower()
        is_candidate = (
            "youtube.com" in lower
            or "youtu.be" in lower
            or value.strip().startswith("@")
        )
        if not is_candidate:
            continue

        handle_match = _YOUTUBE_HANDLE_PATTERN.search(value)
        if handle_match:
            handle = f"@{handle_match.group(1)}"

        url_match = _YOUTUBE_URL_PATTERN.search(value)
        if url_match:
            channel_url = url_match.group(1).rstrip(").,")
        if handle or channel_url:
            break
    return handle, channel_url


def copy_csv_rows(
    input_path: Path,
    output_path: Path,
    *,
    strict: bool = False,
    youtube_lookup: Callable[[list[str]], YouTubeChannelData | None] | None = None,
    instagram_lookup: Callable[[str], InstagramProfileData | None] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    with input_path.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.reader(input_file)
        headers = next(reader, None)
        if headers is None:
            raise ValueError("Input CSV missing header row.")

        normalized_headers = _normalize_headers(headers)
        row_model = _build_row_model(normalized_headers)

        output_headers = headers + YOUTUBE_HYDRATED_FIELDS + INSTAGRAM_HYDRATED_FIELDS

        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(output_headers)

            for line_number, row in enumerate(reader, start=2):
                report.total_rows += 1
                if len(row) != len(headers):
                    message = (
                        "Expected "
                        f"{len(headers)} columns, got {len(row)}."
                    )
                    if strict:
                        raise ValueError(f"Row {line_number}: {message}")
                    report.invalid_rows += 1
                    report.issues.append(
                        RowValidationIssue(row_number=line_number, message=message)
                    )
                    LOGGER.warning("Row %s skipped: %s", line_number, message)
                    continue

                try:
                    row_model.model_validate(dict(zip(normalized_headers, row)))
                except ValidationError as exc:
                    message = str(exc)
                    if strict:
                        raise ValueError(f"Row {line_number}: {message}") from exc
                    report.invalid_rows += 1
                    report.issues.append(
                        RowValidationIssue(row_number=line_number, message=message)
                    )
                    LOGGER.warning("Row %s skipped: %s", line_number, message)
                    continue

                report.valid_rows += 1

                youtube_values = ["", "", "", "", ""]
                if youtube_lookup:
                    hint_handle, hint_url = _extract_youtube_hint(headers, row)
                    queries = _build_youtube_queries(headers, row)
                    if queries:
                        result = youtube_lookup(queries)
                        if result:
                            resolved_handle = result.handle or hint_handle
                            resolved_url = result.url or hint_url
                            youtube_values = [
                                resolved_handle or "",
                                resolved_url or "",
                                str(result.subscriber_count)
                                if result.subscriber_count is not None
                                else "",
                                result.publishing_cadence or "",
                                result.channel_age or "",
                            ]
                            source = result.source_url or resolved_url
                            if source:
                                LOGGER.info("YouTube source URL: %s", source)
                        else:
                            if hint_handle or hint_url:
                                youtube_values = [
                                    hint_handle or "",
                                    hint_url or "",
                                    "",
                                    "",
                                    "",
                                ]
                                LOGGER.info(
                                    "YouTube hint used for row %s (queries=%s).",
                                    line_number,
                                    queries,
                                )
                            else:
                                LOGGER.warning(
                                    "No YouTube match for row %s (queries=%s).",
                                    line_number,
                                    queries,
                                )
                    else:
                        LOGGER.warning("No YouTube query data for row %s.", line_number)

                instagram_values = ["", "", "", ""]
                if instagram_lookup:
                    query = _build_youtube_query(headers, row)
                    if query:
                        result = instagram_lookup(query)
                        if result:
                            instagram_values = [
                                result.handle or "",
                                str(result.followers)
                                if result.followers is not None
                                else "",
                                result.publishing_cadence or "",
                                result.account_age or "",
                            ]
                            if result.source_url:
                                LOGGER.info("Instagram source URL: %s", result.source_url)
                        else:
                            LOGGER.warning(
                                "No Instagram match for row %s (query=%s).",
                                line_number,
                                query,
                            )
                    else:
                        LOGGER.warning("No Instagram query data for row %s.", line_number)

                writer.writerow(row + youtube_values + instagram_values)

    LOGGER.info(
        "Validation summary: total=%s valid=%s invalid=%s",
        report.total_rows,
        report.valid_rows,
        report.invalid_rows,
    )
    return report
