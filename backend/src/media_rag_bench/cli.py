"""Root-level dataset, evaluation, and readable recommendation commands."""

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from shutil import get_terminal_size
import sys
from textwrap import fill

import httpx
from dotenv import load_dotenv
from pydantic import TypeAdapter

from .datasets.snapshots import load_movie_snapshot, save_movie_snapshot, snapshot_path
from .datasets.tmdb import TmdbError, fetch_movies
from .evaluation.movies import MovieScorer
from .evaluation.runner import run_evaluation
from .generation.openai import GenerationError, generate_movies, movie_instructions
from .generation.runner import run_movie_benchmark
from .schemas import MovieEvaluationCase


def _movie_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("limit must be an integer") from None
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return limit


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _recommend_movies(args: argparse.Namespace) -> None:
    if (args.prompt is None) == (args.case_id is None):
        raise ValueError("Provide either a quoted movie request or --case CASE_ID.")
    if args.output is not None:
        if args.case_id is None:
            raise ValueError("--output requires --case CASE_ID so the response can be evaluated.")
        if args.dry_run:
            raise ValueError("--output cannot be used with --dry-run.")
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError(f"Run directory already exists: {args.output}. Choose a new output path.")
    case = None
    if args.case_id is not None:
        if args.count is not None:
            raise ValueError("--case uses the case's recommendation count; omit --count.")
        case_bytes = args.cases.read_bytes()
        cases = TypeAdapter(list[MovieEvaluationCase]).validate_json(case_bytes)
        matches = [case for case in cases if case.case_id == args.case_id]
        if len(matches) != 1:
            raise ValueError("Case ID must identify exactly one movie case in --cases.")
        case = matches[0]
        prompt, count = case.prompt, case.recommendation_count
    else:
        prompt, count = args.prompt.strip(), args.count or 3
    if not prompt:
        raise ValueError("Movie request must not be blank.")
    if count > 10:
        raise ValueError("A single recommendation request supports at most 10 movies.")
    model = (args.model or os.environ.get("OPENAI_MODEL", "")).strip()
    print("LLM prompt\n")
    print(f"Instructions:\n{movie_instructions(count)}\n")
    print(f"User request:\n{prompt}\n", flush=True)
    if args.dry_run:
        print("Dry run: no API request sent.")
        return
    if not model:
        raise ValueError("Set OPENAI_MODEL or pass --model with a model that supports Structured Outputs.")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("Set OPENAI_API_KEY in your shell or local .env file.")
    print(f"Calling OpenAI: {model} (direct, no retrieval)...", flush=True)
    with httpx.Client(
        headers={"Authorization": f"Bearer {key}"}, timeout=60.0
    ) as client:
        result = generate_movies(
            client, prompt=prompt, count=count, model=model, max_output_tokens=args.max_output_tokens
        )
    if args.output is not None and case is not None:
        responses = {case.case_id: result.response.model_dump(mode="json")}
        metadata = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "provider": "openai",
            "method": "direct",
            "case": case.model_dump(mode="json"),
            "cases_file": {"path": str(args.cases), "sha256": hashlib.sha256(case_bytes).hexdigest()},
            "instructions": movie_instructions(count),
            "requested_model": model,
            "model": result.model,
            "max_output_tokens": args.max_output_tokens,
            "latency_seconds": result.latency_seconds,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
        args.output.mkdir(parents=True, exist_ok=False)
        for name, payload in (("responses.json", responses), ("run.json", metadata)):
            with (args.output / name).open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(f"Saved response and run metadata to {args.output}")
    print("\nMovie recommendations\n")
    width = max(40, min(get_terminal_size(fallback=(100, 24)).columns, 120))
    for index, movie in enumerate(result.response.recommendations, start=1):
        year = str(movie.release_year) if movie.release_year is not None else "year unknown"
        print(fill(f"{index}. {movie.title} ({year})", width=width, subsequent_indent="   "))
        print(fill(movie.explanation, width=width, initial_indent="   ", subsequent_indent="   "))
        print()
    input_tokens = result.input_tokens if result.input_tokens is not None else "unavailable"
    output_tokens = result.output_tokens if result.output_tokens is not None else "unavailable"
    print(f"Model: {result.model} | Request latency: {result.latency_seconds:.2f}s")
    print(f"Tokens: input {input_tokens}, output {output_tokens}")


def _benchmark_movies(args: argparse.Namespace) -> int:
    case_bytes = args.cases.read_bytes()
    cases = TypeAdapter(list[MovieEvaluationCase]).validate_json(case_bytes)
    by_id = {case.case_id: case for case in cases}
    if not cases or len(by_id) != len(cases):
        raise ValueError("Case file must be nonempty and have unique case IDs.")
    if len(set(args.case_ids)) != len(args.case_ids):
        raise ValueError("Select each --case at most once.")
    if set(args.case_ids) - by_id.keys():
        raise ValueError("Every --case must identify a movie case in --cases.")
    selected = [by_id[case_id] for case_id in args.case_ids]
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"Run directory already exists: {args.output}. Choose a new output path.")
    model = (args.model or os.environ.get("OPENAI_MODEL", "")).strip()
    if not model:
        raise ValueError("Set OPENAI_MODEL or pass --model with a model that supports Structured Outputs.")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("Set OPENAI_API_KEY in your shell or local .env file.")
    print(f"Running {len(selected)} movie cases with {model} (direct, no retrieval)...", flush=True)
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as client:
        def generate(case: MovieEvaluationCase):
            print(f"Case {case.case_id}...", flush=True)
            return generate_movies(
                client, prompt=case.prompt, count=case.recommendation_count,
                model=model, max_output_tokens=args.max_output_tokens,
            )

        try:
            run = run_movie_benchmark(
                selected, generate=generate, output_dir=args.output,
                cases_file={"path": str(args.cases), "sha256": hashlib.sha256(case_bytes).hexdigest()},
                model=model, max_output_tokens=args.max_output_tokens,
            )
        except KeyboardInterrupt:
            print(f"Benchmark interrupted; completed results remain in {args.output}.", file=sys.stderr)
            return 130
    print(f"Completed: {run['success_count']} succeeded, {run['error_count']} failed. Saved to {args.output}")
    return 1 if run["error_count"] else 0


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
    recommend = commands.add_parser("recommend", help="Show an LLM prompt and readable recommendations")
    recommend.add_argument("domain", choices=("movies",), help="Movies first; games and albums follow later")
    recommend.add_argument("prompt", nargs="?", help="Your quoted movie request")
    recommend.add_argument("--case", dest="case_id", help="Use a versioned evaluation case instead of a request")
    recommend.add_argument("--cases", type=Path, default=Path("benchmarks/cases/movies.v1.json"))
    recommend.add_argument("--count", type=_positive_integer, help="Number of movies, 1-10; default 3 for custom requests")
    recommend.add_argument("--model", help="OpenAI model ID; defaults to OPENAI_MODEL")
    recommend.add_argument("--max-output-tokens", type=_positive_integer, default=4096)
    recommend.add_argument("--dry-run", action="store_true", help="Print the prompt without calling a model")
    recommend.add_argument("--output", type=Path, help="Save a --case response and metadata in a new run directory")
    benchmark = commands.add_parser("benchmark", help="Run selected movie cases and save each result")
    benchmark.add_argument("domain", choices=("movies",))
    benchmark.add_argument("--case", dest="case_ids", action="append", required=True, help="Case ID to run; repeat to select more cases in order")
    benchmark.add_argument("--cases", type=Path, default=Path("benchmarks/cases/movies.v1.json"))
    benchmark.add_argument("--output", type=Path, required=True, help="New run directory for responses and metadata")
    benchmark.add_argument("--model", help="OpenAI model ID; defaults to OPENAI_MODEL")
    benchmark.add_argument("--max-output-tokens", type=_positive_integer, default=4096)
    args = parser.parse_args(argv)
    try:
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False, encoding="utf-8-sig")
        if args.command == "ingest-movies":
            _ingest_movies(args)
        elif args.command == "evaluate-movies":
            _evaluate_movies(args)
        elif args.command == "benchmark":
            return _benchmark_movies(args)
        else:
            _recommend_movies(args)
    except (TmdbError, GenerationError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
