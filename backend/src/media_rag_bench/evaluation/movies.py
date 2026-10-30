"""Conservative catalog matching and objective movie checks."""

from collections import defaultdict
from typing import Literal
import unicodedata

from media_rag_bench.schemas import (
    MovieEvaluationCase,
    MovieRecord,
    Recommendation,
    RecommendationResponse,
)


def normalized_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class MovieScorer:
    def __init__(self, records: list[MovieRecord], method: Literal["direct", "rag"]):
        if method not in ("direct", "rag"):
            raise ValueError("Evaluation method must be direct or rag.")
        self.method = method
        self.by_id = {record.catalog_id: record for record in records}
        self.by_title = defaultdict(list)
        for record in records:
            self.by_title[normalized_text(record.title)].append(record)

    def _match(self, recommendation: Recommendation) -> tuple[dict, MovieRecord | None]:
        record = None
        candidates = []
        if recommendation.catalog_id is not None:
            record = self.by_id.get(recommendation.catalog_id)
            if record is None:
                status = "out_of_catalog"
            elif normalized_text(record.title) != normalized_text(recommendation.title):
                status = "identity_conflict"
                candidates = [record]
                record = None
            else:
                status = "matched"
        else:
            candidates = self.by_title.get(normalized_text(recommendation.title), [])
            if recommendation.release_year is not None:
                candidates = [
                    item for item in candidates
                    if item.release_date is None or item.release_date.year == recommendation.release_year
                ]
            if len(candidates) == 1:
                status, record = "matched", candidates[0]
            else:
                status = "ambiguous" if candidates else "out_of_catalog"
        return {
            "status": status,
            "catalog_id": record.catalog_id if record else None,
            "candidate_ids": [item.catalog_id for item in candidates] if record is None else [],
        }, record

    def _checks(
        self, case: MovieEvaluationCase, recommendation: Recommendation, record: MovieRecord | None
    ) -> dict[str, str]:
        constraints = case.constraints
        checks = {
            "release_year_constraint": "not_applicable",
            "genres_constraint": "not_applicable",
            "stated_release_year": "not_applicable",
            "evidence_ids": "not_applicable",
        }
        if constraints.release_year_min is not None or constraints.release_year_max is not None:
            checks["release_year_constraint"] = "unknown"
            if record is not None and record.release_date is not None:
                year = record.release_date.year
                passed = (
                    (constraints.release_year_min is None or year >= constraints.release_year_min)
                    and (constraints.release_year_max is None or year <= constraints.release_year_max)
                )
                checks["release_year_constraint"] = "pass" if passed else "fail"
        if constraints.genres_all:
            checks["genres_constraint"] = "unknown"
            if record is not None and record.genres:
                expected = {normalized_text(genre) for genre in constraints.genres_all}
                actual = {normalized_text(genre) for genre in record.genres}
                checks["genres_constraint"] = "pass" if expected <= actual else "fail"
        if recommendation.release_year is not None:
            checks["stated_release_year"] = "unknown"
            if record is not None and record.release_date is not None:
                checks["stated_release_year"] = (
                    "pass" if recommendation.release_year == record.release_date.year else "fail"
                )
        if self.method == "rag":
            if not recommendation.evidence_ids or any(
                evidence_id not in self.by_id for evidence_id in recommendation.evidence_ids
            ):
                checks["evidence_ids"] = "fail"
            elif record is None:
                checks["evidence_ids"] = "unknown"
            else:
                checks["evidence_ids"] = (
                    "pass" if record.catalog_id in recommendation.evidence_ids else "fail"
                )
        return checks

    def __call__(self, case: MovieEvaluationCase, response: RecommendationResponse) -> dict:
        results = []
        identities = []
        for recommendation in response.recommendations:
            match, record = self._match(recommendation)
            identities.append(
                record.catalog_id if record else recommendation.catalog_id
                or (normalized_text(recommendation.title), recommendation.release_year)
            )
            results.append({
                "recommendation": recommendation.model_dump(mode="json"),
                "match": match,
                "checks": self._checks(case, recommendation, record),
            })
        return {
            "checks": {
                "recommendation_count": (
                    "pass" if len(results) == case.recommendation_count else "fail"
                ),
                "unique_recommendations": "pass" if len(set(identities)) == len(identities) else "fail",
            },
            "recommendations": results,
        }
