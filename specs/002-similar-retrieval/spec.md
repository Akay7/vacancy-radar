# Feature Specification: `/similar` Retrieval

**Feature Branch**: `002-similar-retrieval`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "`/similar` retrieval" (second unchecked item on the README roadmap, building on the [Ingestion CLI](../001-ingestion-cli/spec.md))

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See similar past vacancies with their outcomes (Priority: P1)

As the user, when I paste a job posting's text, I get back the past vacancies I've already
engaged with that most closely resemble it, each showing what happened (applied, rejected,
offer, etc.), so I immediately know "have I basically seen this one before, and how did it go?"

**Why this priority**: This is the entire point of the feature per the README — "dedupe +
memory: you saw almost this vacancy before — applied, rejected for X." Without this, the
feature doesn't exist.

**Independent Test**: Ingest `data/example/`'s vacancy folders, paste JD text that closely
matches one of the ingested postings, call `/similar`, and confirm that posting's vacancy comes
back with its correct company/position/outcome and a high similarity score.

**Acceptance Scenarios**:

1. **Given** a populated vacancy index containing a posting for "Backend Engineer at Acme
   Corp," **When** the user pastes JD text that is nearly identical to that posting, **Then**
   the response includes that vacancy with its outcome and a high similarity score, ranked
   first.
2. **Given** a populated vacancy index, **When** the user pastes JD text unrelated to anything
   ingested, **Then** the response does not surface unrelated vacancies as if they were close
   matches.
3. **Given** a populated vacancy index with several postings, **When** the user pastes JD text,
   **Then** the response is ordered from most to least similar.

---

### User Story 2 - Flag when this looks like the exact same role at the same company (Priority: P2)

As the user, when the pasted JD is for the same company and essentially the same position as
one I've already logged, I want that called out distinctly from "generally similar" matches, so
I don't accidentally re-apply somewhere I already have a result for.

**Why this priority**: The README specifically frames this as a "dedupe" feature, not just a
similarity search — the sharpest, highest-value signal is "you already did this exact one,"
which is easy to miss if it's buried in a generic ranked list.

**Independent Test**: Ingest a vacancy for "Company X — Role Y," paste JD text for the same
company and role (different posting wording), call `/similar`, and confirm the response
distinctly marks it as an exact/near-exact company+role match rather than only a generic
similarity score.

**Acceptance Scenarios**:

1. **Given** an ingested vacancy for a specific company and position, **When** the user pastes
   JD text for the same company and the same (or effectively the same) position, **Then** that
   match is distinctly flagged as a likely duplicate application, not just ranked by score.
2. **Given** an ingested vacancy for a specific company but a clearly different position,
   **When** the user pastes JD text for that company in a different role, **Then** the match is
   NOT flagged as a duplicate, even if it appears in the similarity results.

---

### User Story 3 - Get a clear "nothing similar yet" result on a fresh or unmatched index (Priority: P3)

As the user, if I haven't ingested anything yet, or nothing in my history resembles the pasted
JD, I get a clear empty result rather than an error or misleading matches.

**Why this priority**: Cold-start and no-match are guaranteed to happen (day one, or a genuinely
novel posting) — the feature must degrade gracefully rather than erroring or showing noise.

**Independent Test**: Call `/similar` against an empty vector index, and separately against a
populated index with JD text unrelated to anything ingested, and confirm both return a valid
empty (or clearly low-confidence) result rather than an error.

**Acceptance Scenarios**:

1. **Given** no vacancies have been ingested yet, **When** the user pastes any JD text, **Then**
   the response is a successful empty result, not an error.
2. **Given** a populated index, **When** the pasted JD text is unrelated to everything ingested,
   **Then** the response does not force irrelevant results into the ranked list just to fill it.

---

### Edge Cases

- What happens when the pasted JD text is empty or whitespace-only? The request should be
  rejected as invalid input rather than embedded and searched.
- What happens when the pasted JD text is nearly identical to a vacancy that was itself
  invalid/conflicting during ingestion (per the Ingestion CLI spec) and therefore was never
  embedded? It simply won't appear in results — retrieval only sees what was successfully
  ingested.
- What happens when two or more ingested vacancies are near-equally similar to the pasted JD?
  All of them within the requested result count are returned, ordered by similarity.
- How does the system handle a JD that is itself a near-duplicate of the CURRENT posting being
  pasted twice in the same session? No special-casing — this is the intended "dedupe" behavior,
  not an edge case to suppress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept pasted job-posting text and return a ranked list of the
  most similar previously-ingested vacancies.
- **FR-002**: Each returned match MUST include, at minimum: the matched vacancy's identity,
  company, position, outcome, and a similarity score.
- **FR-003**: Results MUST be ordered from most to least similar.
- **FR-004**: The system MUST compare the pasted JD only against previously-ingested posting
  content (not correspondence or internal analysis notes), so unrelated internal notes don't
  produce false matches.
- **FR-005**: The system MUST reject empty or whitespace-only JD text as invalid input rather
  than attempting to search with it.
- **FR-006**: The system MUST return a successful, valid empty result (not an error) when no
  vacancies have been ingested yet or none are meaningfully similar to the pasted text.
- **FR-007**: The system MUST omit matches whose similarity falls below a minimum confidence
  threshold, rather than always returning a fixed number of results regardless of relevance —
  a weak, low-confidence match must not be presented as if it were a meaningful similarity.
- **FR-008**: The system MUST distinctly flag a match on the same company and effectively the
  same position as a likely duplicate application, separately from the generic similarity
  ranking (User Story 2) — this signal MUST be identifiable in the response independent of the
  similarity score.
- **FR-009**: Each returned match MUST include a short excerpt of the matched posting's text, so
  the user can visually confirm the match themselves without opening the original vacancy
  folder.

### Key Entities *(include if feature involves data)*

- **Similar vacancy match**: One previously-ingested vacancy returned as a result — carries the
  vacancy's identity, company, position, outcome, a similarity score relative to the pasted JD
  text, a short excerpt of the matched posting text, and a flag indicating whether this looks
  like a duplicate application (same company + effectively the same position).
- **Pasted job description**: The raw text the user provides for this single request; not
  persisted by this feature (persisting a new posting is the Ingestion CLI's `/ingest/vacancy`
  concern, not this one).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who pastes a JD nearly identical to a vacancy they've already logged sees
  that exact vacancy, with its outcome, at or near the top of the results.
- **SC-002**: A user pasting a JD unrelated to their history does not see irrelevant past
  vacancies presented as close matches — weak matches are omitted rather than padded in.
- **SC-003**: A user gets a response for any pasted JD — including on a completely empty
  history — without encountering an error.
- **SC-004**: Results consistently come back ordered by similarity, so the most relevant match
  is always first.
- **SC-005**: When a pasted JD is essentially the same company and position as one already
  logged, the user can identify that it's a likely duplicate application directly from the
  response, without having to compare similarity scores themselves.
- **SC-006**: For every match returned, the user can see enough of the original posting text to
  judge the match's relevance themselves, without leaving the response to look up the original
  vacancy folder.

## Assumptions

- This feature is retrieval-only: it reads the vacancy index that the Ingestion CLI ([[001-ingestion-cli]])
  already populates; it does not ingest, create, or modify any vacancy folder or index entry.
- Comparisons are scoped to `doc_type=posting` chunks only, per the existing retrieval metadata
  contract (`retriever.py`) — correspondence and analysis notes are excluded from matching to
  avoid unrelated internal notes producing false matches.
- This feature is exposed as the existing `POST /similar` HTTP endpoint only; no new CLI command
  is introduced (the README documents `/similar` strictly as an API endpoint).
- The default number of results returned matches the existing scaffold's default (3), unless
  changed during planning.
- Vacancy folders that were invalid or conflicting during ingestion (Ingestion CLI FR-008/FR-009)
  were never embedded and therefore cannot appear in results — no additional handling is needed
  here for that case.
- The specific minimum-similarity threshold (FR-007) and the specific rule for "effectively the
  same position" (FR-008, e.g. exact string match vs. a looser comparison) are implementation
  parameters to be chosen during planning, not user-facing business rules — this spec only
  requires that both mechanisms exist and are exercised by the acceptance scenarios above.
