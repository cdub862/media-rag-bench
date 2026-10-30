import hashlib
import json
from pathlib import Path

import httpx
import pytest

from media_rag_bench.cli import main
from media_rag_bench.datasets import tmdb
from media_rag_bench.schemas import MovieRecord

MOVIES = json.loads(
    (Path(__file__).parent / "fixtures/tmdb_movies.json").read_text(encoding="utf-8")
)


@pytest.fixture
def mock_tmdb(monkeypatch):
    client_class = httpx.Client
    monkeypatch.setenv("TMDB_READ_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setattr(tmdb, "sleep", lambda seconds: None)

    def install(handler):
        monkeypatch.setattr(
            "media_rag_bench.cli.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


def command(output_dir, *extra):
    return [
        "ingest-movies", "--dataset-version", "movies-v1",
        "--limit", "2", "--output-dir", str(output_dir), *extra,
    ]


def test_ingestion_paginates_deduplicates_and_saves_a_reproducible_snapshot(
    tmp_path, mock_tmdb, capsys
):
    requested_ids = []

    def handler(request):
        assert request.headers["Authorization"] == "Bearer fixture-token"
        assert request.url.params["language"] == "en-US"
        if request.url.path.endswith("/discover/movie"):
            assert request.url.params["include_adult"] == "false"
            assert request.url.params["sort_by"] == "popularity.desc"
            page = int(request.url.params["page"])
            ids = [900001] if page == 1 else [900001, 900002]
            return httpx.Response(200, json={
                "page": page, "total_pages": 2, "results": [{"id": value} for value in ids],
            })
        assert request.url.params["append_to_response"] == "keywords"
        movie_id = int(request.url.path.rsplit("/", 1)[1])
        requested_ids.append(movie_id)
        return httpx.Response(200, json=next(movie for movie in MOVIES if movie["id"] == movie_id))

    mock_tmdb(handler)
    assert main(command(tmp_path)) == 0
    assert requested_ids == [900001, 900002]
    contents = (tmp_path / "movies-v1.json").read_text(encoding="utf-8")
    snapshot = json.loads(contents)
    records = [MovieRecord.model_validate(item) for item in snapshot["records"]]
    assert snapshot["record_count"] == 2
    assert snapshot["dataset_version"] == "movies-v1"
    assert snapshot["selection"]["requested_count"] == 2
    assert records[0].catalog_id == "tmdb:movie:900001"
    assert records[0].description == MOVIES[0]["overview"].strip()
    assert records[0].keywords == ["exploration"]
    assert records[0].provenance.source == "tmdb"
    assert records[0].provenance.dataset_version == "movies-v1"
    assert records[0].provenance.retrieved_at.tzinfo is not None
    assert records[1].release_date is None
    assert records[1].description is None
    assert records[1].keywords == []
    canonical = json.dumps(snapshot["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert snapshot["records_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert "fixture-token" not in contents
    assert "Saved 2 movies" in capsys.readouterr().out


def test_existing_snapshot_is_not_overwritten_or_refetched(tmp_path, mock_tmdb, capsys):
    destination = tmp_path / "movies-v1.json"
    destination.write_text("original snapshot", encoding="utf-8")

    def unexpected_request(request):
        pytest.fail("An existing version must be refused before any request")

    mock_tmdb(unexpected_request)
    assert main(command(tmp_path)) == 1
    assert destination.read_text(encoding="utf-8") == "original snapshot"
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("auth", "authentication failed"),
        ("rate-limit", "rate limit"),
        ("timeout", "Could not reach TMDB"),
        ("bad-json", "invalid JSON"),
        ("bad-details", "invalid movie details"),
        ("exhausted", "only 0 distinct movies"),
    ],
)
def test_ingestion_errors_do_not_publish_a_partial_catalog(
    failure, message, tmp_path, mock_tmdb, capsys
):
    def handler(request):
        if request.url.path.endswith("/discover/movie"):
            results = [] if failure == "exhausted" else [{"id": 900001}, {"id": 900002}]
            return httpx.Response(200, json={"page": 1, "total_pages": 1, "results": results})
        if request.url.path.endswith("/900001"):
            return httpx.Response(200, json=MOVIES[0])
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture-token must not be logged", request=request)
        if failure == "bad-json":
            return httpx.Response(200, text="not JSON")
        if failure == "bad-details":
            return httpx.Response(200, json={"id": 900002, "title": " "})
        return httpx.Response(401 if failure == "auth" else 429)

    mock_tmdb(handler)
    assert main(command(tmp_path)) == 1
    assert not (tmp_path / "movies-v1.json").exists()
    captured = capsys.readouterr()
    assert message in captured.err
    assert "fixture-token" not in captured.err


def test_missing_token_and_unsafe_version_fail_before_network(
    tmp_path, monkeypatch, mock_tmdb, capsys
):
    def unexpected_request(request):
        pytest.fail("Invalid configuration must be refused before any request")

    mock_tmdb(unexpected_request)
    monkeypatch.delenv("TMDB_READ_ACCESS_TOKEN")
    assert main(command(tmp_path)) == 1
    assert "Set TMDB_READ_ACCESS_TOKEN" in capsys.readouterr().err
    assert main(command(tmp_path, "--dataset-version", "../escape")) == 1
    assert "dataset-version must" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
