# Implementation Plan: `/similar` Retrieval

**Branch**: `002-similar-retrieval` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-similar-retrieval/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Implement the `POST /similar` endpoint already stubbed in `api.py`: embed the pasted JD text,
query the `vacancies` Chroma collection's `doc_type=posting` chunks (populated by the Ingestion
CLI, [[001-ingestion-cli]]), group hits by vacancy natural key, filter out weak matches below a
minimum similarity threshold, flag same-company+same-position hits as likely duplicates, and
return each match with company/position/outcome/similarity/excerpt/duplicate-flag — purely
read-only against the existing index, no new ingestion or storage introduced.

## Technical Context

**Language/Version**: Python 3.11 (unchanged from [[001-ingestion-cli]])

**Primary Dependencies**: `chromadb` (query against the existing `vacancies` collection via
`ChromaStore`), `sentence-transformers` (via the existing `Embedder` ABC, to embed the pasted
JD text), `pydantic` (extend `SimilarVacancy`), `FastAPI` (wire the existing `/similar` stub)

**Storage**: Reads the existing `.cache/chroma` `vacancies` collection populated by the
Ingestion CLI; this feature introduces no new persisted storage and performs no writes

**Testing**: `pytest` + `httpx`/FastAPI `TestClient` (existing dev deps, matching
`tests/test_api.py`'s existing pattern)

**Target Platform**: Same as [[001-ingestion-cli]] — bare CLI/API process or the existing Docker
image/compose service

**Project Type**: Single project — extends the existing `src/vacancy_radar/` package

**Performance Goals**: Not a target for this feature (Constitution IV); correctness of ranking
and threshold behavior matters more than query latency at the project's stated scale

**Constraints**: Fully offline-capable (JD text is embedded locally via the existing `Embedder`,
no network calls introduced, per Constitution I/III); read-only — MUST NOT modify the Chroma
store or any vacancy source file (Constitution VI)

**Scale/Scope**: Same single-user, low-thousands-of-chunks scale as [[001-ingestion-cli]]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | Reads only the local `.cache/chroma` store; embeds JD text locally via the existing `Embedder`; no network calls | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | Not generation (no LLM claim produced here); the required excerpt (FR-009) and vacancy identity on every match keep the same spirit — every claim ("this is similar") is traceable to a real stored chunk | PASS (N/A to this feature's own output, consistent with the principle) |
| III. Pluggable, Provider-Agnostic LLM | No `LLMProvider` use at all; only the existing `Embedder` ABC, already provider-agnostic | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | Uses Chroma's own `query()` (no custom ANN/vector math); duplicate-flag rule is a simple normalized string match, not fuzzy matching (research.md) | PASS |
| V. Test & Lint Gates | Plan requires `ruff` clean + `pytest` coverage for retrieval, threshold, and duplicate-flag logic before considered done | PASS (enforced in tasks) |
| VI. Regenerable Derived State | Read-only feature — makes zero writes to the Chroma store or manifest; a schema-version bump for the collection's distance-metric config (research.md) is handled entirely through the existing compat-stamp auto-reindex mechanism, not by hand-editing the store | PASS |

No violations — Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── retriever.py       # existing stub — implement query_similar_vacancies() here
├── chroma_store.py     # existing — add a query() method
├── api.py                # existing — wire the POST /similar stub to the retriever
├── models.py               # existing — extend SimilarVacancy (excerpt, is_duplicate)
├── compat.py                 # existing — bump CURRENT_STAMP.schema_version (research.md)
└── ingest.py                   # unchanged — only VACANCIES_COLLECTION/doc_type constants referenced

tests/
├── test_api.py         # existing, extended with /similar tests
└── test_retriever.py    # NEW — query_similar_vacancies unit tests (threshold, ranking,
                          #        dedup-by-natural-key, duplicate-flag, excerpt)
```

**Structure Decision**: Single project (Option 1), same as [[001-ingestion-cli]] — extends the
existing flat `src/vacancy_radar/` package and flat `tests/` directory; no new modules beyond
what's needed to fill in the two existing stubs (`retriever.py`, the `/similar` route).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table not needed.

**Post-Design re-check** (after Phase 1 data-model.md/contracts/quickstart.md): grouping-by-
natural-key, threshold filtering, and the duplicate-flag string match are all pure in-memory
logic over data already in the existing collection — no new writes, no new external calls, no
new persisted personal data. All six gates above still PASS unchanged.
