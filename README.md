# Media RAG Bench

Compare direct LLM recommendations with retrieval-augmented generation for movies,
then albums and video games. The full plan is in
[the MVP roadmap](media-rag-bench_mvp_roadmap.md).

## Current phase

Phase 1C adds offline evaluation of saved recommendations against validated movie
snapshots. The earlier slices provide Python contracts and TMDB ingestion. The
evaluation set still contains three synthetic cases; expanding it to 30–50 real
requests is a later slice. No model calls or frontend are included in this slice.

## Run from the repository root

Install [uv](https://docs.astral.sh/uv/) and run:

```powershell
uv sync --locked
uv run --locked pytest
```

`.python-version` selects Python 3.14 for development. The package declares Python
3.12 or newer; other Python versions have not yet been verified.

If your default uv cache is not writable, use a workspace-local cache:

```powershell
$env:UV_CACHE_DIR = "$PWD/.uv-cache"
uv sync --locked
uv run --locked pytest
```

The root `pyproject.toml` packages `backend/src/media_rag_bench`; no directory
changes, manual virtual environment activation, or `PYTHONPATH` changes are needed.
uv's build backend supports this through its
[`module-root` setting](https://docs.astral.sh/uv/configuration/build-backend/).

The CLI automatically loads `.env` from the current working directory when the
file exists. Run commands from the repository root to use your local `.env`.
Existing shell variables take precedence over `.env`. A missing `.env` is fine
when using shell variables or offline evaluation.

## Layout

- `backend/src/media_rag_bench/schemas/`: movie records, provenance, recommendation
  responses, and movie evaluation cases.
- `backend/src/media_rag_bench/datasets/`: TMDB ingestion and JSON snapshot storage.
- `backend/src/media_rag_bench/evaluation/`: shared runner and movie matching/scoring.
- `backend/tests/`: focused validation tests and synthetic fixtures.
- `benchmarks/cases/`: versioned evaluation requests, separate from catalog data.
- `data/` and `artifacts/`: reserved for local catalogs and generated outputs;
  ignored by Git.

Python dependencies and their lockfile live at the root. When the frontend phase
is approved, React + TypeScript will live in `frontend/`, with Bun dependencies,
a root lockfile, and root scripts to start the API and UI together.

## Ingest a movie catalog

Get an **API Read Access Token** from your [TMDB API settings](https://www.themoviedb.org/settings/api).
TMDB accepts it as a Bearer token; see [application authentication](https://developer.themoviedb.org/docs/authentication-application).
Copy `.env.example` to `.env` and set `TMDB_READ_ACCESS_TOKEN` locally. The CLI
loads it automatically:

```powershell
uv run --locked media-rag-bench ingest-movies --dataset-version movies-v1 --limit 500
```

For an initial live smoke check, use a separate version with `--limit 5`. The limit
must be between 1 and 1,000; it defaults to 500. `--language` defaults to `en-US`;
it selects translated metadata, not movies' original language. You can also set
the token in your shell environment instead of `.env`.

The command uses [movie discovery](https://developer.themoviedb.org/reference/discover-movie)
sorted by descending popularity, excludes adult and video entries, deduplicates
IDs across pages, and fetches [movie details](https://developer.themoviedb.org/reference/movie-details)
with appended keywords. Requests are sequential with a 250 ms pause before each
request and a 20 second network timeout. Authentication failures, rate limits,
network failures, invalid records, or insufficient results stop the run without
publishing a partial catalog. There are no automatic retries; on a `429`, wait
before retrying, following [TMDB's rate-limit guidance](https://developer.themoviedb.org/docs/rate-limiting).

The result is `data/movies/movies-v1.json`. Use `--output-dir` to select a different
directory. A version file is never overwritten; use a new `--dataset-version`
for a fresh snapshot. Versions allow 1–80 letters, digits, underscores, or hyphens
and must start with a letter or digit.

Each snapshot contains normalized records and metadata: schema and dataset
versions, creation time, record count, discovery parameters, and a SHA-256 checksum
of the records. Each record retains its TMDB ID, source link, retrieval timestamp,
and dataset version through `RecordSource`. The checksum uses UTF-8 JSON of the
`records` array, sorted object keys, compact separators, and unescaped Unicode.
The snapshot contains no access token or raw API response bodies.

Preserve a snapshot to reproduce an experiment. A later fetch can return different
data or rankings even with identical discovery parameters. This initial catalog
is selected by popularity and is not a balanced sample. API tests use synthetic
responses; a live fetch requires your local token.

Keep fetched data local: `data/` is ignored by Git. Review TMDB's current usage and
redistribution terms before sharing a catalog. Public presentation must follow
the [TMDB attribution requirements](https://developer.themoviedb.org/docs/faq),
including an approved logo when the demo is built.

This product uses the TMDB API but is not endorsed or certified by TMDB.

## Evaluate saved recommendations

This command runs entirely offline and does not require a TMDB or model token:

```powershell
uv run --locked media-rag-bench evaluate-movies --snapshot backend/tests/fixtures/movie_snapshot.json --cases benchmarks/cases/movies.sample.json --responses backend/tests/fixtures/evaluation_responses.json --method rag --output artifacts/evaluation-fixture-rag-v1.json
```

The included snapshot and answers are synthetic fixtures. This checks the runner,
not model quality. To evaluate your own saved answers, use a movie snapshot from
ingestion, an array of movie cases, and a JSON object mapping case IDs to responses:

```json
{
  "fixture-movies-001": {
    "domain": "movies",
    "recommendations": [
      {
        "title": "The Quiet Observatory",
        "release_year": 2005,
        "explanation": "A story about exploration.",
        "catalog_id": "fixture:movie:1",
        "evidence_ids": ["fixture:movie:1"]
      }
    ]
  }
}
```

Use `--method direct` for direct responses, which can omit catalog and evidence
IDs. A value can also be a raw JSON response string, or `{"error": "Model unavailable"}`
to record an unsuccessful call. Missing cases and malformed responses are reported
separately. Unknown case IDs, duplicate case IDs, and invalid input files stop the
command. An existing output report is never overwritten.

Snapshot loading validates the schema, checksum, record count, unique catalog IDs,
and source/version consistency. Reports retain the dataset version and records
checksum, case/response file hashes, evaluator version, and per-case results.

Matching uses a supplied catalog ID and checks its title, or uses a normalized
title and the proposed release year when available. Normalization applies Unicode
NFKC, case folding, and whitespace collapsing; punctuation is preserved. No fuzzy
matching is performed. Ambiguous titles, out-of-catalog identities, and conflicting
known IDs/titles are reported separately. An out-of-catalog title is not labeled
factually wrong. Unresolvable identities and missing catalog metadata produce
`unknown` constraint checks rather than failures.

Objective checks cover the requested count, duplicate recommendations, inclusive
release-year bounds, all requested genres, and stated release years. RAG evidence
IDs must exist in the catalog and include the matched movie's ID; evidence is
`not_applicable` for direct responses. These ID checks do not establish that a
record was retrieved or that the explanation is supported by its text.

Summary counts retain `pass`, `fail`, `unknown`, and `not_applicable` separately.
Count/uniqueness checks have one result per case; fact/evidence checks have one
result per recommendation in structurally valid responses. Invalid, missing, and
failed responses remain in the response totals. No composite quality score is
calculated. Subjective relevance, explanation accuracy, and human ratings remain
outside this automated scorer.

## Contracts and fixtures

Movie records retain source identity, source URL, timezone-aware retrieval time,
and dataset version. An unknown release date or missing description can be kept
as missing data rather than fabricated.

Recommendation responses share a domain and a list of recommendations. A direct
response can use a proposed title without a catalog ID; a RAG response can attach
catalog and evidence IDs. Missing citations and out-of-catalog titles remain
representable so the evaluator can report them. Schema validation checks shape,
not factual accuracy or recommendation quality.

`benchmarks/cases/movies.sample.json` and the test fixtures use fictional titles
and original descriptions. They are smoke-test inputs, not a real catalog, the
planned 30–50 evaluation requests, or measured benchmark results. The
`human_review` flag selects cases for later human relevance ratings; no ratings
have been collected.

Work proceeds one approved slice at a time, following [AGENTS.md](AGENTS.md).
