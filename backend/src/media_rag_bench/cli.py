"""Root-level dataset commands; no API server or LLM required."""

import argparse
import os
from pathlib import Path
import sys

import httpx

from .datasets.snapshots import save_movie_snapshot, snapshot_path
from .datasets.tmdb import TmdbError, fetch_movies


def _movie_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be an integer") from None
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return limit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-rag-bench")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest-movies", help="Save a versioned TMDB movie catalog")
    ingest.add_argument("--dataset-version", required=True)
    ingest.add_argument("--limit", type=_movie_limit, default=500)
    ingest.add_argument("--language", default="en-US")
    ingest.add_argument("--output-dir", type=Path, default=Path("data/movies"))
    args = parser.parse_args(argv)

    try:
        destination = snapshot_path(args.output_dir, args.dataset_version)
        if destination.exists():
            raise FileExistsError(f"Snapshot already exists: {destination}. Choose a new version.")
        token = os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
        if not token:
            raise ValueError("Set TMDB_READ_ACCESS_TOKEN or use uv run --env-file .env.")
        print(f"Fetching {args.limit} movies from TMDB...", flush=True)
        with httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20.0,
        ) as client:
            records = fetch_movies(
                client,
                dataset_version=args.dataset_version,
                limit=args.limit,
                language=args.language,
            )
        path = save_movie_snapshot(
            records,
            output_dir=args.output_dir,
            dataset_version=args.dataset_version,
            requested_count=args.limit,
            language=args.language,
        )
    except (TmdbError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(records)} movies to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
