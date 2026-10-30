"""Sequential TMDB discovery and movie-detail normalization."""

from datetime import UTC, date, datetime
from time import sleep
from typing import Annotated

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from media_rag_bench.schemas import MovieRecord, RecordSource
from media_rag_bench.schemas.common import NonEmptyText

API_ROOT = "https://api.themoviedb.org/3"
PositiveID = Annotated[int, Field(strict=True, gt=0)]


class TmdbError(RuntimeError):
    """An actionable ingestion failure without credentials or response bodies."""


class _MovieID(BaseModel):
    id: PositiveID


class _DiscoverPage(BaseModel):
    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    results: list[_MovieID]


class _NamedItem(BaseModel):
    name: NonEmptyText


class _Keywords(BaseModel):
    keywords: list[_NamedItem] = Field(default_factory=list)


class _MovieDetails(BaseModel):
    id: PositiveID
    title: NonEmptyText
    overview: str | None = None
    release_date: date | None = None
    genres: list[_NamedItem] = Field(default_factory=list)
    keywords: _Keywords = Field(default_factory=_Keywords)

    @field_validator("release_date", mode="before")
    @classmethod
    def empty_date_is_unknown(cls, value):
        return None if value == "" else value


def discovery_parameters(language: str) -> dict[str, str]:
    return {
        "language": language,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "include_video": "false",
    }


def _get_json(client: httpx.Client, path: str, params: dict) -> dict:
    # At most four sequential requests per second, before network latency.
    sleep(0.25)
    try:
        response = client.get(f"{API_ROOT}{path}", params=params)
    except httpx.RequestError:
        raise TmdbError("Could not reach TMDB. Check your connection and retry.") from None
    if response.status_code in (401, 403):
        raise TmdbError("TMDB authentication failed. Check TMDB_READ_ACCESS_TOKEN.")
    if response.status_code == 429:
        raise TmdbError("TMDB rate limit reached (HTTP 429). Wait before retrying.")
    if response.is_error or response.is_redirect:
        raise TmdbError(f"TMDB request failed (HTTP {response.status_code}).")
    try:
        payload = response.json()
    except ValueError:
        raise TmdbError("TMDB returned invalid JSON.") from None
    if not isinstance(payload, dict):
        raise TmdbError("TMDB returned an unexpected response shape.")
    return payload


def normalize_movie(
    payload: dict, *, dataset_version: str, retrieved_at: datetime
) -> MovieRecord:
    try:
        movie = _MovieDetails.model_validate(payload)
    except ValidationError:
        raise TmdbError("TMDB returned invalid movie details.") from None
    return MovieRecord(
        catalog_id=f"tmdb:movie:{movie.id}",
        title=movie.title,
        description=(movie.overview.strip() or None) if movie.overview else None,
        release_date=movie.release_date,
        genres=list(dict.fromkeys(item.name for item in movie.genres)),
        keywords=list(dict.fromkeys(item.name for item in movie.keywords.keywords)),
        provenance=RecordSource(
            source="tmdb",
            source_id=str(movie.id),
            source_url=f"https://www.themoviedb.org/movie/{movie.id}",
            retrieved_at=retrieved_at,
            dataset_version=dataset_version,
        ),
    )


def fetch_movies(
    client: httpx.Client,
    *,
    dataset_version: str,
    limit: int = 500,
    language: str = "en-US",
) -> list[MovieRecord]:
    """Fetch exactly `limit` distinct movies or fail without publishing a catalog."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if not language.strip():
        raise ValueError("language must not be blank")
    records = []
    seen = set()
    # TMDB permits at most 500 discovery pages per query.
    for page_number in range(1, 501):
        payload = _get_json(
            client,
            "/discover/movie",
            {**discovery_parameters(language), "page": page_number},
        )
        try:
            page = _DiscoverPage.model_validate(payload)
        except ValidationError:
            raise TmdbError("TMDB returned invalid discovery data.") from None
        if page.page != page_number:
            raise TmdbError("TMDB returned the wrong discovery page.")
        for item in page.results:
            if item.id in seen:
                continue
            seen.add(item.id)
            details = _get_json(
                client,
                f"/movie/{item.id}",
                {"language": language, "append_to_response": "keywords"},
            )
            movie = normalize_movie(
                details, dataset_version=dataset_version, retrieved_at=datetime.now(UTC)
            )
            if movie.provenance.source_id != str(item.id):
                raise TmdbError("TMDB movie details do not match the requested ID.")
            records.append(movie)
            if len(records) == limit:
                return records
        if page_number >= page.total_pages or not page.results:
            break
    raise TmdbError(f"TMDB returned only {len(records)} distinct movies; requested {limit}.")
