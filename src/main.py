from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.adapters.youtube import find_best_youtube_channel
from src.csv_pipeline import copy_csv_rows


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
    return parser


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    youtube_lookup = find_best_youtube_channel if args.youtube else None
    copy_csv_rows(
        args.input_path,
        args.output_path,
        strict=args.strict,
        youtube_lookup=youtube_lookup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
