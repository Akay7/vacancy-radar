# Feature Specification: `/analyze` Full Report Generation

**Feature Branch**: `003-analyze-report-generation`

**Created**: 2026-08-01

**Status**: Draft

**Input**: User description: "`/analyze` full report generation" (third unchecked item on the README roadmap, building on [[001-ingestion-cli]] and [[002-similar-retrieval]])

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a grounded match assessment for a pasted JD (Priority: P1)

As the user, when I paste a job posting's text, I get back a match score plus red/green flags
and capability gaps — every one of them traceable to a real piece of my experience or one of my
own filter rules — so I can quickly judge whether this posting is worth pursuing without
wondering if the assessment is just made up.

**Why this priority**: This is the headline promise of the whole project ("get a match score
against your CV, red/green flags... grounded in your real experience") and the reason
[[001-ingestion-cli]] and [[002-similar-retrieval]] exist at all — without a trustworthy
assessment, the tool has nothing to offer beyond a search box.

**Independent Test**: Ingest `data/example/`, paste a JD that clearly overlaps with some
ingested experience bullets and clearly lacks others, call `/analyze`, and confirm the
resulting score/flags/gaps reflect that overlap and every flag cites a real bullet or filter
rule that actually supports it.

**Acceptance Scenarios**:

1. **Given** ingested CV bullets that closely match a pasted JD's requirements, **When** the
   user calls `/analyze`, **Then** the report includes a high match score and green flags,
   each citing the specific bullet(s) that justify it.
2. **Given** ingested CV bullets that are missing a requirement the JD asks for, **When** the
   user calls `/analyze`, **Then** the report lists that missing requirement as a gap.
3. **Given** a claim the system would otherwise want to make that has no supporting bullet or
   filter rule, **When** the report is generated, **Then** that claim does not appear in the
   report rather than being included unsupported.

---

### User Story 2 - Get a grounded draft opening paragraph (Priority: P2)

As the user, after seeing the match assessment, I get a draft opening paragraph for my
application that only references things I've actually done, so I have a real starting point
instead of a blank page or a paragraph that invents an achievement I'd have to fact-check myself.

**Why this priority**: The second half of the project's headline promise, and the piece with
the highest cost if grounding fails — a fabricated claim in a cover letter is worse than no
draft at all (this is called out explicitly in the project's own README and constitution).

**Independent Test**: Call `/analyze` with a JD matching some ingested bullets, and confirm the
draft opening paragraph's claims are each traceable to a retrieved bullet, with no invented
achievement, tool, or outcome.

**Acceptance Scenarios**:

1. **Given** ingested CV bullets relevant to the pasted JD, **When** the user calls `/analyze`,
   **Then** the response includes a draft opening paragraph whose claims are all grounded in
   those bullets.
2. **Given** no CV bullets have been ingested at all, **When** the user calls `/analyze`,
   **Then** the response does not include a fabricated draft paragraph — it clearly reflects
   that there was nothing to draft from.

---

### User Story 3 - See similar past vacancies alongside the assessment (Priority: P3)

As the user, I see the same "have I basically seen this one before" information from
`/similar` folded directly into the `/analyze` report, so I get the full picture — match
quality, gaps, draft text, and history — in one response instead of two separate calls.

**Why this priority**: Pure convenience/consolidation on top of already-shipped functionality
([[002-similar-retrieval]]) — valuable, but the tool is still useful without it if the other
two stories work.

**Independent Test**: Call `/analyze` with a JD nearly identical to an already-ingested
vacancy, and confirm the report's similar-vacancies section matches what a direct `/similar`
call for the same text would return.

**Acceptance Scenarios**:

1. **Given** a pasted JD that closely matches an already-ingested vacancy, **When** the user
   calls `/analyze`, **Then** the report includes that vacancy among its similar vacancies,
   with the same outcome/similarity/duplicate-flag information `/similar` would return.

---

### Edge Cases

- What happens when no CV bullets have been ingested yet? The report must not fabricate a
  score, flags, or draft paragraph from nothing — it must clearly reflect that no grounded
  assessment was possible (User Story 2, Scenario 2).
- What happens when the pasted JD text is empty or whitespace-only? The request should be
  rejected as invalid input, matching [[002-similar-retrieval]]'s existing convention.
- What happens when the configured LLM backend (hosted or local) is unreachable or
  misconfigured? The user must see a clear error, not a silent empty or default-looking report.
- What happens when a would-be claim (flag, gap detail, or draft-paragraph sentence) has no
  supporting bullet or filter rule? See FR-008 for the resolved behavior.
- What happens when the pasted JD is itself a near-duplicate of a previously-ingested vacancy
  (dedupe case)? Handled identically to `/similar` (User Story 3) — no special-casing beyond
  what [[002-similar-retrieval]] already does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept pasted job-posting text and return one combined report
  containing: a match score, categorized flags, capability gaps, similar past vacancies, and a
  draft opening paragraph.
- **FR-002**: Every flag and every sentence of the draft opening paragraph MUST be traceable to
  either a retrieved experience bullet or a filter rule; the report MUST record which source
  backs each such claim (Constitution Principle II, non-negotiable).
- **FR-003**: The system MUST retrieve experience bullets relevant to the pasted JD from the
  user's ingested CV data (per [[001-ingestion-cli]]) to serve as grounding material.
- **FR-004**: The system MUST include similar past vacancies in the report, using the same
  ranking, similarity threshold, and duplicate-application flag behavior already defined in
  [[002-similar-retrieval]].
- **FR-005**: The match score MUST be expressed as a small set of categorical match bands
  (e.g., Strong / Good / Weak / Poor match), not a bare numeric percentage — avoiding false
  precision an LLM-derived number would imply. The band MUST be determined via a rubric that
  compares the JD's stated requirements against the user's retrieved experience bullets and
  relevant vacancy history (not an unconstrained free-form judgment), so the score itself is
  grounded the same way flags and the draft paragraph are.
- **FR-006**: Each flag MUST be categorized as red (a concern) or green (a strength) and MUST
  include a plain-language reason.
- **FR-007**: Filter rules are a user-authored file of personal dealbreakers/preferences (e.g.,
  "must be remote," "no on-call rotation"), analogous to CV bullets but distinct from them, read
  as plain text and supplied to the LLM as additional grounding context. The system MUST support
  reading this file (when present) and using its content as a valid citation source for flags,
  per FR-002. An absent filter-rules file is a valid state — the system MUST proceed without one
  rather than treating it as an error.
- **FR-008**: When a would-be claim (flag, gap, or draft-paragraph content) cannot be grounded
  in any retrieved bullet or filter rule, the system MUST silently omit that specific claim and
  continue producing the rest of the report — an ungroundable claim never blocks the whole
  `/analyze` request.
- **FR-009**: The system MUST produce a report of identical structure and grounding guarantees
  regardless of which configured LLM backend (hosted API or local model) generated it, per the
  project's pluggable-provider principle.
- **FR-010**: If no experience bullets have been ingested, the system MUST return a report that
  clearly reflects the absence of grounding material (e.g., no draft paragraph fabricated, no
  unsupported flags) rather than an error or invented content.
- **FR-011**: The system MUST reject empty or whitespace-only JD text as invalid input.
- **FR-012**: The system MUST surface a clear, actionable error when the configured LLM backend
  is unreachable or misconfigured, rather than returning a silently empty or default-looking
  report.

### Key Entities *(include if feature involves data)*

- **Match report**: The combined result of one `/analyze` call — score, flags, gaps, similar
  vacancies, draft opening paragraph, and the citations backing every grounded claim in it.
- **Flag**: A single red or green signal in the report, with a plain-language reason and a
  citation back to the bullet or filter rule that supports it.
- **Gap**: A capability or requirement from the JD that the user's ingested experience does not
  appear to cover.
- **Citation**: A link from a specific claim in the report back to the exact bullet or filter
  rule text that grounds it.
- **Filter rule**: A user-authored personal dealbreaker or preference (e.g., "must be remote"),
  read from a plain-text file the user maintains, usable as grounding material for flags
  alongside experience bullets but distinct from them.
- **Match band**: The categorical result of comparing a JD's requirements against the user's
  retrieved experience (e.g., Strong / Good / Weak / Poor match) — the report's headline
  score, derived from a rubric rather than an unconstrained judgment (FR-005).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user pasting a JD receives one complete report — score, flags, gaps, similar
  vacancies, and a draft paragraph — from a single request.
- **SC-002**: Every claim in a report's flags and draft paragraph can be traced by the user back
  to a specific piece of their real experience or one of their own filter rules — none can be
  traced to nothing.
- **SC-003**: A user with no ingested experience data still receives a valid, non-fabricated
  report rather than an error or invented content.
- **SC-004**: A user gets the same report structure and the same grounding guarantee regardless
  of whether their configured LLM backend is the hosted API or a local model.
- **SC-005**: A user can tell from the flags alone, without reading the full draft paragraph,
  whether a posting looks like a reasonable match for their real experience.
- **SC-006**: A user can look at the match band alone (without reading flags or gaps) and get a
  directionally correct sense of fit — a Strong-match posting and a Poor-match posting are
  clearly distinguishable at a glance.

## Assumptions

- This feature builds directly on [[001-ingestion-cli]] (experience bullets, vacancy ingestion)
  and [[002-similar-retrieval]] (similar-vacancy ranking/threshold/duplicate-flag logic) —
  it adds bullet retrieval and LLM-based report generation on top of both, and does not change
  their existing behavior.
- Per Constitution Principle III (Pluggable, Provider-Agnostic LLM), both the hosted (Claude)
  and local (Ollama) providers already stubbed in the codebase must be implemented — this
  feature is not considered complete with only one backend working.
- This feature is exposed as the existing `POST /analyze` HTTP endpoint only, matching the
  README; no new CLI command is introduced.
- Gaps are inherently statements about *absence* of matching experience (e.g., "no Kubernetes
  experience found in ingested bullets") — they describe what wasn't found rather than making a
  positive claim, so they are not subject to the same per-claim citation requirement as flags
  and draft-paragraph content (FR-002).
- Performance/latency targets are out of scope for this feature (Constitution IV); correctness
  of grounding matters far more than response time at this project's stated scale.
- The exact filter-rules file location/name (e.g., under `data/user/`) and the exact rubric
  criteria used to derive the match band are implementation details to be settled during
  planning, not user-facing business rules fixed by this spec.
