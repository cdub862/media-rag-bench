# Movie evaluation set

`cases/movies.v1.json` contains 40 original movie recommendation requests with
stable IDs `movies-v1-001` through `movies-v1-040`. Each case uses schema version 1
and works with the existing movie evaluation runner. The three cases in
`cases/movies.sample.json` remain separate synthetic smoke-test fixtures.

The set requests 1, 2, or 3 recommendations per case. Objective constraints use
recommendation count, inclusive release-year bounds, and genre labels. Every
genre in `genres_all` is required; multiple genres mean AND. Theme, mood, style,
and spoiler preferences are subjective and are not automatically scored.

| Cases | Focus |
| --- | --- |
| 001–010 | Individual genres, varied eras, and recommendation counts |
| 011–020 | Combined genres, date ranges, and narrative preferences |
| 021–030 | Theme and tone requests without genre constraints |
| 031–040 | Exact years, older and recent releases, and mixed constraints |

Years are explicit rather than relative to the current date. Recent-release
ranges end in 2025. Prompts request brief, spoiler-free explanations and do not
name expected titles or reveal catalog records.

## Versioning and fair comparisons

Use the same case file, order, rubric, and generation settings when comparing
methods. Once benchmark runs begin, preserve this version; substantive edits
belong in a new version with new case IDs. Reports already record the case-file
SHA-256 hash, which identifies the exact bytes used.

These prompts were authored without consulting a real catalog or model outputs.
Keep them out of retrieval documents and indexes. This separation does not prove
independence from model training data. Corpus coverage, genre intersections, and
the availability of enough qualifying films have not yet been audited against a
live snapshot. A popularity-selected catalog may have poor coverage of older,
documentary, or tightly constrained requests. Record that limitation rather than
changing requests after seeing which method performs better.

Out-of-catalog recommendations are not automatically wrong. Unknown identities
or absent metadata remain `unknown` for objective checks. Catalog genre labels
can also differ from a person's interpretation. Review questionable matches and
keep factual verification separate from subjective relevance.

## Human relevance review: rubric v1

Twelve cases are marked `human_review: true`: **003, 006, 009, 012, 015, 018, 021,
024, 027, 030, 033, and 039**, using the `movies-v1-` prefix. This fixed subset
covers genre, combined-genre, theme, mood, and era preferences. Use it for every
method. It requests 28 recommendations per complete run.

Rate each recommended film's fit to the request's subjective preferences:

| Score | Meaning |
| --- | --- |
| 0 | No meaningful fit; the requested theme, mood, or style is absent. |
| 1 | Weak fit; a minor connection exists, but a central preference is missed. |
| 2 | Good fit; the main preference is met, with a noticeable limitation. |
| 3 | Strong fit; the film clearly satisfies the request's subjective preferences. |

Use **abstain** when you cannot identify the film or lack enough information to
judge it. A persuasive explanation alone is not evidence of relevance. Do not
assign zero solely for a failed date/genre check or an out-of-catalog title;
those outcomes have separate measures. Note misleading explanations and spoilers
separately rather than inventing an automated explanation-accuracy score.

For each rating, record the case ID, recommendation position, blinded run ID,
rater ID, score or abstention, and a short reason. Tie the rating file to the
case-file hash, catalog version, and rubric version. Keep ratings under the
ignored `artifacts/` directory for now.

Present each rater with the original request and the same answer fields for every
method. Hide the provider, direct/RAG label, evidence IDs, and timing/cost data;
shuffle method order and retain the mapping separately. Use the same raters and
information access across methods. Document any independent sources consulted.

Report per-case mean scores over rated recommendations, then an equally weighted
mean over the fixed review cases with ratings. Publish the number of rated and
abstained recommendations, rated cases out of 12, and missing/failed responses
alongside the mean. Compare methods over the same rated cases, identifying any
excluded cases. Do not hide abstentions or missing answers by reporting a mean
alone. Disclose the number of raters; a single-rater review is preliminary.

No human ratings or model benchmark results have been collected in this slice.

## Running the set

The existing `evaluate-movies` command accepts this file through
`--cases benchmarks/cases/movies.v1.json`. Supply a validated catalog snapshot
and saved responses keyed by the new case IDs. The synthetic answers under
`backend/tests/fixtures/` target the sample cases and cannot be reused as answers
to these 40 requests.

Use the readable movie CLI to try an individual case:

```powershell
uv run --locked media-rag-bench recommend movies --case movies-v1-003
```

It displays the instructions and request sent to OpenAI, then prints numbered
answers with years and explanations. Set `OPENAI_API_KEY` and `OPENAI_MODEL` in
your local `.env`, which the CLI loads automatically from the current working
directory, for a live call. Add `--dry-run` for an offline prompt preview. The
selected case supplies its recommendation count. This command displays one
response; full saved benchmark runs remain future work. Game and album support
will follow their dataset adapters.
