"""Small shared types for the benchmark contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Domain = Literal["movies", "music", "games"]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
