from __future__ import annotations

import csv
import json
import logging
import os
import re
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Callable, TextIO
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


class LowConfidenceIssue(BaseModel):
    row_number: int
    queries: list[str]
    candidate_url: str | None
    candidate_handle: str | None
    confidence: int | None
    source: str | None


class ValidationReport(BaseModel):
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    hydrated_youtube_rows: int = 0
    hydrated_instagram_rows: int = 0
    warning_rows: int = 0
    low_confidence_rows: list[LowConfidenceIssue] = Field(default_factory=list)
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


def _build_instagram_query(headers: list[str], row: list[str]) -> str | None:
    base_query = _build_youtube_query(headers, row)
    other = _first_value(headers, row, "Other")
    company_url = _first_value(headers, row, "Company URL")
    bio = _first_value(
        headers,
        row,
        "What's your Twitter bio? (Describe who you help and how you help them in 3 sentences or less).",
    )
    parts = [base_query or "", other, company_url, bio]
    query = " ".join(part.strip() for part in parts if part and part.strip())
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


def _count_data_rows(input_path: Path) -> int:
    with input_path.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.reader(input_file)
        next(reader, None)
        return sum(1 for _ in reader)


def _emit_event(events_file: TextIO | None, payload: dict[str, object]) -> None:
    if events_file is None:
        return
    payload_with_ts = {"ts": datetime.now(timezone.utc).isoformat(), **payload}
    events_file.write(json.dumps(payload_with_ts) + "\n")
    events_file.flush()


def copy_csv_rows(
    input_path: Path,
    output_path: Path,
    *,
    strict: bool = False,
    youtube_lookup: Callable[[list[str]], YouTubeChannelData | None] | None = None,
    instagram_lookup: Callable[[str], InstagramProfileData | None] | None = None,
    row_limit: int | None = None,
    low_confidence_report_path: Path | None = None,
    checkpoint_every: int = 100,
    events_path: Path | None = None,
) -> ValidationReport:
    report = ValidationReport()
    rows_since_checkpoint = 0
    total_rows_planned = _count_data_rows(input_path)
    if row_limit is not None:
        total_rows_planned = min(total_rows_planned, row_limit)
    low_confidence_file = None
    low_confidence_writer: csv.writer | None = None
    events_file = None

    if low_confidence_report_path is not None:
        low_confidence_file = low_confidence_report_path.open(
            "w",
            encoding="utf-8",
            newline="",
        )
        low_confidence_writer = csv.writer(low_confidence_file)
        low_confidence_writer.writerow(
            [
                "row_number",
                "queries",
                "candidate_url",
                "candidate_handle",
                "confidence",
                "source",
            ]
        )
    if events_path is not None:
        events_file = events_path.open("w", encoding="utf-8", newline="\n")

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
                if row_limit is not None and report.total_rows >= row_limit:
                    break
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
                    _emit_event(
                        events_file,
                        {
                            "type": "invalid_row",
                            "row_number": line_number,
                            "status": "invalid",
                            "reason": message,
                        },
                    )
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
                    _emit_event(
                        events_file,
                        {
                            "type": "invalid_row",
                            "row_number": line_number,
                            "status": "invalid",
                            "reason": "validation_error",
                        },
                    )
                    continue

                report.valid_rows += 1
                row_name = _first_value(headers, row, "Name")
                _emit_event(
                    events_file,
                    {
                        "type": "row_start",
                        "row_number": line_number,
                        "name": row_name,
                        "item": row_name or f"row {line_number}",
                        "status": "searching",
                        "method": "row-initialization",
                    },
                )

                youtube_values = ["", "", "", "", ""]
                youtube_status = "disabled"
                if youtube_lookup:
                    hint_handle, hint_url = _extract_youtube_hint(headers, row)
                    queries = _build_youtube_queries(headers, row)
                    if queries:
                        _emit_event(
                            events_file,
                            {
                                "type": "youtube_searching",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": "searching",
                                "method": "multi-source-candidate-search",
                            },
                        )
                        result = youtube_lookup(queries)
                        if result and result.accepted:
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
                            report.hydrated_youtube_rows += 1
                            source = result.source_url or resolved_url
                            if source:
                                LOGGER.info("YouTube HIT row=%s source=%s", line_number, source)
                            youtube_status = "hit"
                        elif result and not result.accepted:
                            issue = LowConfidenceIssue(
                                row_number=line_number,
                                queries=queries,
                                candidate_url=result.url,
                                candidate_handle=result.handle,
                                confidence=result.confidence,
                                source=result.source,
                            )
                            report.low_confidence_rows.append(issue)
                            if low_confidence_writer is not None:
                                low_confidence_writer.writerow(
                                    [
                                        issue.row_number,
                                        " | ".join(issue.queries),
                                        issue.candidate_url or "",
                                        issue.candidate_handle or "",
                                        issue.confidence
                                        if issue.confidence is not None
                                        else "",
                                        issue.source or "",
                                    ]
                                )
                            youtube_status = "low_confidence"
                        else:
                            if hint_handle or hint_url:
                                youtube_values = [
                                    hint_handle or "",
                                    hint_url or "",
                                    "",
                                    "",
                                    "",
                                ]
                                report.hydrated_youtube_rows += 1
                                LOGGER.info(
                                    "YouTube HIT row=%s source=hint",
                                    line_number,
                                )
                                youtube_status = "hit_hint"
                            else:
                                report.warning_rows += 1
                                LOGGER.info("YouTube NO_HIT row=%s", line_number)
                                youtube_status = "no_hit"
                        _emit_event(
                            events_file,
                            {
                                "type": "youtube_result",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": youtube_status,
                                "method": result.source if result else "unknown",
                                "youtube_handle": youtube_values[0],
                                "youtube_url": youtube_values[1],
                                "youtube_subs_count": youtube_values[2],
                                "youtube_publishing_cadence": youtube_values[3],
                                "youtube_channel_age": youtube_values[4],
                            },
                        )
                    else:
                        report.warning_rows += 1
                        LOGGER.info("YouTube NO_HIT row=%s reason=no_query", line_number)
                        youtube_status = "no_query"
                        _emit_event(
                            events_file,
                            {
                                "type": "youtube_result",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": youtube_status,
                                "method": "no-query",
                                "youtube_handle": youtube_values[0],
                                "youtube_url": youtube_values[1],
                                "youtube_subs_count": youtube_values[2],
                                "youtube_publishing_cadence": youtube_values[3],
                                "youtube_channel_age": youtube_values[4],
                            },
                        )

                instagram_values = ["", "", "", ""]
                instagram_status = "disabled"
                if instagram_lookup:
                    query = _build_instagram_query(headers, row)
                    if query:
                        _emit_event(
                            events_file,
                            {
                                "type": "instagram_searching",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": "searching",
                                "method": "instaloader+web-validation",
                            },
                        )
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
                            report.hydrated_instagram_rows += 1
                            if result.source_url:
                                LOGGER.info("Instagram HIT row=%s source=%s", line_number, result.source_url)
                            instagram_status = "hit"
                        else:
                            report.warning_rows += 1
                            LOGGER.info("Instagram NO_HIT row=%s", line_number)
                            instagram_status = "no_hit"
                        _emit_event(
                            events_file,
                            {
                                "type": "instagram_result",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": instagram_status,
                                "method": "instaloader+web-validation",
                                "instagram_handle": instagram_values[0],
                                "instagram_followers": instagram_values[1],
                                "instagram_publishing_cadence": instagram_values[2],
                                "instagram_account_age": instagram_values[3],
                            },
                        )
                    else:
                        report.warning_rows += 1
                        LOGGER.info("Instagram NO_HIT row=%s reason=no_query", line_number)
                        instagram_status = "no_query"
                        _emit_event(
                            events_file,
                            {
                                "type": "instagram_result",
                                "row_number": line_number,
                                "name": row_name,
                                "item": row_name or f"row {line_number}",
                                "status": instagram_status,
                                "method": "no-query",
                                "instagram_handle": instagram_values[0],
                                "instagram_followers": instagram_values[1],
                                "instagram_publishing_cadence": instagram_values[2],
                                "instagram_account_age": instagram_values[3],
                            },
                        )

                writer.writerow(row + youtube_values + instagram_values)
                _emit_event(
                    events_file,
                    {
                        "type": "row_complete",
                        "row_number": line_number,
                        "name": row_name,
                        "item": row_name or f"row {line_number}",
                        "youtube": youtube_status,
                        "instagram": instagram_status,
                        "method": "write-output-row",
                        "youtube_handle": youtube_values[0],
                        "youtube_url": youtube_values[1],
                        "youtube_subs_count": youtube_values[2],
                        "youtube_publishing_cadence": youtube_values[3],
                        "youtube_channel_age": youtube_values[4],
                        "instagram_handle": instagram_values[0],
                        "instagram_followers": instagram_values[1],
                        "instagram_publishing_cadence": instagram_values[2],
                        "instagram_account_age": instagram_values[3],
                    },
                )
                rows_since_checkpoint += 1

                if checkpoint_every > 0 and rows_since_checkpoint >= checkpoint_every:
                    output_file.flush()
                    os.fsync(output_file.fileno())
                    if low_confidence_file is not None:
                        low_confidence_file.flush()
                        os.fsync(low_confidence_file.fileno())
                    remaining_rows = max(0, total_rows_planned - report.total_rows)
                    LOGGER.info(
                        "Checkpoint: processed=%s/%s remaining=%s valid=%s invalid=%s youtube=%s instagram=%s low_conf=%s",
                        report.total_rows,
                        total_rows_planned,
                        remaining_rows,
                        report.valid_rows,
                        report.invalid_rows,
                        report.hydrated_youtube_rows,
                        report.hydrated_instagram_rows,
                        len(report.low_confidence_rows),
                    )
                    rows_since_checkpoint = 0
                    if events_file is not None:
                        events_file.flush()
                        os.fsync(events_file.fileno())

            output_file.flush()
            os.fsync(output_file.fileno())

    LOGGER.info(
        "Validation summary: total=%s valid=%s invalid=%s youtube=%s instagram=%s warnings=%s",
        report.total_rows,
        report.valid_rows,
        report.invalid_rows,
        report.hydrated_youtube_rows,
        report.hydrated_instagram_rows,
        report.warning_rows,
    )

    if low_confidence_file is not None:
        low_confidence_file.flush()
        os.fsync(low_confidence_file.fileno())
        low_confidence_file.close()
    if events_file is not None:
        events_file.flush()
        os.fsync(events_file.fileno())
        events_file.close()

    return report
