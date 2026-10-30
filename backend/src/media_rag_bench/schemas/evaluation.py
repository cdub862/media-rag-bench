"""Movie evaluation inputs; scoring is implemented in a later phase."""

from typing import Literal, Self

from pydantic import Field, model_validator

from .common import Contract, NonEmptyText


class MovieConstraints(Contract):
    release_year_min: int | None = Field(default=None, ge=1, le=9999)
    release_year_max: int | None = Field(default=None, ge=1, le=9999)
    genres_all: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        if (
            self.release_year_min is not None
            and self.release_year_max is not None
            and self.release_year_min > self.release_year_max
        ):
            raise ValueError("release_year_min must not exceed release_year_max")
        return self


class MovieEvaluationCase(Contract):
    schema_version: Literal[1] = 1
    case_id: NonEmptyText
    domain: Literal["movies"] = "movies"
    prompt: NonEmptyText
    recommendation_count: int = Field(ge=1)
    constraints: MovieConstraints = Field(default_factory=MovieConstraints)
    human_review: bool = False
