"""Validated catalog, recommendation, and evaluation contracts."""

from .catalog import CatalogRecord, MovieRecord, MovieSnapshot, RecordSource
from .evaluation import EvaluationCase, MovieConstraints, MovieEvaluationCase
from .recommendations import Recommendation, RecommendationResponse

__all__ = [
    "CatalogRecord",
    "EvaluationCase",
    "MovieConstraints",
    "MovieEvaluationCase",
    "MovieRecord",
    "MovieSnapshot",
    "Recommendation",
    "RecommendationResponse",
    "RecordSource",
]
