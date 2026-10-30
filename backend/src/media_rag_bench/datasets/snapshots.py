"""Versioned JSON movie catalogs kept outside version control."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import re

from media_rag_bench.schemas import MovieRecord

from .tmdb import API_ROOT, discovery_parameters


def snapshot_path(output_dir: Path, dataset_version: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", dataset_version):
        raise ValueError(
            "dataset-version must be 1-80 letters, digits, underscores, or hyphens, "
            "starting with a letter or digit"
        )
    return output_dir / f"{dataset_version}.json"


def save_movie_snapshot(
    records: list[MovieRecord],
    *,
    output_dir: Path,
    dataset_version: str,
    requested_count: int,
    language: str,
) -> Path:
    destination = snapshot_path(output_dir, dataset_version)
    if len(records) != requested_count or not records:
        raise ValueError("snapshot must contain the requested number of movies")
    if len({record.catalog_id for record in records}) != len(records):
        raise ValueError("snapshot contains duplicate catalog IDs")
    if any(
        record.provenance.dataset_version != dataset_version
        or record.provenance.source != "tmdb"
        for record in records
    ):
        raise ValueError("record sources must match the TMDB snapshot version")
    serialized_records = [record.model_dump(mode="json") for record in records]
    canonical_records = json.dumps(
        serialized_records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    snapshot = {
        "schema_version": 1,
        "dataset_version": dataset_version,
        "source": "tmdb",
        "domain": "movies",
        "created_at": datetime.now(UTC).isoformat(),
        "record_count": len(records),
        "records_sha256": hashlib.sha256(canonical_records).hexdigest(),
        "selection": {
            "endpoint": f"{API_ROOT}/discover/movie",
            "parameters": discovery_parameters(language),
            "requested_count": requested_count,
        },
        "records": serialized_records,
    }
    # Serialize the complete catalog before opening a new, exclusive version file.
    contents = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        try:
            handle.write(contents)
        except BaseException:
            handle.close()
            destination.unlink()
            raise
    return destination
