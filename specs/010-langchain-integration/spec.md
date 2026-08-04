# Feature Specification: Migrate Generation and Retrieval to LangChain

**Feature Branch**: `010-langchain-integration`

**Created**: 2026-08-04

**Status**: Draft

**Input**: User description: "Migrate the LLM generation and retrieval layers to LangChain, per
the amended constitution (Principle III: Standard Integration Layers via LangChain). Today,
src/vacancy_radar/llm/ contains a hand-rolled LLMProvider ABC with separate ClaudeProvider (raw
anthropic SDK) and OllamaProvider (raw httpx calls) implementations, and
src/vacancy_radar/retriever.py + chroma_store.py hand-wrap a ChromaDB client directly. This
should move onto LangChain's BaseChatModel abstraction (ChatAnthropic for the hosted Claude
backend, ChatOllama for the fully local/offline Ollama backend) for generation, and LangChain's
VectorStore/retriever interface (langchain-chroma's Chroma) for retrieval, instead of the
current hand-rolled equivalents. This is an internal architecture migration, not a new
user-facing feature: every existing behavior must be preserved exactly as-is from the
perspective of anyone using the app — the JSON/HTML API contracts, the grounded match-report
generation and its citation-checking requirement, vacancy upload drafting (including
vision-based drafting/analysis for image uploads), similar-vacancy retrieval, and the eval
harness must all keep working identically. Nothing about what a user sees or does should
change; only the underlying implementation mechanism for talking to LLM providers and the
vector store changes."

## User Scenarios & Testing *(mandatory)*

<!--
  This feature is an internal architecture migration mandated by the project's own constitution
  (Principle III, amended 2026-08-04) rather than new user-facing value. Its "users" are
  therefore framed as the maintainer (who depends on the app continuing to work and on the
  codebase depending on maintained integrations instead of hand-rolled ones) and, transitively,
  anyone using the running app (who must see zero change in behavior).
-->

### User Story 1 - Generation keeps working, now via a maintained integration (Priority: P1)

The maintainer wants match-report generation, vacancy-metadata drafting, and vision-based
analysis to run through LangChain's chat model abstraction instead of hand-written
per-vendor request/response code — so that provider-specific quirks (structured output,
retries, vision content blocks) are the maintained integration's responsibility, not this
repo's. Anyone using the app must see no difference: the same kind of match report, the same
drafted fields, the same grounding guarantee.

**Why this priority**: This is the larger and riskier of the two migrations (it sits directly
under the non-negotiable grounding/citation requirement), and the one named first in the
constitution amendment — it has to work before the retrieval migration's value is fully
realized, since `/analyze` exercises both together.

**Independent Test**: Run the existing automated test suite and eval harness against the
migrated generation code with a fake/stubbed chat model; separately, run the manual quickstart
scenarios from [[006-vacancy-upload]], [[007-vision-drafting]], and [[009-analyze-and-log-vacancy]]
against a real configured backend and confirm the outputs are the same kind of result as before
the migration.

**Acceptance Scenarios**:

1. **Given** a job posting and ingested experience bullets, **When** a match report is
   requested, **Then** the report has the same shape (score, flags, gaps, similar vacancies,
   draft paragraph) and every flag/draft sentence is still citation-checked against real source
   text before being included.
2. **Given** an uploaded vacancy document (text, PDF, DOCX, or image), **When** metadata is
   drafted, **Then** company/position/date are proposed the same way as before, including the
   vision path for images.
3. **Given** a backend that can't complete a request (unreachable, misconfigured, or lacking
   vision support), **When** generation or drafting is attempted, **Then** the same specific,
   plain-language failure behavior established in prior features still occurs — no silent
   fallback, no generic unhandled error.

---

### User Story 2 - Retrieval keeps working, now via a maintained integration (Priority: P2)

The maintainer wants experience-bullet and similar-vacancy retrieval to run through LangChain's
vector store interface instead of a hand-rolled wrapper around the Chroma client — including
delegating the minimum-similarity cutoff and doc-type filtering to LangChain's own
score-threshold/filter support rather than hand-implemented post-query filtering. What LangChain
has no generic equivalent for — flagging a match as a likely duplicate above a second, higher
threshold, and collapsing multiple chunks from the same vacancy to its single best-scoring hit
— remains this project's own logic on top of the retrieved, scored results. Either way, results
must stay the same.

**Why this priority**: Lower priority than generation because retrieval is comparatively
lower-risk (no non-negotiable citation requirement sits directly on it), but it's still named
explicitly in the constitution amendment and exercised by the same `/analyze` flow as User
Story 1.

**Independent Test**: Re-run the eval harness's retrieval checks (bullet-retrieval recall@5/MRR,
similar-vacancy precision@3) against the migrated retrieval code and confirm no regression
against the checked-in golden fixtures; confirm `/similar` still flags near-duplicate postings
the same way.

**Acceptance Scenarios**:

1. **Given** a job posting similar to one already ingested, **When** similar vacancies are
   requested, **Then** the same vacancy is returned with a comparable similarity score and the
   same duplicate/non-duplicate classification as before the migration.
2. **Given** the local cache is deleted and ingestion is re-run from source, **When** retrieval
   is exercised afterward, **Then** the same vacancies/bullets are retrievable as before —
   nothing about the source-of-truth data or its retrievability is lost by the migration.

---

### Edge Cases

- A structured-output response that today parses cleanly into `CandidateReport`/
  `DraftVacancyMetadata` must still parse cleanly through whatever mechanism LangChain uses to
  request/validate structured output — a change here that silently loosens validation would be
  a regression, not neutral.
- Ollama's current "retry once on invalid JSON" behavior must have an equivalent (LangChain's
  own retry/parsing behavior, or an explicit reimplementation of the same one-retry rule) —
  simply dropping it would reduce robustness against a real local-model failure mode already
  observed.
- The eval harness's four checks are the regression gate for this migration specifically
  because they're the only fully local, deterministic, checked-in measurement of grounding and
  retrieval quality — any of them newly failing after the migration blocks it from being done.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: LLM generation (match-report analysis, vacancy-metadata drafting, vision-based
  text extraction for image analysis) MUST be performed via LangChain's chat model abstraction
  rather than direct vendor SDK/HTTP calls.
- **FR-002**: Vector retrieval (experience-bullet queries, similar-vacancy queries) MUST be
  performed via LangChain's vector store/retriever interface rather than a hand-rolled Chroma
  client wrapper.
- **FR-003**: The existing JSON (`POST /api/analyze`, `POST /api/similar`) and HTML
  (`POST /analyze`, `POST /ingest/draft`, `POST /ingest/confirm`) route contracts MUST be
  unchanged in request/response shape and status codes as a result of this migration.
- **FR-004**: Every generated claim MUST continue to be citation-checked against retrieved
  source text before it can appear in a response — the grounding requirement is carried through
  unchanged, not re-implemented differently.
- **FR-005**: Both a hosted (Claude) and a fully local/offline (Ollama) generation backend MUST
  remain fully functional through the migrated abstraction, selected the same way as today
  (presence of an API key, no separate switch).
- **FR-006**: Vision-based capabilities (image-based metadata drafting, image-based match-report
  analysis) MUST continue to work with no silent OCR-like fallback — a failure MUST still
  produce the same specific, honest failure messaging behavior already established.
- **FR-007**: The eval harness's four existing checks (grounding enforcement, bullet-retrieval
  recall/MRR, similar-vacancy precision, filter-rule consistency) MUST pass at parity with their
  pre-migration results.
- **FR-008**: The minimum-similarity cutoff and doc-type filter on similar-vacancy retrieval
  MUST be delegated to LangChain's own score-threshold/filter search support rather than
  hand-implemented post-query filtering. The duplicate-flag threshold and deduplication to the
  best-scoring chunk per vacancy — for which LangChain has no generic equivalent — MUST remain
  this project's own logic applied to the scored results, and MUST keep producing the same
  matches and classifications as today.
- **FR-009**: The regenerable-derived-state guarantee (the local cache can be deleted and
  rebuilt from source with no data loss) MUST be preserved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every existing automated test and eval harness check passes after the migration,
  with no assertion weakened or removed to make it pass.
- **SC-002**: A user pasting or uploading the same job posting before and after the migration
  receives a match report of the same shape and grounding guarantee (citations still verified
  against real source text) — exact generated wording is not expected to be identical, since
  that already varies run-to-run today.
- **SC-003**: Switching between the hosted and local backend continues to require no more
  configuration than it does today (an API key present or absent).
- **SC-004**: Deleting the local cache and re-running ingestion reproduces the same retrievable
  set of vacancies and experience bullets as before the migration.

## Assumptions

- LangChain's `ChatAnthropic`/`ChatOllama` support a structured-output mechanism close enough to
  today's (Claude's JSON-schema-constrained output, Ollama's JSON-mode with a retry-on-invalid
  rule) that `CandidateReport`/`DraftVacancyMetadata` parsing is preserved without weakening
  grounding — if a gap exists, it is closed by explicit equivalent logic in this repo, not
  silently dropped.
- LangChain's `Chroma` vector store can operate against the same on-disk embedded/persistent
  Chroma directory (`.cache/chroma`) already in use, so this migration does not require
  re-embedding or a data migration step.
- Confirmed against LangChain's actual retriever implementation: its minimum-similarity and
  metadata-filter support (`score_threshold` / `filter` search arguments) is delegated to
  directly, replacing the hand-implemented equivalents in `retriever.py`. Its wrapped
  `Retriever.invoke()` discards the numeric similarity score after filtering, so the migrated
  code calls the vector store's own scored-search method directly (still LangChain's interface,
  just not the bare-`Retriever` wrapper) to keep the score value the duplicate-flag/dedup logic
  needs. That duplicate-flag threshold and best-scoring-chunk-per-vacancy deduplication have no
  generic LangChain equivalent and remain this project's own logic on the scored results.
- Local `sentence-transformers` embeddings continue to be used, accessed via LangChain's
  embeddings interface instead of directly — no change to the embedding model or vector
  dimensionality, so no `reindex` is required by this migration itself.
