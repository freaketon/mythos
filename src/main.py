from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.adapters.instagram import find_instagram_profile
from src.adapters.youtube import YouTubeSearchConfig, find_best_youtube_channel
from src.csv_pipeline import copy_csv_rows
from src.env import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Contact enrichment skill")
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--output", required=True, type=Path, dest="output_path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail fast on validation errors instead of skipping invalid rows.",
    )
    parser.add_argument(
        "--youtube",
        action="store_true",
        help="Enable YouTube enrichment via scrapetube.",
    )
    parser.add_argument(
        "--instagram",
        action="store_true",
        help="Enable Instagram enrichment via instaloader.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows processed (data rows only).",
    )
    parser.add_argument(
        "--low-confidence-report",
        type=Path,
        default=None,
        help="Write a CSV report of low-confidence YouTube matches.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Flush output files every N processed rows to reduce progress loss on crash.",
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        default=Path("run.events.jsonl"),
        help="Write row-level hit/no-hit events as JSONL for UI streaming.",
    )
    parser.add_argument(
        "--llm-rerank",
        action="store_true",
        help="Use an LLM to rerank ambiguous YouTube candidates (requires OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI model name for reranking (default: gpt-4o-mini).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = build_parser()
    args = parser.parse_args(argv)
    youtube_lookup = None
    if args.youtube:
        yt_config = YouTubeSearchConfig(llm_rerank=args.llm_rerank, llm_model=args.llm_model)
        youtube_lookup = lambda queries: find_best_youtube_channel(queries, config=yt_config)  # noqa: E731
    instagram_lookup = find_instagram_profile if args.instagram else None
    copy_csv_rows(
        args.input_path,
        args.output_path,
        strict=args.strict,
        youtube_lookup=youtube_lookup,
        instagram_lookup=instagram_lookup,
        row_limit=args.limit,
        low_confidence_report_path=args.low_confidence_report,
        checkpoint_every=args.checkpoint_every,
        events_path=args.events_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
