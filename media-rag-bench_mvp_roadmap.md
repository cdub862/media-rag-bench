# media-rag-bench — Movie, Music & Video Game Recommendation Benchmark

**Status:** Agreed MVP direction (updated October 30, 2026)  
**Repository:** `media-rag-bench`  
**Project:** Media RAG Bench  
**Goal:** Build a reproducible AI recommendation benchmark and small public-facing demo that compares **direct LLM recommendations against retrieval-augmented generation (RAG)** for **movies, music albums, and video games**, using the **OpenAI API** and a **locally hosted Qwen model**.

## MVP outcome

One repository and one React application with three selectable domains. The same evaluation infrastructure compares four configurations per domain:

| Generation model | Direct LLM (no retrieval) | RAG |
| --- | --- | --- |
| OpenAI API | OpenAI only | OpenAI + RAG |
| Locally hosted Qwen | Qwen only | Qwen + RAG |

**Target: 12 benchmark groups = 3 domains × 4 configurations.**

The central research questions are:

1. Does RAG improve recommendation relevance, factual accuracy, constraint satisfaction, or evidence support?
2. Does the effect vary between OpenAI and locally hosted Qwen?
3. How do quality, end-to-end latency, and resource/cost characteristics differ across models and domains?

**Development strategy:** Complete the full four-way experiment on **movies first**. Add **music albums** and **games** afterward as dataset adapters, without rebuilding the model, retrieval, or benchmark infrastructure.

## Data sources and scope

| Domain | Recommendation unit | Initial source | MVP content |
| --- | --- | --- | --- |
| Movies | Film | [TMDB API](https://developer.themoviedb.org/) | IDs, titles, summaries, genres, release dates, keywords where available |
| Music | Album | [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) | Release-group IDs, album names, artists, dates, genres/tags where available; supplement with appropriately licensed descriptive text only if needed |
| Games | Video game | [RAWG API](https://rawg.io/apidocs) | IDs, titles, descriptions, genres, platforms, release dates, other allowed metadata |

- Start with roughly **500–1,000 movie records**. Add similar-scale music and game catalogs only after the movie benchmark works.
- Record provenance, retrieval date, source IDs, and dataset versions. Respect each provider's API terms, usage limits, attribution requirements, and redistribution restrictions. Do not commit restricted API responses, copyrighted text, or secrets without permission.
- Store a normalized shared record shape, but retain domain-specific fields and validation rules. Music recommendations mean **albums**, not an ambiguous mixture of tracks, artists, and albums.
- Some metadata sources contain little natural-language description. Record this limitation and measure its effect on RAG instead of fabricating corpus text.

## Comparison and evaluation principles

- Use the **same questions, generation model version and settings, output schema, and scoring rubric** for direct vs. RAG within a domain. Use comparable prompts between OpenAI and Qwen while accommodating genuine model capability differences.
- The **direct LLM** baselines must not receive retrieved dataset records. The dataset may be consulted *after inference* to evaluate answers. Avoid unfairly counting a correct real-world recommendation as wrong solely because it lies outside the curated index; report out-of-catalog responses separately.
- Both RAG variants within a domain use the **same index, retrieval corpus, embeddings, and retrieved candidates** when comparing generation models.
- Use structured, validated outputs containing recommended catalog identity (or proposed title for direct LLM), brief explanation, and any evidence IDs available. Match free-form titles to known identities carefully and report ambiguous matches.
- Create **30–50 movie evaluation requests initially**; add separate domain-appropriate sets for music and games. Include objective constraints (e.g., date, genre, platform, artist) plus subjective relevance judgments where feasible.
- Keep an independent, versioned evaluation set distinct from retrieval documents where possible; disclose potential overlap and corpus-coverage limitations.
- Report unsuccessful calls, invalid structured outputs, missing citations, and negative results—not only successful examples. Do not assume RAG is superior.

## MVP implementation phases

### Phase 1 — Movie dataset and evaluation foundation

- Set up a minimal Python project using **uv**, **Pydantic**, and **pytest**.
- Implement TMDB ingestion, normalization, snapshot/version metadata, and local storage for a small movie catalog.
- Define a shared recommendation response contract, domain-neutral evaluation runner, and movie-specific constraints/scorers.
- Prepare 30–50 representative movie recommendation requests, expected factual constraints, and a small human-rated subset for relevance.
- Ensure evaluation works on fixture responses before connecting any LLM.

**Done when:** A reproducible movie catalog and a tested evaluation harness exist independently of the model.

### Phase 2 — OpenAI direct-LLM baseline on movies

- Call the **OpenAI API directly**, with no LangChain or retrieval dependency.
- Generate structured recommendations from movie prompts, validate outputs, and score them against the benchmark.
- Record model/version, configuration, latency, token usage, actual API cost, errors, and per-question outcomes.
- Save benchmark results in a comparable, reproducible format.

**Done when:** We have a measured **OpenAI-only movie baseline**.

### Phase 3 — Local Qwen direct-LLM baseline on movies

- Connect to a locally hosted **Qwen** inference server via an appropriate compatible client.
- Use the same movie questions, semantic output contract, and evaluation harness as Phase 2.
- Record model/quantization, hardware environment, inference latency, tokens per second, CPU/GPU utilization, and memory usage where available.
- Distinguish **no external per-token API fee** from real hardware, electricity, and possible cloud-compute costs.

**Done when:** Direct OpenAI and direct local Qwen have comparable movie benchmark reports.

### Phase 4 — LlamaIndex RAG on movies

- Use **LlamaIndex** to index the movie corpus, persist the retrieval index, and retrieve relevant records for each query.
- Feed consistent retrieved context to OpenAI and Qwen through otherwise comparable recommendation pipelines.
- Add provenance/evidence checks and record retrieval latency separately from generation latency.
- Benchmark **OpenAI + RAG** and **Qwen + RAG** against the same movie questions.

**Done when:** All **four movie configurations** are measured, with a documented direct-vs-RAG comparison and analysis of failures.

### Phase 5 — Add music and games using the same engine

- Introduce dataset adapters for **MusicBrainz album metadata** and **RAWG game metadata**, including ingestion, normalized IDs, and domain-specific metadata.
- Create separate music and game indexes using the existing LlamaIndex retrieval pipeline.
- Add 30–50 domain-appropriate evaluation prompts and constraints per dataset; ensure meaningful descriptive data is available for retrieval.
- Run all four configurations for each new domain without duplicating model or benchmark logic.

**Done when:** The platform produces **12 benchmark groups** across movies, music albums, and games with comparable reports and clearly documented domain differences.

### Phase 6 — React demo, results, and reproducible release

- Create a compact **React + TypeScript** interface with **Movies / Music / Games** selection and a four-method recommendation comparison.
- Display recommendation results, retrieved evidence (when applicable), per-run latency/usage information, and benchmark aggregates.
- Provide a reproducibility page or README with dataset/model/index versions, benchmark commands, results, limitations, and architecture.
- Package the backend and UI for deployment; protect OpenAI credentials with server-side execution, rate limits, caching, and spending controls.
- A hosted Qwen runtime is **not required** for a public demo: allow clearly labeled precomputed Qwen examples/benchmark results if the live local GPU is unavailable. Never present cached or hosted runs as live local inference.

**Done when:** Visitors can inspect real comparisons, run bounded demo queries where supported, and understand how to reproduce the published benchmarks.

## Evaluation metrics

| Category | Metrics |
| --- | --- |
| **Recommendation quality (primary)** | Relevance (including human-rated subset), valid identities, factual correctness, constraint satisfaction, evidence support for RAG |
| **Reliability (primary)** | Invalid structured outputs, unsupported claims, missing/ambiguous catalog matches, API failures |
| **Performance (primary)** | End-to-end latency (median/p95), retrieval vs. generation time, Qwen tokens/second |
| **Cost and resources (secondary)** | OpenAI input/output tokens and actual API spend; Qwen GPU/CPU utilization, RAM/VRAM, approximate power/hardware expense where feasible |

Publish raw per-question results or a distributable, license-safe evaluation artifact alongside aggregate metrics. Distinguish measured results from illustrative examples.

## Proposed technical stack

- **Backend:** Python, uv, Pydantic, pytest; FastAPI for demo endpoints.
- **Direct models:** OpenAI API; local Qwen served by a compatible inference runtime.
- **RAG:** LlamaIndex with a consistent embedding/retrieval setup and domain-specific indexes.
- **Data:** Domain adapters and reproducible catalogs; SQLite for metadata if useful, plus a persisted vector index.
- **Frontend:** React + TypeScript (small comparison UI, not a full recommendation social network).
- **Operations:** Environment-based secrets, cached examples for public demo, rate limits, CI, documented benchmark commands.

## Post-MVP possibilities

- **LangChain agentic pipeline:** Let an agent choose among metadata filtering, semantic retrieval, or multiple tools; benchmark it as a *new* experimental configuration, not part of the initial four-way comparison.
- Hybrid keyword/vector search, reranking, richer legally reusable corpora, additional local models, conversational follow-ups, user preferences, and personalized recommendations.
- Broader datasets or deeper domain-specific assessments once the first 12 configurations are reproducible.

## Explicitly out of scope for the MVP

User accounts, watchlists, streaming-service integrations, audio/video understanding from raw media, collaborative features, complex multi-agent systems, and production-scale catalogs.
