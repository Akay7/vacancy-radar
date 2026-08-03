# Feature Specification: Eval Harness

**Feature Branch**: `004-eval-harness`

**Created**: 2026-08-01

**Status**: Draft

**Input**: User description: "Eval harness (grounding check, retrieval recall/MRR, similar-vacancy precision, filter-consistency)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Grounding enforcement check (Priority: P1)

As the maintainer, I want to run a check that confirms citations in a curated set of example match reports are verified correctly — fabricated claims rejected, genuinely grounded claims kept — so that changes to prompts, providers, or the grounding logic can never silently start leaking ungrounded claims into a real report (Constitution Principle II, non-negotiable).

**Why this priority**: Grounding is the one non-negotiable correctness property of this project. A regression here is the single worst thing that could ship silently, so it's the first thing the harness must guard.

**Independent Test**: Run the eval command with only the grounding-check fixtures present (no ingested bullets or vacancies needed); it reports pass/fail per fixture and an aggregate score on its own.

**Acceptance Scenarios**:

1. **Given** a curated set of example candidate reports where each claim is labeled "genuinely grounded" or "fabricated", **When** the grounding check runs, **Then** every fabricated-labeled claim is reported as rejected and every genuinely-grounded claim is reported as kept.
2. **Given** a curated candidate report whose claim's outcome doesn't match its label, **When** the grounding check runs, **Then** that fixture is reported as a discrepancy for the maintainer to review, not silently ignored or averaged away.

---

### User Story 2 - Retrieval recall/MRR check (Priority: P2)

As the maintainer, I want to measure how well experience-bullet retrieval surfaces the right prior experience for known job-description-style queries, so degradations in the embedding or retrieval pipeline are caught before they affect real match reports.

**Why this priority**: Retrieval quality directly bounds report quality — an LLM cannot cite bullets it was never given — but a regression here degrades results rather than corrupting correctness, so it ranks below grounding.

**Independent Test**: Run the eval command against its own small set of example experience bullets and a labeled list of (query, expected relevant bullet ids); it reports recall@k and MRR without needing any vacancy history or LLM report generation.

**Acceptance Scenarios**:

1. **Given** a labeled query with known relevant bullets ingested, **When** the retrieval check runs, **Then** it reports whether each expected bullet appeared in the top-k results and computes recall@k and MRR across all labeled queries.
2. **Given** a labeled query whose expected bullet was never actually ingested, **When** the retrieval check runs, **Then** it flags the missing fixture as a data problem rather than silently scoring it the same as a real retrieval miss.

---

### User Story 3 - Similar-vacancy precision check (Priority: P3)

As the maintainer, I want to measure whether `/similar` surfaces genuinely similar past vacancies — not just topically-related noise — for known postings, so I can trust its "you saw this before" signal.

**Why this priority**: This affects the usefulness of a secondary, lower-stakes signal (dedup/memory), not correctness of the generated report itself.

**Independent Test**: Run the eval command against its own small set of example vacancies and a labeled set of "these two postings are truly similar" pairs; it reports precision@k for similar-vacancy retrieval on its own.

**Acceptance Scenarios**:

1. **Given** a labeled posting with known truly-similar prior vacancies ingested, **When** the similar-vacancy check runs, **Then** it reports the fraction of top-k results that are labeled truly similar (precision@k) for that posting and in aggregate across all labeled postings.

---

### User Story 4 - Filter-rule consistency check (Priority: P4)

As the maintainer, I want to confirm that a real filter-rule violation is reliably surfaced as a grounded flag, and a fabricated one is reliably rejected, so the filter-rules mechanism doesn't silently stop working after changes elsewhere in the pipeline.

**Why this priority**: This is a narrower slice of the same grounding-enforcement path already covered by User Story 1, focused specifically on the filter-rules source; useful but the smallest independent increment.

**Independent Test**: Run the eval command against a curated set of candidate reports that do or do not reference real filter-rule text; it reports whether each is consistently classified, independent of the other three checks.

**Acceptance Scenarios**:

1. **Given** a curated candidate report that cites a real filter-rule violation verbatim, **When** the filter-consistency check runs, **Then** the flag is reported as correctly retained.
2. **Given** a curated candidate report that fabricates a filter-rule citation not present in the actual filter-rules text, **When** the filter-consistency check runs, **Then** the flag is reported as correctly rejected.

---

### Edge Cases

- What happens when the fixture set for one check is missing or empty? The harness reports that check as skipped/no-data, distinct from a passing or failing score.
- How does the system handle a labeled fixture that references a bullet or vacancy id no longer present in the harness's own ingested example data (e.g., a stale or typo'd fixture)? It is reported as a fixture/data error, distinct from a genuine retrieval or grounding miss.
- What happens when a check's aggregate score falls below its configured threshold? The run reports that check as failing and produces an overall failing status, while still reporting the other checks' results in full.
- What happens when the harness is run from a fresh clone with nothing pre-ingested? It ingests its own bundled example fixtures as part of the run, rather than failing because the maintainer's real data isn't present.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single command that runs all four checks (grounding, retrieval recall/MRR, similar-vacancy precision, filter-consistency) and produces one combined report.
- **FR-002**: The system MUST allow each check to be run individually, so a maintainer can iterate on one area without waiting on the others.
- **FR-003**: The system MUST ship with its own checked-in, maintained set of labeled example fixtures for each check (candidate reports labeled grounded/fabricated; queries with expected relevant bullet ids; vacancy pairs labeled truly-similar or not; filter-rule violation and non-violation examples), so it is runnable out of the box without the maintainer's private data.
- **FR-004**: The system MUST produce all four checks' metrics using only local, deterministic components (the local embedding model and the grounding-enforcement logic) and MUST NOT require a live generative-LLM call or network access.
- **FR-005**: For each check, the system MUST report an aggregate score (grounding precision/recall, retrieval recall@k and MRR, similar-vacancy precision@k, filter-consistency accuracy) and the specific fixtures that failed, with the reason.
- **FR-006**: The system MUST report an overall failing status when any check's aggregate score falls below its configured threshold, so it can be used as a gate alongside the project's existing lint and test gates.
- **FR-007**: The system MUST distinguish a check failure caused by a fixture/data problem (e.g., a stale reference, a malformed fixture) from a check failure caused by a genuine quality regression, and report them differently.
- **FR-008**: The system MUST NOT read, mutate, or depend on the maintainer's real private CV or vacancy data, and MUST NOT share the regenerable cache used by real ingestion — it operates only on its own dedicated fixture data.

### Key Entities

- **Eval Fixture Set**: The checked-in collection of labeled examples for one check type — grounding candidate reports with ground-truth labels, retrieval queries with expected bullet ids, vacancy-similarity pairs with expected labels, or filter-rule violation examples.
- **Eval Report**: The result of a harness run — per-check aggregate metrics, the list of failing fixtures with reasons, and an overall pass/fail status.
- **Metric Threshold**: The configured minimum acceptable value for a given metric, used to decide whether a check passes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can run the full eval suite from a fresh clone, using only the bundled example fixtures, and get a complete report in under 1 minute with no external API keys or network access required.
- **SC-002**: The eval report distinguishes passing from failing checks clearly enough that a maintainer can identify which of the four quality dimensions regressed without reading the harness's own code.
- **SC-003**: Deliberately introducing a grounding-enforcement bug (e.g., disabling the verbatim-quote check) causes the grounding check to fail in the eval report, demonstrating the harness catches real regressions rather than always passing.
- **SC-004**: The eval suite can be run as part of the project's existing automated gate (alongside lint and tests) and reports an overall failing status when any check regresses below its threshold.

## Assumptions

- The eval harness is a maintainer/developer-facing tool. Throughout this spec, "user" means the project maintainer validating quality — not the job-seeker end user of `/analyze` and `/similar`.
- All four checks can be implemented without invoking a live generative LLM: the grounding and filter-consistency checks exercise the deterministic grounding-enforcement logic directly against curated candidate-report-shaped fixtures; the retrieval recall/MRR and similar-vacancy precision checks exercise the deterministic, local-embedding-based retrieval layer. This keeps the harness runnable in CI without secrets, consistent with the project's existing lint/test gates.
- Fixture data is small, hand-curated, and checked into the repository — not the maintainer's private CV or vacancy data — similar in spirit to the existing `data/example/` sanitized demo set.
- Exact per-metric pass thresholds (e.g., what recall@k counts as passing) are an implementation decision made when the harness is built, not a business requirement fixed by this spec; grounding is the one check expected to require a 100% threshold given Principle II.
- "Filter-consistency" is scoped to verifying the grounding-enforcement pipeline's handling of filter-rule citations (real ones kept, fabricated ones rejected) — not to verifying the completeness or correctness of the filter rules' own content.
