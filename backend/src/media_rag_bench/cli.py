"""Root-level dataset commands; no API server or LLM required."""

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx
from dotenv import load_dotenv
from pydantic import TypeAdapter

from .datasets.snapshots import load_movie_snapshot, save_movie_snapshot, snapshot_path
from .datasets.tmdb import TmdbError, fetch_movies
from .evaluation.movies import MovieScorer
from .evaluation.runner import run_evaluation
from .schemas import MovieEvaluationCase


def _movie_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be an integer") from None
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return limit


def _ingest_movies(args: argparse.Namespace) -> None:
    destination = snapshot_path(args.output_dir, args.dataset_version)
    if destination.exists():
        raise FileExistsError(f"Snapshot already exists: {destination}. Choose a new version.")
    token = os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("Set TMDB_READ_ACCESS_TOKEN in your shell or local .env file.")
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
    print(f"Saved {len(records)} movies to {path}")


def _evaluate_movies(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise FileExistsError(f"Report already exists: {args.output}. Choose a new output path.")
    if args.output.resolve() in {path.resolve() for path in (args.snapshot, args.cases, args.responses)}:
        raise ValueError("Report output must differ from the input files.")
    snapshot = load_movie_snapshot(args.snapshot)
    case_bytes = args.cases.read_bytes()
    response_bytes = args.responses.read_bytes()
    cases = TypeAdapter(list[MovieEvaluationCase]).validate_json(case_bytes)
    responses = json.loads(response_bytes)
    if not isinstance(responses, dict):
        raise ValueError("Responses must be a JSON object keyed by case ID.")
    report = {
        "schema_version": 1,
        "evaluator_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "method": args.method,
        "inputs": {
            "snapshot": {
                "path": str(args.snapshot),
                "dataset_version": snapshot.dataset_version,
                "source": snapshot.source,
                "records_sha256": snapshot.records_sha256,
            },
            "cases": {"path": str(args.cases), "sha256": hashlib.sha256(case_bytes).hexdigest()},
            "responses": {"path": str(args.responses), "sha256": hashlib.sha256(response_bytes).hexdigest()},
        },
        **run_evaluation(cases, responses, MovieScorer(snapshot.records, args.method)),
    }
    contents = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)
    print(f"Evaluated {len(cases)} cases; saved report to {args.output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-rag-bench")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest-movies", help="Save a versioned TMDB movie catalog")
    ingest.add_argument("--dataset-version", required=True)
    ingest.add_argument("--limit", type=_movie_limit, default=500)
    ingest.add_argument("--language", default="en-US")
    ingest.add_argument("--output-dir", type=Path, default=Path("data/movies"))
    evaluate = commands.add_parser("evaluate-movies", help="Score saved responses against a movie snapshot")
    evaluate.add_argument("--snapshot", type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--responses", type=Path, required=True)
    evaluate.add_argument("--method", choices=("direct", "rag"), required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False, encoding="utf-8-sig")
        if args.command == "ingest-movies":
            _ingest_movies(args)
        else:
            _evaluate_movies(args)
    except (TmdbError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
