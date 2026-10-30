"""One semantic response contract for direct and RAG recommendations."""

from pydantic import Field

from .common import Contract, Domain, NonEmptyText


class Recommendation(Contract):
    title: NonEmptyText
    explanation: NonEmptyText
    catalog_id: NonEmptyText | None = None
    release_year: int | None = Field(default=None, ge=1, le=9999)
    evidence_ids: list[NonEmptyText] = Field(default_factory=list)


class RecommendationResponse(Contract):
    domain: Domain
    recommendations: list[Recommendation] = Field(min_length=1)
