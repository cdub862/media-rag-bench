"""Normalized catalog records with source and snapshot provenance."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl

from .common import Contract, Domain, NonEmptyText


class RecordSource(Contract):
    source: NonEmptyText
    source_id: NonEmptyText
    source_url: HttpUrl
    retrieved_at: AwareDatetime
    dataset_version: NonEmptyText


class CatalogRecord(Contract):
    catalog_id: NonEmptyText
    domain: Domain
    title: NonEmptyText
    description: str | None = None
    provenance: RecordSource


class MovieRecord(CatalogRecord):
    domain: Literal["movies"] = "movies"
    release_date: date | None = None
    genres: list[NonEmptyText] = Field(default_factory=list)
    keywords: list[NonEmptyText] = Field(default_factory=list)
