# Agent instructions

## Approval before implementation

- Work in small, explicitly approved phases.
- Read-only inspection, research, analysis, and proposals are allowed without implementation approval.
- Do not implement anything unless the user explicitly approves the concrete scope first. This includes application code, scaffolding, configuration, dependency changes or installation, generated project files, and implementation-driven changes to existing files.
- A request for recommendations, discussion, or planning is not approval to implement the proposal. If approval is unclear, present the proposed scope and wait.
- Approval applies only to the agreed scope. Complete that scope, report the changes and verification, and wait for approval before starting another phase or expanding the work.
- A direct user request to edit a particular document or agent instruction authorizes that edit only; it does not authorize application implementation.

## Phase review and commit workflow

1. Propose one small phase with a concrete scope and wait for the user to confirm it before implementation.
2. Implement only that phase and perform the minimal relevant verification described below.
3. Report the completed changes using the phase report requirements below, then stop and wait for the user's review approval. Do not commit yet or start the next phase.
4. When the user says "approve" in response to the completed phase, commit the reviewed changes for that phase. Include only the phase's changes; do not include unrelated user work. This approval authorizes the commit, not implementation of the next phase.
5. Report the commit and automatically describe the next phase's concrete scope in the same response. Do not require separate confirmation or ask permission to show or discuss the next phase. Presenting the scope does not authorize implementation; begin only when the user explicitly approves that scope.
6. Repeat this workflow for each phase. Keep approval of completed work separate from confirmation to begin new work.

## Phase implementation reports

- After every phase implementation, explain in plain language what was done and how the resulting behavior works.
- Include clickable references to the relevant changed files, with line numbers for the main implementation points where useful.
- Explain why each main change was needed and how it contributes to the approved phase and project goal. Connect the explanation to the referenced files rather than listing filenames alone.
- Report the verification performed, its results, and what remains for manual testing, including any material limitations.
- State that the phase is ready for review and whether it has been committed. Stop for review approval as required by the workflow above.

## Commit message conventions

- Use Conventional Commits in the form `type(scope): description`; include a meaningful scope.
- Choose the type that describes the change: `feat`, `fix`, `docs`, `refactor`, `test`, or `chore`.
- Use a concise, imperative description of the actual change, for example `feat(catalog): add TMDB ingestion` or `fix(evaluation): handle ambiguous titles`.
- Do not include phase names or phase numbers in commit subjects or bodies. Describe the resulting behavior or change instead.

## Implementation scope

- Implement only what the user asks for within the approved scope, plus the minimum supporting changes necessary to make it work.
- Do not add unsolicited features, speculative abstractions, unrelated refactors, or extra tooling.

## Testing

- Use the smallest meaningful set of automated tests that covers the critical app behavior affected by the change. Keep test-writing effort proportional to the change; do not pursue exhaustive coverage.
- For a regression bug, prioritize a focused automated test that reproduces the bug and verifies the fix, whenever practical.
- Prioritize critical behavior such as data validation, benchmark correctness, recommendation contracts, and essential API flows as those features are implemented.
- The user will manually test other frontend behavior for now. Do not add broad frontend test suites or tests for cosmetic changes unless requested or needed to protect a critical flow or regression.
- Run the relevant existing checks and any focused tests added for the change. Broaden testing only when failures or a concrete risk justify it.
- Report what was verified and what remains for manual testing.

## Project direction

- Read `media-rag-bench_mvp_roadmap.md` before proposing project changes.
- Follow the movie-first roadmap. Keep shared benchmark logic independent of the HTTP API and frontend.
- Treat proposed architecture and tooling as proposals until the user approves them.
