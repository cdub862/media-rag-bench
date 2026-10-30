# Media RAG Bench

Compare direct LLM recommendations with retrieval-augmented generation for movies,
then albums and video games. The full plan is in
[the MVP roadmap](media-rag-bench_mvp_roadmap.md).

## Current phase

Phase 1A: Python setup, validated data and recommendation contracts, and a small
set of synthetic movie evaluation cases. TMDB ingestion and the evaluation runner
are subsequent slices of roadmap Phase 1. No model calls or frontend are included
in this slice.

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

## Layout

- `backend/src/media_rag_bench/schemas/`: movie records, provenance, recommendation
  responses, and movie evaluation cases.
- `backend/tests/`: focused validation tests and synthetic fixtures.
- `benchmarks/cases/`: versioned evaluation requests, separate from catalog data.
- `data/` and `artifacts/`: reserved for local catalogs and generated outputs;
  ignored by Git.

Python dependencies and their lockfile live at the root. When the frontend phase
is approved, React + TypeScript will live in `frontend/`, with Bun dependencies,
a root lockfile, and root scripts to start the API and UI together.

## Contracts and fixtures

Movie records retain source identity, source URL, timezone-aware retrieval time,
and dataset version. An unknown release date or missing description can be kept
as missing data rather than fabricated.

Recommendation responses share a domain and a list of recommendations. A direct
response can use a proposed title without a catalog ID; a RAG response can attach
catalog and evidence IDs. Missing citations and out-of-catalog titles remain
representable so the future evaluator can report them. Validation checks shape,
not factual accuracy or recommendation quality.

`benchmarks/cases/movies.sample.json` and the test fixtures use fictional titles
and original descriptions. They are smoke-test inputs, not a real catalog, the
planned 30–50 evaluation requests, or measured benchmark results. The
`human_review` flag selects cases for later human relevance ratings; no ratings
have been collected.

Work proceeds one approved slice at a time, following [AGENTS.md](AGENTS.md).
