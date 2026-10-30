import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from media_rag_bench.schemas import (
    MovieConstraints,
    MovieEvaluationCase,
    MovieRecord,
    RecommendationResponse,
    RecordSource,
)

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def test_movie_fixtures_retain_identity_and_provenance():
    records = [
        MovieRecord.model_validate(item)
        for item in json.loads((FIXTURES / "movies.json").read_text(encoding="utf-8"))
    ]
    assert len({record.catalog_id for record in records}) == 2
    for record in records:
        assert isinstance(record.provenance, RecordSource)
        assert record.provenance.source == "synthetic-fixture"
        assert record.provenance.dataset_version == "synthetic-v1"
        assert MovieRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("method", ["direct", "rag"])
def test_direct_and_rag_use_the_same_response_contract(method):
    responses = json.loads((FIXTURES / "responses.json").read_text(encoding="utf-8"))
    response = RecommendationResponse.model_validate(responses[method])
    recommendation = response.recommendations[0]
    if method == "direct":
        assert recommendation.catalog_id is None
        assert recommendation.evidence_ids == []
    else:
        assert recommendation.catalog_id == "fixture:movie:1"
        assert recommendation.evidence_ids == ["fixture:movie:1"]


@pytest.mark.parametrize(
    "payload",
    [
        {"domain": "movies", "recommendations": []},
        {"domain": "movies", "recommendations": [{"title": "  ", "explanation": "Reason"}]},
        {"domain": "movies", "recommendations": [{"title": "Title"}]},
        {
            "domain": "movies",
            "recommendations": [{"title": "Title", "explanation": "Reason", "invented": True}],
        },
    ],
)
def test_malformed_recommendation_responses_are_rejected(payload):
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(payload)


def test_provenance_requires_a_timezone_but_movie_metadata_can_be_missing():
    payload = json.loads((FIXTURES / "movies.json").read_text(encoding="utf-8"))[0]
    payload.pop("release_date")
    payload.pop("description")
    record = MovieRecord.model_validate(payload)
    assert record.release_date is None
    assert record.description is None

    payload["provenance"]["retrieved_at"] = "2026-10-30T00:00:00"
    with pytest.raises(ValidationError):
        MovieRecord.model_validate(payload)


def test_sample_cases_validate_and_reject_reversed_year_bounds():
    payload = json.loads(
        (ROOT / "benchmarks/cases/movies.sample.json").read_text(encoding="utf-8")
    )
    cases = [MovieEvaluationCase.model_validate(item) for item in payload]
    assert len({case.case_id for case in cases}) == 3
    assert cases[0].constraints.genres_all == ["Science Fiction"]
    assert cases[1].constraints.release_year_max == 1999
    assert cases[2].recommendation_count == 2

    with pytest.raises(ValidationError, match="release_year_min"):
        MovieConstraints(release_year_min=2010, release_year_max=2000)
