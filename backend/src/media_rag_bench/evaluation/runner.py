"""Evaluate saved responses without model calls or domain-specific knowledge."""

from collections import Counter
from collections.abc import Callable, Sequence
from typing import TypeVar

from pydantic import ValidationError

from media_rag_bench.schemas import EvaluationCase, RecommendationResponse

Case = TypeVar("Case", bound=EvaluationCase)
CHECK_STATUSES = ("pass", "fail", "unknown", "not_applicable")
RESPONSE_STATUSES = ("valid", "invalid", "missing", "error")
MATCH_STATUSES = ("matched", "ambiguous", "out_of_catalog", "identity_conflict")


def run_evaluation(
    cases: Sequence[Case],
    responses: dict[str, object],
    scorer: Callable[[Case, RecommendationResponse], dict],
) -> dict:
    case_ids = {case.case_id for case in cases}
    if not cases or len(case_ids) != len(cases):
        raise ValueError("Evaluation cases must be nonempty and have unique IDs.")
    if responses.keys() - case_ids:
        raise ValueError("Response file contains unknown case IDs.")

    results = []
    for case in cases:
        result = {
            "case": case.model_dump(mode="json"),
            "response_status": "missing",
            "errors": [],
            "checks": {"recommendation_count": "unknown", "unique_recommendations": "unknown"},
            "recommendations": [],
        }
        if case.case_id not in responses:
            result["errors"] = [{"message": "No saved response for this case."}]
        else:
            raw = responses[case.case_id]
            if isinstance(raw, dict) and set(raw) == {"error"} and isinstance(raw["error"], str):
                result["response_status"] = "error"
                result["errors"] = [{"message": raw["error"]}]
            else:
                try:
                    response = (
                        RecommendationResponse.model_validate_json(raw)
                        if isinstance(raw, str)
                        else RecommendationResponse.model_validate(raw)
                    )
                except ValidationError as exc:
                    result["response_status"] = "invalid"
                    result["errors"] = exc.errors(include_input=False, include_url=False)
                else:
                    if response.domain != case.domain:
                        result["response_status"] = "invalid"
                        result["errors"] = [{"message": "Response domain does not match the case."}]
                    else:
                        result["response_status"] = "valid"
                        result.update(scorer(case, response))
        results.append(result)

    response_counts = Counter({status: 0 for status in RESPONSE_STATUSES})
    identity_counts = Counter({status: 0 for status in MATCH_STATUSES})
    check_counts = {}
    for result in results:
        response_counts[result["response_status"]] += 1
        checks = list(result["checks"].items())
        for recommendation in result["recommendations"]:
            identity_counts[recommendation["match"]["status"]] += 1
            checks.extend(recommendation["checks"].items())
        for name, status in checks:
            counts = check_counts.setdefault(name, {key: 0 for key in CHECK_STATUSES})
            counts[status] += 1
    return {
        "summary": {
            "case_count": len(cases),
            "response_status_counts": dict(response_counts),
            "identity_counts": dict(identity_counts),
            "check_counts": check_counts,
        },
        "cases": results,
    }
