# Implementation Plan: `/analyze` Full Report Generation

**Branch**: `003-analyze-report-generation` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-analyze-report-generation/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Implement the `POST /analyze` endpoint already stubbed in `api.py`: retrieve relevant CV bullets
(new `Retriever.query_bullets()`) and similar vacancies (existing, [[002-similar-retrieval]]),
read the user's optional filter-rules file, prompt whichever configured `LLMProvider` (Claude or
Ollama) for a structured candidate report, then run that candidate through one shared,
provider-agnostic grounding validator that strips any flag or draft-paragraph sentence whose
cited quote doesn't verbatim-match a retrieved bullet or filter rule — before it ever reaches
the HTTP response. Both `ClaudeProvider` and `OllamaProvider` get real implementations behind
the same interface, satisfying Constitution Principle III.

## Technical Context

**Language/Version**: Python 3.11 (unchanged from [[001-ingestion-cli]] / [[002-similar-retrieval]])

**Primary Dependencies**: `anthropic` (already a dependency, v0.120.2 installed — supports
`output_config.format` structured outputs); `httpx` (already installed transitively, but must
move from dev-only to a main dependency since `OllamaProvider` calls it at runtime, not just in
tests); existing `Retriever`/`ChromaStore`/`Embedder` from [[001-ingestion-cli]] and
[[002-similar-retrieval]]; `FastAPI` (wire the existing `/analyze` stub)

**Storage**: Reads the existing `.cache/chroma` `experience_bullets` and `vacancies`
collections; reads an optional user-authored plain-text filter-rules file (path convention
`data/user/filter-rules.md`, analogous to `CV_DIR`). No new persisted storage; this feature
performs no writes to the vector store.

**Testing**: `pytest` + FastAPI `TestClient` (existing pattern); LLM provider calls are mocked
in tests — no real network calls to Anthropic/Ollama in the automated suite (matching
[[001-ingestion-cli]]/[[002-similar-retrieval]]'s pattern of injectable fakes, plus one manual
quickstart pass against the real providers, per Constitution V)

**Target Platform**: Same as prior features — bare CLI/API process or the existing Docker
image/compose service (including the `local` profile running Ollama)

**Project Type**: Single project — extends the existing `src/vacancy_radar/` package

**Performance Goals**: Not a target for this feature (Constitution IV); grounding correctness
matters far more than latency — an LLM round trip is expected to dominate response time
regardless of implementation choices here

**Constraints**: MUST work identically (same Report structure, same grounding guarantee)
regardless of configured `LLM_PROVIDER` (Constitution III); MUST NOT include any claim in the
response that isn't traceable to a retrieved bullet or filter rule, enforced centrally rather
than trusted to each provider (Constitution II, NON-NEGOTIABLE); read-only against the vector
store (Constitution VI)

**Scale/Scope**: Same single-user scale as prior features; one `/analyze` call = one JD, a
handful of retrieved bullets (top 5) and similar vacancies (top 3), one LLM round trip

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | Reads only local `.cache/chroma` and the user's own filter-rules file; the Claude path does send JD text + retrieved bullets to the Anthropic API (unavoidable for that backend, per Constitution III's own design), but the Ollama path keeps everything local — the user chooses via `LLM_PROVIDER` | PASS (offline mode fully available; hosted mode's data flow is the explicit, documented tradeoff of choosing it) |
| II. Grounded Generation (NON-NEGOTIABLE) | This feature's entire purpose is grounding enforcement — every flag and draft-paragraph sentence is validated against a retrieved bullet or filter rule by one shared, provider-agnostic checkpoint before the response is returned (research.md) | PASS — this is the principle's primary implementation site |
| III. Pluggable, Provider-Agnostic LLM | Both `ClaudeProvider` and `OllamaProvider` implement the same `LLMProvider.analyze()` signature; the grounding checkpoint lives outside both providers, so neither can bypass it | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | One shared grounding validator (substring match) instead of two divergent provider-specific mechanisms; match band derived by the LLM against an embedded rubric instead of a hand-built scoring engine | PASS |
| V. Test & Lint Gates | Plan requires `ruff` clean + `pytest` coverage for the grounding validator, bullet retrieval, and both providers (via fakes) before considered done, plus one manual pass against real Claude/Ollama | PASS (enforced in tasks) |
| VI. Regenerable Derived State | Read-only feature — no writes to `.cache/chroma` or the manifest; bumps `compat.CURRENT_STAMP.schema_version` again (research.md) since bullet retrieval also needs cosine space, handled by the existing auto-reindex mechanism | PASS |

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
├── retriever.py        # existing — implement query_bullets(); add cosine metadata for bullets
├── ingest.py             # existing — add BULLETS_COLLECTION_METADATA (cosine), wire into upsert/reset
├── compat.py               # existing — bump CURRENT_STAMP.schema_version again (research.md)
├── models.py                 # existing — change Report.score to a MatchBand literal; add Gap? (see data-model.md)
├── grounding.py                # NEW — shared, provider-agnostic citation/claim validator
├── filter_rules.py               # NEW — read the optional user filter-rules file
├── llm/
│   ├── base.py                     # existing interface — unchanged signature
│   ├── claude.py                     # existing stub — implement via output_config.format
│   └── ollama.py                       # existing stub — implement via local HTTP call + lenient JSON parse
└── api.py                                # existing — wire POST /analyze: retrieve → prompt → validate → respond

tests/
├── test_grounding.py    # NEW — the shared validator's stripping behavior
├── test_retriever.py     # extended — query_bullets() tests
└── test_api.py             # extended — /analyze tests, LLMProvider faked via dependency override

pyproject.toml
└── move `httpx` from `[project.optional-dependencies].dev` to `[project].dependencies`
    (OllamaProvider needs it at runtime, not just in tests)
```

**Structure Decision**: Single project (Option 1), same as [[001-ingestion-cli]] and
[[002-similar-retrieval]] — extends the existing flat `src/vacancy_radar/` package and flat
`tests/` directory. Two new modules (`grounding.py`, `filter_rules.py`) are added because they
are genuinely new, shared concerns — not per-provider logic — that both `ClaudeProvider` and
`OllamaProvider` depend on.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table not needed.

**Post-Design re-check** (after Phase 1 data-model.md/contracts/quickstart.md): the grounding
validator is pure in-memory string matching over data already retrieved; the filter-rules
reader is a single optional local file read. Neither introduces a new external call, new
persisted data, or a way to bypass Constitution II. All six gates above still PASS unchanged.
