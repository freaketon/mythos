from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.adapters.youtube import YouTubeSearchConfig, fetch_recent_video_titles


class QualificationResult(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    theme: str = ""
    recent_video_topic: str = ""
    icp_fit_summary: str = ""
    pitch_angle: str = ""
    ig_dm_message: str = ""


@dataclass(frozen=True)
class QualifyConfig:
    model: str = "gpt-5-mini"
    titles_limit: int = 5
    qualify_threshold: int = 70
    cache_path: Path | None = Path("qualify.cache.jsonl")
    max_retries: int = 2
    timeout_s: float = 45.0


def _read_text_arg(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def _stable_lead_key(row: dict[str, str]) -> str:
    # Prefer stable identifiers; fall back to name + company.
    for k in (
        "Youtube URL",
        "Youtube handle",
        "Instagram handle",
        "Company URL",
        "Email",
    ):
        v = (row.get(k) or "").strip()
        if v:
            return f"{k}:{v.lower()}"
    name = (row.get("Name") or "").strip().lower()
    company = (row.get("Company") or "").strip().lower()
    return f"name_company:{name}|{company}"


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.isdigit():
        return int(v)
    # Common formatted cases: "12,345"
    v2 = v.replace(",", "")
    if v2.isdigit():
        return int(v2)
    return None


class JSONLCache:
    def __init__(self, path: Path):
        self.path = path
        self._loaded: dict[str, dict[str, object]] = {}

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                key = obj.get("key")
                value = obj.get("value")
                if isinstance(key, str) and isinstance(value, dict):
                    self._loaded[key] = value

    def get(self, key: str) -> dict[str, object] | None:
        return self._loaded.get(key)

    def put(self, key: str, value: dict[str, object]) -> None:
        self._loaded[key] = value
        tmp = {"key": key, "value": value, "ts": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(tmp, ensure_ascii=False) + "\n")
            f.flush()


def _default_fetch_titles(row: dict[str, str], limit: int) -> list[str]:
    youtube_url = (row.get("Youtube URL") or row.get("YouTube URL") or "").strip() or None
    if not youtube_url:
        return []
    return fetch_recent_video_titles(channel_url=youtube_url, limit=limit, config=YouTubeSearchConfig())


def _openai_chat_completions_json(
    *,
    api_key: str,
    model: str,
    payload: dict[str, object],
    timeout_s: float,
) -> dict[str, object]:
    system = (
        "Return ONLY valid JSON.\n"
        "Never invent facts; use only the provided evidence.\n"
        "If evidence is insufficient, set fit_score low and explain in icp_fit_summary."
    )
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM returned empty content")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    return parsed


def _run_llm_with_validation(
    *,
    llm_call: Callable[[dict[str, object]], dict[str, object]],
    max_retries: int,
    payload: dict[str, object],
) -> tuple[QualificationResult | None, dict[str, object] | None, str | None]:
    last_err: str | None = None
    last_raw: dict[str, object] | None = None
    for _attempt in range(max(1, max_retries)):
        try:
            raw = llm_call(payload)
            last_raw = raw
            result = QualificationResult.model_validate(raw)
            return result, raw, None
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_err = str(exc)
            continue
    return None, last_raw, last_err


def qualify_rows(
    rows: Iterable[dict[str, str]],
    *,
    icp_prompt: str,
    product_prompt: str,
    config: QualifyConfig,
    llm_call: Callable[[dict[str, object]], dict[str, object]],
    fetch_titles: Callable[[dict[str, str], int], list[str]] = _default_fetch_titles,
) -> list[dict[str, str]]:
    cache = JSONLCache(config.cache_path) if config.cache_path else None
    if cache:
        cache.load()

    out: list[dict[str, str]] = []
    for row in rows:
        enriched = dict(row)
        key = _stable_lead_key(row)
        cached = cache.get(key) if cache else None
        titles = fetch_titles(row, config.titles_limit)
        enriched["qual_youtube_titles_json"] = json.dumps(titles, ensure_ascii=False)

        payload: dict[str, object] = {
            "name": (row.get("Name") or "").strip(),
            "company": (row.get("Company") or "").strip(),
            "youtube_url": (row.get("Youtube URL") or "").strip(),
            "youtube_handle": (row.get("Youtube handle") or "").strip(),
            "youtube_subscribers": _as_int(row.get("Youtube Subs count")),
            "instagram_handle": (row.get("Instagram handle") or "").strip(),
            "instagram_followers": _as_int(row.get("Instagram followers")),
            "youtube_recent_video_titles": titles,
            "icp_prompt": icp_prompt,
            "product_prompt": product_prompt,
            "output_keys": list(QualificationResult.model_fields.keys()),
        }

        started = time.time()
        status = "ok"
        err = ""
        raw: dict[str, object] | None = None

        if cached is not None:
            raw = cached
        else:
            result, raw, err = _run_llm_with_validation(
                llm_call=llm_call,
                max_retries=config.max_retries,
                payload=payload,
            )
            if result is None:
                status = "error"
            if cache and raw is not None:
                cache.put(key, raw)

        elapsed_ms = int((time.time() - started) * 1000)
        enriched["qual_status"] = status
        enriched["qual_error"] = err or ""
        enriched["qual_llm_model"] = config.model
        enriched["qual_llm_latency_ms"] = str(elapsed_ms)
        enriched["qual_llm_json"] = json.dumps(raw or {}, ensure_ascii=False)

        try:
            parsed = QualificationResult.model_validate(raw or {})
            score = int(parsed.fit_score)
            enriched["qual_fit_score"] = str(score)
            enriched["qual_qualified"] = "yes" if score >= config.qualify_threshold else "no"
            enriched["qual_theme"] = parsed.theme
            enriched["qual_recent_video_topic"] = parsed.recent_video_topic
            enriched["qual_icp_fit_summary"] = parsed.icp_fit_summary
            enriched["qual_pitch_angle"] = parsed.pitch_angle
            enriched["qual_ig_dm_message"] = parsed.ig_dm_message
        except ValidationError as exc:
            enriched["qual_fit_score"] = "0"
            enriched["qual_qualified"] = "no"
            enriched["qual_theme"] = ""
            enriched["qual_recent_video_topic"] = ""
            enriched["qual_icp_fit_summary"] = ""
            enriched["qual_pitch_angle"] = ""
            enriched["qual_ig_dm_message"] = ""
            if status == "ok":
                enriched["qual_status"] = "error"
            if not enriched["qual_error"]:
                enriched["qual_error"] = str(exc)

        out.append(enriched)

    # Ranking is a pure sort; we keep it here so consumers can just take the output list.
    out.sort(key=lambda r: int((r.get("qual_fit_score") or "0").strip() or 0), reverse=True)
    return out


def qualify_csv(
    *,
    input_path: Path,
    output_path: Path,
    icp_prompt: str,
    product_prompt: str,
    config: QualifyConfig,
    llm_call: Callable[[dict[str, object]], dict[str, object]],
    preserve_order: bool = True,
    limit: int | None = None,
) -> None:
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if limit is not None:
        rows = rows[: max(0, limit)]

    out_rows = qualify_rows(
        rows,
        icp_prompt=icp_prompt,
        product_prompt=product_prompt,
        config=config,
        llm_call=llm_call,
    )
    if preserve_order:
        indexed = {_stable_lead_key(r): r for r in out_rows}
        out_rows = [indexed.get(_stable_lead_key(r), r) for r in rows]

    if not out_rows:
        output_path.write_text("", encoding="utf-8")
        return
    with output_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Qualify leads for IG DM outreach")
    p.add_argument("--input", required=True, type=Path, dest="input_path")
    p.add_argument("--output", required=True, type=Path, dest="output_path")
    p.add_argument("--icp", required=True, help="ICP prompt text, or @path/to/file.txt")
    p.add_argument("--product", required=True, help="Product prompt text, or @path/to/file.txt")
    p.add_argument("--model", default="gpt-5-mini")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--sort", action="store_true", help="Sort rows by fit score (default: preserve input order).")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required (or inject your own llm_call in code).")

    config = QualifyConfig(
        model=args.model,
        cache_path=None if args.no_cache else Path("qualify.cache.jsonl"),
    )

    icp = _read_text_arg(args.icp)
    product = _read_text_arg(args.product)

    def llm_call(payload: dict[str, object]) -> dict[str, object]:
        return _openai_chat_completions_json(
            api_key=api_key,
            model=config.model,
            payload=payload,
            timeout_s=config.timeout_s,
        )

    qualify_csv(
        input_path=args.input_path,
        output_path=args.output_path,
        icp_prompt=icp,
        product_prompt=product,
        config=config,
        llm_call=llm_call,
        preserve_order=not args.sort,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

