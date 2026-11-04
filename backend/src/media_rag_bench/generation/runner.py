"""Run selected movie cases and preserve progress without depending on the CLI."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
from time import perf_counter

from .openai import GenerationError, GenerationResult, movie_instructions
from ..schemas import MovieEvaluationCase


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def run_movie_benchmark(
    cases: Sequence[MovieEvaluationCase],
    *,
    generate: Callable[[MovieEvaluationCase], GenerationResult],
    output_dir: Path,
    cases_file: dict[str, str],
    model: str,
    max_output_tokens: int,
) -> dict:
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Benchmark cases must be nonempty and have unique IDs.")
    if any(case.recommendation_count > 10 for case in cases):
        raise ValueError("Each benchmark case supports at most 10 movies.")
    output_dir.mkdir(parents=True, exist_ok=False)
    responses = {}
    run = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "status": "running",
        "provider": "openai",
        "method": "direct",
        "cases_file": cases_file,
        "cases": [case.model_dump(mode="json") for case in cases],
        "requested_model": model,
        "max_output_tokens": max_output_tokens,
        "success_count": 0,
        "error_count": 0,
        "case_results": {},
    }

    def save_progress() -> None:
        _write_json(output_dir / "responses.json", responses)
        _write_json(output_dir / "run.json", run)

    save_progress()
    try:
        for case in cases:
            started = perf_counter()
            metadata = {
                "instructions": movie_instructions(case.recommendation_count),
                "model": None,
                "input_tokens": None,
                "output_tokens": None,
            }
            try:
                result = generate(case)
            except GenerationError as exc:
                responses[case.case_id] = {"error": str(exc)}
                metadata.update(status="error", error=str(exc), latency_seconds=perf_counter() - started)
                run["error_count"] += 1
            else:
                responses[case.case_id] = result.response.model_dump(mode="json")
                metadata.update(
                    status="success",
                    model=result.model,
                    latency_seconds=result.latency_seconds,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                run["success_count"] += 1
            run["case_results"][case.case_id] = metadata
            save_progress()
    except KeyboardInterrupt:
        run["status"] = "interrupted"
        run["finished_at"] = datetime.now(UTC).isoformat()
        save_progress()
        raise
    run["status"] = "completed"
    run["finished_at"] = datetime.now(UTC).isoformat()
    save_progress()
    return run
