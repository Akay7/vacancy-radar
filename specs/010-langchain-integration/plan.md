# Implementation Plan: Migrate Generation and Retrieval to LangChain

**Branch**: `010-langchain-integration` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-langchain-integration/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Replace the hand-rolled `LLMProvider` ABC (`ClaudeProvider`/`OllamaProvider` over the raw
`anthropic` SDK and raw `httpx`) with LangChain's `BaseChatModel` (`ChatAnthropic`/`ChatOllama`),
and replace the hand-rolled `ChromaStore`/`Retriever` wrapper with `langchain-chroma`'s `Chroma`
vector store plus `langchain-huggingface`'s `HuggingFaceEmbeddings`. Verified directly against
the installed packages (not assumed) before writing this plan: both chat models accept the
exact same standardized image content block for vision calls (one shared helper instead of two
provider-specific request builders); `.with_structured_output(PydanticModel, method="json_schema")`
returns a validated Pydantic instance directly for both providers, eliminating the manual
`json.loads` + `model_validate` step, and composes with LangChain's own `Runnable.with_retry()`
to reproduce Ollama's retry-on-invalid-output behavior without any hand-rolled retry loop;
`Chroma.similarity_search_with_relevance_scores(query, k=, score_threshold=, filter=)` implements
exactly the minimum-similarity-cutoff-plus-doc_type-filter behavior `retriever.py` hand-rolls
today, using the *same* cosine-distance-to-score formula (`1 - distance`) already assumed by
`MIN_SIMILARITY`'s calibration comment — confirmed by reading both collections' existing
`hnsw:space: cosine` metadata. One real behavior difference was found and is noted rather than
silently accepted: `HuggingFaceEmbeddings` strips newlines from text before encoding and the
current `SentenceTransformersEmbedder` does not. This is not addressed with a `compat.py`
version-stamp bump, since no tagged release or real running installation currently depends on
today's embedding output to protect — `vacancy-radar reindex` remains the correct manual remedy
if it ever matters.

## Technical Context

**Language/Version**: Python 3.11 (unchanged).

**Primary Dependencies**: New — `langchain-core`, `langchain-anthropic`, `langchain-ollama`,
`langchain-chroma`, `langchain-huggingface` (all verified installable and compatible with the
installed `anthropic`/`chromadb`/`sentence-transformers` versions during research). Removed —
no packages are removed; `anthropic`, `chromadb`, `sentence-transformers`, `httpx` remain as
transitive dependencies of the LangChain integration packages themselves (`httpx` also still
used elsewhere, e.g. `documents.py`... actually not — verify at implementation time and drop
only if genuinely unused after migration).

**Storage**: No new persisted state. The same on-disk `.cache/chroma` embedded/persistent
directory is reused — `Chroma(client=<shared chromadb.PersistentClient>, collection_name=...,
embedding_function=...)` wraps the existing collections in place, verified to correctly detect
their existing `hnsw:space: cosine` configuration. No `compat.py` version-stamp bump is part of
this migration (see Summary) — `vacancy-radar reindex` remains available as a manual remedy if
ever needed.

**Testing**: `pytest`, same fake-provider-at-the-boundary pattern as every prior feature —
fakes move from mocking `anthropic.Messages.create`/`httpx.post` directly to mocking/faking
`BaseChatModel.invoke()`/`.with_structured_output()` and `Chroma`'s scored-search methods.
Ollama's connection-failure exception type is confirmed, not guessed: ran `ChatOllama(base_url=
"http://127.0.0.1:1").invoke(...)` against a genuinely unreachable port — `httpx.ConnectError`
propagates unchanged, so today's `except httpx.HTTPError` catch needs no change.

**Target Platform**: Same as today — single `app` service, no new container/port.

**Project Type**: Web application — single FastAPI project (unchanged).

**Performance Goals**: No explicit target changes. LangChain's structured-output path for Claude
uses the same underlying `json_schema` mechanism as today's `output_config.format`, so latency
is expected to be equivalent; this is validated in quickstart.md rather than assumed.

**Constraints**: Every functional requirement in spec.md (FR-001 through FR-009) is a
preserve-existing-behavior constraint — this migration ships only when the eval harness and full
test suite pass at parity (FR-007, SC-001).

**Scale/Scope**: Every file in `src/vacancy_radar/llm/` is rewritten; `retriever.py` and
`chroma_store.py` are rewritten (`chroma_store.py` may be deleted outright if `Chroma` fully
replaces its role — confirmed during implementation); `embedder.py`'s custom `Embedder` ABC is
removed in favor of `langchain_core.embeddings.Embeddings` directly (research.md #7);
`tests/_fakes.py`'s fakes are updated to that interface too; `api.py`'s
`get_llm_provider()`/`get_retriever()`/`get_embedder()` dependency functions and `run_analysis()`
are updated to the new types; every test file that fakes an LLM provider or the retriever/store
(`test_llm_claude.py`, `test_llm_ollama.py`, `test_api.py`, `test_ui.py`,
`test_ingest_upload.py`, `test_retriever.py`) is
updated to fake the new interfaces. `compat.py` is untouched — no `schema_version` bump (see
Summary).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | No change to what leaves the machine — LangChain's chat models call the exact same Claude API / local Ollama host as today; `langchain-chroma`/`langchain-huggingface` are local libraries, no telemetry call is introduced (verified: no network calls in `HuggingFaceEmbeddings`/`Chroma` beyond the model download already required today). | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | `grounding.enforce()` is untouched — it operates on `CandidateReport`, whose shape is unchanged; FR-004 requires citation-checking to survive the migration unchanged, and this is the primary regression gate (FR-007, eval harness). | PASS |
| III. Standard Integration Layers via LangChain | This feature *is* Principle III's compliance work — `BaseChatModel` (`ChatAnthropic`/`ChatOllama`) for generation, `Chroma`/`VectorStore` for retrieval, exactly as the amended constitution requires. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | Five new dependencies, but each is the specific package the constitution names, not a broader adoption of LangChain's ecosystem (no agent framework, no additional document loaders) — matches Principle IV's own carve-out language. The migration is verified (via research.md) to reduce hand-written code, not add abstraction for hypothetical scale. | PASS |
| V. Test & Lint Gates | Full test suite + eval harness must pass at parity before this ships (FR-007/SC-001) — a stricter bar than usual, since this is a preserve-behavior migration, not new functionality. | PASS |
| VI. Regenerable Derived State | Unaffected — the store remains upsert-keyed and deletable/rebuildable from source exactly as today. The embedder's newline-stripping difference (research.md #6) is a noted behavior change, not a data-loss risk: `vacancy-radar reindex` already exists as the sanctioned remedy, and no real running installation currently depends on today's embedding output to protect, so no additional enforcement is warranted. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were
written): unchanged — every design decision either preserves existing behavior exactly or routes
a genuine behavior change (the embedder's newline handling) through the constitution's own
existing mechanism (VI) rather than around it.*

## Project Structure

### Documentation (this feature)

```text
specs/010-langchain-integration/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── llm/
│   ├── base.py               # rewritten: LLMProvider ABC removed; a shared
│   │                          #   build_vision_content(image_bytes, image_media_type) -> list
│   │                          #   helper replaces the two hand-built request shapes (both
│   │                          #   ChatAnthropic and ChatOllama accept the same standard
│   │                          #   ImageContentBlock — verified in research.md #1)
│   ├── claude.py               # rewritten: ChatAnthropic(model=...).with_structured_output(
│   │                           #   CandidateReport / DraftVacancyMetadata, method="json_schema")
│   │                           #   replaces the manual messages.create()+output_config+json.loads
│   │                           #   calls; anthropic.APIConnectionError/AuthenticationError/
│   │                           #   APIError still caught around .invoke() (verified unchanged —
│   │                           #   research.md #3) and re-raised as LLMProviderError
│   ├── ollama.py                # rewritten: ChatOllama(model=...).with_structured_output(...,
│   │                            #   method="json_schema") replaces the raw httpx.post + manual
│   │                            #   "format": "json" + retry-on-invalid-JSON loop; the one-retry
│   │                            #   rule is explicitly reimplemented (LangChain doesn't auto-retry
│   │                            #   — research.md #2), catching OutputParserException
│   ├── prompts.py                # unchanged in spirit — prompt text stays the same; JSON-schema
│   │                             #   dicts (CANDIDATE_REPORT_JSON_SCHEMA etc.) may be replaced by
│   │                             #   passing the Pydantic models directly to
│   │                             #   with_structured_output(), removing the hand-written schemas
│   └── config.py                 # unchanged (specs/009's LLMConfig — provider selection by
│                                  #   ANTHROPIC_API_KEY presence is orthogonal to this migration)
├── retriever.py                   # rewritten: query_bullets()/query_similar_vacancies() call
│                                  #   Chroma.similarity_search_with_score() /
│                                  #   .similarity_search_with_relevance_scores(k=, score_threshold=,
│                                  #   filter=) instead of ChromaStore.query(); natural-key
│                                  #   deduplication and the duplicate-flag threshold remain
│                                  #   hand-written Python on the returned (Document, score) pairs
│                                  #   (research.md #4 — no LangChain equivalent exists)
├── chroma_store.py                 # likely deleted — its role (wrapping the chromadb client) is
│                                   #   fully absorbed by langchain-chroma's Chroma; confirmed
│                                   #   during implementation whether anything still needs it
│                                   #   directly (e.g. ingest.py's upsert path — see research.md #5)
├── embedder.py                      # custom Embedder ABC removed (research.md #7); returns
│                                    #   HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
│                                    #   — a langchain_core.embeddings.Embeddings instance — directly
└── api.py                            # get_llm_provider()/get_retriever()/get_embedder() return
                                     #   the new types; run_analysis() and ingest_draft()/
                                     #   ui_analyze()'s calls to .analyze()/.draft_vacancy_metadata()/
                                     #   .extract_document_text() are updated to whatever the new
                                     #   shared calling convention is (still one call site per
                                     #   concern — Constitution III unchanged in spirit)

tests/
├── _fakes.py                          # FakeEmbedder/BagOfWordsEmbedder subclass
│                                      #   langchain_core.embeddings.Embeddings
│                                      #   (embed_documents/embed_query) instead of Embedder
├── test_llm_claude.py                # rewritten: fakes BaseChatModel/.with_structured_output()
│                                     #   instead of the raw anthropic SDK client
├── test_llm_ollama.py                 # rewritten: fakes ChatOllama instead of raw httpx.post
├── test_retriever.py                   # updated: existing real-Chroma-backed tests (via
│                                      #   BagOfWordsEmbedder) keep passing against Retriever's
│                                      #   new Chroma-backed internals — same assertions, same
│                                      #   fixture shape, since the public API is unchanged
├── test_api.py, test_ui.py, test_ingest_upload.py  # updated: dependency-override fakes conform
│                                      #   to the new call signatures
└── (eval/run_eval.py fixtures unchanged — it exercises the public retriever/LLM functions, not
    their internals, so its golden fixtures are the regression gate, not something to edit)
```

**Structure Decision**: Single project (unchanged). No new services, no new top-level
directories — this is a like-for-like internal rewrite of `llm/`, `retriever.py`,
`chroma_store.py`, and `embedder.py` behind their existing call sites in `api.py`.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
