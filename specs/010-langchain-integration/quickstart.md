# Quickstart: Migrate Generation and Retrieval to LangChain

This is a preserve-behavior migration — the quickstart is about proving *nothing changed* from
a user's perspective.

## Prerequisites

- `pip install langchain-core langchain-anthropic langchain-ollama langchain-chroma
  langchain-huggingface` (already verified installable and mutually compatible during planning).
- A working `LLM_PROVIDER`-equivalent setup (Claude API key, or a local Ollama).
- The existing `data/example` fixtures ingested fresh (`vacancy-radar ingest`) against the
  migrated code — there's no in-place store to migrate, since nothing real currently depends on
  the pre-migration embedding output (research.md #6).

## Scenario 1 — Match report generation, unchanged shape

1. `POST /api/analyze` (or paste on `/`) with a real job posting against ingested `data/example`
   bullets.

**Expected**: a `Report` with the same fields as before (score, flags, gaps, similar, draft
paragraph, draft_sentences, citations); every flag/draft sentence's `quote` is still verifiably
present in the source bullet/filter-rule text (grounding unchanged).

## Scenario 2 — Vacancy metadata drafting, both text and vision paths

1. Upload a text/PDF/DOCX posting on `/ingest` — confirm company/position/date draft the same
   way as before.
2. Upload an image posting — confirm the vision path still works, using the new shared
   `build_vision_message()` helper for both Claude and Ollama.

**Expected**: identical drafting behavior to specs/006/specs/007's original quickstart
scenarios.

## Scenario 3 — Ollama's retry-on-invalid-JSON still works

1. With Ollama configured against a model prone to occasionally malformed JSON, trigger drafting
   or analysis enough times to observe (or simulate via a fake that fails once) a retry.

**Expected**: the same one-retry-then-fail behavior as today — confirmed via a unit test with a
fake `ChatOllama` that returns invalid output once, then valid output, exercising
`Runnable.with_retry()` (research.md #2) rather than a hand-rolled retry loop.

## Scenario 4 — Similar-vacancy retrieval, same rankings

1. `POST /api/similar` with a posting similar to one already ingested.

**Expected**: the same vacancy is returned, with a comparable similarity score and the same
`is_duplicate` classification as before the migration (contracts/retrieval-langchain.md).

## Scenario 5 — Both backends still work, selected the same way

1. With `ANTHROPIC_API_KEY` set, confirm Claude is used (unchanged from specs/010-preceding
   auto-detect design).
2. With it unset, confirm Ollama is used, and the fully local/offline path still produces a
   report/draft.

## Automated coverage

Full existing `pytest` suite (updated to fake `BaseChatModel`/`Chroma` at the new boundary) plus
`eval/run_eval.py`'s four checks (grounding enforcement, bullet-retrieval recall@5/MRR,
similar-vacancy precision@3, filter-rule consistency) — this is the actual regression gate
(spec.md FR-007/SC-001): the migration is not done until these pass at parity with pre-migration
results, not just until new code compiles.
