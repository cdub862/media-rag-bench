from copy import deepcopy
from datetime import date
import json
from pathlib import Path

from pydantic import TypeAdapter
import pytest

from media_rag_bench.cli import main
from media_rag_bench.datasets.snapshots import load_movie_snapshot, records_checksum
from media_rag_bench.evaluation.movies import MovieScorer
from media_rag_bench.evaluation.runner import run_evaluation
from media_rag_bench.schemas import MovieEvaluationCase, RecommendationResponse

FIXTURES = Path(__file__).parent / "fixtures"
CASES_PATH = Path(__file__).resolve().parents[2] / "benchmarks/cases/movies.sample.json"


def inputs():
    snapshot = load_movie_snapshot(FIXTURES / "movie_snapshot.json")
    cases = TypeAdapter(list[MovieEvaluationCase]).validate_json(CASES_PATH.read_bytes())
    responses = json.loads((FIXTURES / "evaluation_responses.json").read_bytes())
    return snapshot, cases, responses


def test_evaluation_cli_writes_a_traceable_report_without_overwriting(tmp_path, capsys):
    output = tmp_path / "report.json"
    args = [
        "evaluate-movies", "--snapshot", str(FIXTURES / "movie_snapshot.json"),
        "--cases", str(CASES_PATH), "--responses", str(FIXTURES / "evaluation_responses.json"),
        "--method", "rag", "--output", str(output),
    ]
    assert main(args) == 0
    report = json.loads(output.read_bytes())
    assert report["inputs"]["snapshot"]["dataset_version"] == "synthetic-v1"
    assert len(report["inputs"]["cases"]["sha256"]) == 64
    assert report["summary"]["case_count"] == 3
    assert report["summary"]["response_status_counts"]["valid"] == 3
    assert report["summary"]["identity_counts"]["matched"] == 4
    assert report["summary"]["check_counts"]["recommendation_count"]["pass"] == 3
    assert report["summary"]["check_counts"]["evidence_ids"]["pass"] == 4
    assert report["cases"][0]["case"]["human_review"] is True
    original = output.read_bytes()
    assert main(args) == 1
    assert "already exists" in capsys.readouterr().err
    assert output.read_bytes() == original


@pytest.mark.parametrize("corruption", ["checksum", "count", "duplicates", "source", "schema"])
def test_snapshot_loader_rejects_corruption(corruption, tmp_path):
    payload = json.loads((FIXTURES / "movie_snapshot.json").read_bytes())
    if corruption == "checksum":
        payload["records"][0]["title"] = "Changed after snapshot creation"
    elif corruption == "count":
        payload["record_count"] += 1
    elif corruption == "duplicates":
        payload["records"][1] = deepcopy(payload["records"][0])
        payload["records_sha256"] = records_checksum(payload["records"])
    elif corruption == "source":
        payload["dataset_version"] = "wrong-version"
    else:
        payload["schema_version"] = 2
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_movie_snapshot(path)


def test_matching_preserves_ambiguity_out_of_catalog_and_identity_conflicts():
    snapshot, cases, responses = inputs()
    original = snapshot.records[0]
    remake = original.model_copy(update={"catalog_id": "fixture:remake", "release_date": date(1990, 1, 1)})
    scorer = MovieScorer([*snapshot.records, remake], "direct")
    base = responses[cases[0].case_id]["recommendations"][0]
    proposals = [
        {**base, "catalog_id": None, "release_year": None},
        {**base, "catalog_id": None, "title": "  THE QUIET OBSERVATORY  "},
        {**base, "catalog_id": None, "release_year": 2020},
        {**base, "catalog_id": "fixture:movie:2"},
    ]
    response = RecommendationResponse(domain="movies", recommendations=proposals)
    report = run_evaluation(cases[:1], {cases[0].case_id: response.model_dump()}, scorer)
    results = report["cases"][0]["recommendations"]
    assert [item["match"]["status"] for item in results] == [
        "ambiguous", "matched", "out_of_catalog", "identity_conflict",
    ]
    assert len(results[0]["match"]["candidate_ids"]) == 2
    assert results[2]["checks"]["release_year_constraint"] == "unknown"
    assert results[2]["checks"]["genres_constraint"] == "unknown"
    assert results[2]["checks"]["evidence_ids"] == "not_applicable"
    assert report["summary"]["check_counts"]["recommendation_count"]["fail"] == 1


def test_objective_checks_catch_wrong_facts_duplicates_and_missing_evidence():
    snapshot, cases, responses = inputs()
    base = responses[cases[0].case_id]["recommendations"][0]
    wrong = {**base, "release_year": 1995, "evidence_ids": []}
    case = cases[1].model_copy(update={"recommendation_count": 2})
    response = RecommendationResponse(domain="movies", recommendations=[wrong, wrong])
    result = MovieScorer(snapshot.records, "rag")(case, response)
    assert result["checks"] == {"recommendation_count": "pass", "unique_recommendations": "fail"}
    assert all(status == "fail" for status in result["recommendations"][0]["checks"].values())

    unknown = snapshot.records[0].model_copy(update={"release_date": None, "genres": []})
    result = MovieScorer([unknown], "rag")(cases[0], response)
    assert result["recommendations"][0]["checks"]["release_year_constraint"] == "unknown"
    assert result["recommendations"][0]["checks"]["genres_constraint"] == "unknown"


@pytest.mark.parametrize("evidence", [["fixture:movie:2"], ["unknown-id"]])
def test_rag_rejects_wrong_or_unknown_evidence_ids(evidence):
    snapshot, cases, responses = inputs()
    raw = responses[cases[0].case_id]
    raw["recommendations"][0]["evidence_ids"] = evidence
    response = RecommendationResponse.model_validate(raw)
    result = MovieScorer(snapshot.records, "rag")(cases[0], response)
    assert result["recommendations"][0]["checks"]["evidence_ids"] == "fail"


def test_runner_reports_invalid_missing_and_failed_calls_and_refuses_misaligned_inputs():
    snapshot, cases, responses = inputs()
    scorer = MovieScorer(snapshot.records, "direct")
    responses = {cases[0].case_id: "malformed JSON", cases[1].case_id: {"error": "Model unavailable"}}
    report = run_evaluation(cases, responses, scorer)
    assert report["summary"]["response_status_counts"] == {
        "valid": 0, "invalid": 1, "missing": 1, "error": 1,
    }
    assert report["summary"]["check_counts"]["recommendation_count"]["unknown"] == 3
    with pytest.raises(ValueError, match="unique IDs"):
        run_evaluation([cases[0], cases[0]], {}, scorer)
    with pytest.raises(ValueError, match="unknown case IDs"):
        run_evaluation(cases, {"typo-case": {}}, scorer)

    wrong_domain = {cases[0].case_id: {"domain": "games", "recommendations": [
        {"title": "A game", "explanation": "Wrong domain"},
    ]}}
    report = run_evaluation(cases[:1], wrong_domain, scorer)
    assert report["summary"]["response_status_counts"]["invalid"] == 1
