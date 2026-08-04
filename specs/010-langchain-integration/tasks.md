---

description: "Task list for Migrate Generation and Retrieval to LangChain"
---

# Tasks: Migrate Generation and Retrieval to LangChain

**Input**: Design documents from `/specs/010-langchain-integration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/llm-provider-langchain.md, contracts/retrieval-langchain.md, quickstart.md

**Tests**: Included — this repo's established pattern (every prior feature) is tests-first, and
this migration's bar is stricter than usual: FR-007/SC-001 require the full suite and eval
harness to pass at parity, not just green on new code.

**Organization**: Tasks are grouped by user story (US1 = P1 generation, US2 = P2 retrieval) per
spec.md. Foundational work only covers what's genuinely shared (dependencies); US1 and US2 are
otherwise independent of each other's internals.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root (unchanged).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Land the new dependencies before either story touches code that imports them.

- [X] T001 Add `langchain-core`, `langchain-anthropic`, `langchain-ollama`, `langchain-chroma`,
      `langchain-huggingface` to `[project].dependencies` in `pyproject.toml` (versions
      confirmed installable/compatible during planning: `langchain-core` 1.5.3,
      `langchain-anthropic` 1.5.3, `langchain-ollama` 1.1.0, `langchain-chroma` 1.1.0,
      `langchain-huggingface` 1.2.2 — pin with `>=` floors at these versions).
- [X] T002 Run `pip install -e .` and confirm all five import cleanly
      (`python -c "import langchain_core, langchain_anthropic, langchain_ollama, langchain_chroma, langchain_huggingface"`).

**Checkpoint**: Dependencies installed — US1 and US2 can now proceed independently.

---

## Phase 2: User Story 1 - Generation via a maintained integration (Priority: P1) 🎯 MVP

**Goal**: `analyze()`, `draft_vacancy_metadata()`, `extract_document_text()` run through
`ChatAnthropic`/`ChatOllama` instead of the raw `anthropic` SDK/raw `httpx`, with identical
external behavior (FR-001, FR-004, FR-006).

**Independent Test**: quickstart.md Scenarios 1–3 — report generation, text/vision drafting, and
Ollama's retry-once behavior all work exactly as before, validated against real backends.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T003 [P] [US1] Rewrite `tests/test_llm_claude.py`: fake `ChatAnthropic` at the
      `with_structured_output()`/`invoke()` boundary (a fake `Runnable`-like object, not
      `anthropic.Messages.create`). Assert: the Pydantic class (`CandidateReport` /
      `DraftVacancyMetadata`) is passed directly to `with_structured_output(..., method=
      "json_schema")`; a well-formed fake response comes back already validated (no manual
      `json.loads` in the provider); `anthropic.APIError` on `.invoke()` raises
      `LLMProviderError` (contracts/llm-provider-langchain.md); vision calls build a message via
      `build_vision_message()` whose content contains a `create_image_block`-shaped dict.
- [X] T004 [P] [US1] Rewrite `tests/test_llm_ollama.py`: fake `ChatOllama` similarly. Assert:
      `with_structured_output(..., method="json_schema")` is used (not `format: "json"` +
      manual parsing); a fake that raises `OutputParserException` once then succeeds is
      retried exactly once via `.with_retry(retry_if_exception_type=(OutputParserException,),
      stop_after_attempt=2)` and returns the valid result; a fake that always raises
      `OutputParserException` raises `LLMProviderError` after the retry; `httpx.HTTPError` on
      `.invoke()` raises `LLMProviderError` (research.md #3 — confirmed real exception type,
      no change to the existing catch clause's type).
- [X] T005 [P] [US1] In `tests/test_llm_claude.py` and `tests/test_llm_ollama.py`: add a test
      for `extract_document_text()` asserting it returns the chat model's plain response content
      (no `output_config`/schema involved) and raises `LLMProviderError` on the same exception
      types as the other vision paths.

### Implementation for User Story 1

- [X] T006 [US1] Rewrite `src/vacancy_radar/llm/base.py`: remove the `LLMProvider` ABC; keep
      `LLMProviderError` unchanged; add a `typing.Protocol` named `LLMProvider` (structural
      typing only, no `abstractmethod`/`ABC` — used for type hints in `api.py`, not enforcement)
      with `analyze()`/`draft_vacancy_metadata()`/`extract_document_text()` signatures unchanged
      from today; add `build_vision_message(prompt: str, image_bytes: bytes, image_media_type:
      str) -> HumanMessage` per contracts/llm-provider-langchain.md (uses
      `langchain_core.messages.content.create_image_block`).
- [X] T007 [US1] In `src/vacancy_radar/llm/prompts.py`: remove `CANDIDATE_REPORT_JSON_SCHEMA` and
      `DRAFT_METADATA_JSON_SCHEMA` (confirmed unused anywhere else — grep clean) now that
      Pydantic models are passed directly to `with_structured_output()`; keep every
      `build_*_prompt()` function unchanged (prompt text itself doesn't change — research.md #8).
- [X] T008 [US1] Rewrite `src/vacancy_radar/llm/claude.py`: `ClaudeProvider.__init__` constructs
      `ChatAnthropic(model=self.model)` instead of `anthropic.Anthropic()`; `analyze()` and
      `_draft_from_text()`/`_draft_from_image()` call
      `self._chat_model.with_structured_output(CandidateReport | DraftVacancyMetadata,
      method="json_schema").invoke(prompt_or_message)`, catching `anthropic.APIError`
      uniformly (contracts/llm-provider-langchain.md — standardizes today's inconsistent
      catch clauses); `_draft_from_image()` builds its message via
      `build_vision_message()` instead of hand-building the content list;
      `extract_document_text()` calls `self._chat_model.invoke([build_vision_message(...)])`
      and returns `response.content` directly (no schema).
- [X] T009 [US1] Rewrite `src/vacancy_radar/llm/ollama.py`: `OllamaProvider.__init__` constructs
      `ChatOllama(model=self.model, base_url=self.host)`; `analyze()`/`_draft_from_text()`/
      `_draft_from_image()` call `self._chat_model.with_structured_output(CandidateReport |
      DraftVacancyMetadata, method="json_schema").with_retry(retry_if_exception_type=
      (OutputParserException,), stop_after_attempt=2).invoke(...)`, catching
      `OutputParserException` (after the retry is exhausted) → `LLMProviderError` and
      `httpx.HTTPError` → `LLMProviderError`; remove `RETRY_INSTRUCTION` and the manual
      `json.loads`/retry loop entirely (research.md #2); `_draft_from_image()`/
      `extract_document_text()` use `build_vision_message()`; `_chat()` and its `json_format`
      parameter are removed (no longer needed — structured output vs. plain `.invoke()`
      replaces the `format: "json"` toggle).
- [X] T010 [US1] In `src/vacancy_radar/api.py`: update `get_llm_provider()`'s type hint (still
      returns `ClaudeProvider`/`OllamaProvider`, now typed as the `Protocol`-based
      `LLMProvider` from the rewritten `base.py` — construction logic itself, based on
      `LLMConfig.anthropic_api_key` presence, is unchanged from specs/009/the earlier
      auto-detect work).

**Checkpoint**: Generation runs through LangChain end-to-end — independently testable via
quickstart.md Scenarios 1–3 against a real backend, before US2 touches retrieval at all.

---

## Phase 3: User Story 2 - Retrieval via a maintained integration (Priority: P2)

**Goal**: `Retriever.query_bullets()`/`.query_similar_vacancies()` run through `langchain-chroma`
instead of `ChromaStore`, with the minimum-similarity/doc-type filtering delegated to LangChain
and the natural-key dedup/duplicate-flag logic preserved as hand-written post-processing
(FR-002, FR-008).

**Independent Test**: quickstart.md Scenario 4 plus `eval/run_eval.py`'s retrieval checks
(bullet-retrieval recall@5/MRR, similar-vacancy precision@3) at parity with pre-migration
results.

### Tests for User Story 2 ⚠️

> `tests/test_retriever.py`'s existing tests already assert the required *behavior* (near-dup
> ranking, doc_type filtering, duplicate flagging, natural-key collapsing, MIN_SIMILARITY
> cutoff, empty-collection handling) against `BagOfWordsEmbedder` and a real on-disk Chroma
> store — per FR-003/FR-008 these must keep passing unchanged, so they are the regression test
> for this story rather than being rewritten. Only the fakes they depend on change (T012).

- [X] T011 [P] [US2] In `tests/test_retriever.py`: add one new test asserting the doc-type
      filter and score threshold are actually passed to the vector store's search call (e.g. by
      asserting a posting-only query never returns a `doc_type="vacancy_meta"`/`correspondence`
      chunk even when one would otherwise rank highly) — a direct check that FR-008's delegation
      actually happens, not just that final results happen to look right.

### Implementation for User Story 2

- [X] T012 [US2] In `tests/_fakes.py`: change `FakeEmbedder`/`BagOfWordsEmbedder` to subclass
      `langchain_core.embeddings.Embeddings` — implement `embed_documents(self, texts) ->
      list[list[float]]` (existing `embed()` body) and `embed_query(self, text) -> list[float]`
      (`self.embed_documents([text])[0]`) instead of `Embedder.embed()` (research.md #7).
- [X] T013 [US2] Remove `src/vacancy_radar/embedder.py`'s `Embedder` ABC and
      `SentenceTransformersEmbedder`; replace with a `get_embeddings(model_name: str = "BAAI/
      bge-small-en-v1.5") -> Embeddings` function returning
      `langchain_huggingface.HuggingFaceEmbeddings(model_name=model_name)` (research.md #7).
- [X] T014 [US2] Rewrite `src/vacancy_radar/retriever.py` per
      contracts/retrieval-langchain.md: construct one shared `chromadb.PersistentClient` and two
      `langchain_chroma.Chroma` instances (`collection_name=BULLETS_COLLECTION` /
      `VACANCIES_COLLECTION`, same `embedding_function`); `query_bullets()` calls
      `similarity_search_with_score(query_text, k=top_k)`, converting `(Document, distance)` to
      today's `{"id", "text", "similarity"}` dict shape (`doc.id`, `doc.page_content`, `min(1.0,
      1 - distance)`); `query_similar_vacancies()` calls
      `similarity_search_with_relevance_scores(query_text, k=n_results,
      score_threshold=MIN_SIMILARITY, filter={"doc_type": doc_type} if doc_type else None)`,
      then applies the unchanged natural-key dedup (`doc.id.split("/", 1)[0]`) and
      `DUPLICATE_SIMILARITY` flagging on the returned `(Document, similarity)` pairs. Public
      signatures (`query_bullets(query_text, top_k=5) -> list[dict]`,
      `query_similar_vacancies(query_text, top_k=3, doc_type="posting") ->
      list[SimilarVacancy]`) and every module-level constant (`MIN_SIMILARITY`,
      `DUPLICATE_SIMILARITY`, `EXCERPT_LENGTH`, `OVERFETCH_MULTIPLIER`, `MAX_OVERFETCH`) are
      unchanged.
- [X] T015 [US2] Decide and act on `src/vacancy_radar/chroma_store.py`'s fate (research.md #5):
      if `ingest.py`'s `upsert`/`delete_all`/`reset_collection`/`count` calls can move onto
      `Chroma`'s equivalent methods (`add_texts`/`delete`/collection-reset) cleanly against the
      natural-key upsert pattern Constitution VI requires, migrate `ingest.py` onto `Chroma` too
      and delete `chroma_store.py`; if not, keep `chroma_store.py` scoped to `ingest.py`'s
      upsert path only (retrieval no longer uses it either way — that's this story's actual
      requirement, per FR-002).
- [X] T016 [US2] In `src/vacancy_radar/api.py`: update `get_embedder()` to call
      `embedder.get_embeddings()` (T013); update `get_retriever()`'s type hints if
      `Retriever.__init__`'s `embedder`/`store` parameter types changed (per T014/T015's actual
      shape).

**Checkpoint**: Retrieval runs through LangChain end-to-end — `test_retriever.py`'s full
existing suite passes unchanged against the new internals, independently testable via
`eval/run_eval.py`'s retrieval checks even before US1's generation changes are considered done.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T017 Run the full `pytest` suite (`test_llm_claude.py`, `test_llm_ollama.py`,
      `test_retriever.py`, `test_api.py`, `test_ui.py`, `test_ingest_upload.py`,
      `test_cli_ingest.py`, `test_llm_config.py`, everything else) and confirm every test passes
      — updating any remaining dependency-override fake in `test_api.py`/`test_ui.py`/
      `test_ingest_upload.py` whose `draft_vacancy_metadata`/`analyze`/`extract_document_text`
      stub signature needs to match the `Protocol`-based `LLMProvider` from T006 (signatures are
      unchanged, so this should mostly be a no-op check, not a rewrite).
- [X] T018 Run `eval/run_eval.py` and confirm all four checks (grounding enforcement,
      bullet-retrieval recall@5/MRR, similar-vacancy precision@3, filter-rule consistency) pass
      at parity with their pre-migration results (FR-007/SC-001 — the actual regression gate for
      this feature, not optional polish).
- [X] T019 [P] Run `ruff check .` and fix any lint findings across all files changed by this
      feature (expect unused-import removals in `llm/claude.py`/`llm/ollama.py` — `anthropic`
      SDK's request-building imports, `base64`/`json` where no longer used directly, etc.).
- [X] T020 [P] Update `CHANGELOG.md`'s `[Unreleased]` section under `### Added` only (not
      `### Changed` — nothing about public behavior changes, per FR-003, and there's no prior
      release to diff against for this specific internal rewrite): note that LLM generation and
      retrieval now run through LangChain (`ChatAnthropic`/`ChatOllama`, `langchain-chroma`)
      instead of hand-rolled clients, per the amended constitution.
- [X] T021 [P] Update `README.md`'s Stack table: change the "Generation" row to name
      `ChatAnthropic`/`ChatOllama` (via LangChain) instead of "Claude API or local Ollama"
      directly, and the "Vector DB" row to mention `langchain-chroma`'s `Chroma` wrapping the
      same embedded/persistent store.
- [X] T022 Perform manual quickstart validation per
      `specs/010-langchain-integration/quickstart.md` (all 5 scenarios) against a real Claude
      API key and a real local Ollama instance, including the vision paths (specs/007/009) and
      the Ollama retry path (Scenario 3).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS both user stories
  (both import the new packages).
- **User Story 1 (Phase 2)**: Depends on Phase 1 only. Independent of US2.
- **User Story 2 (Phase 3)**: Depends on Phase 1 only. Independent of US1 — `retriever.py` and
  `llm/` share no code.
- **Polish (Phase 4)**: Depends on both user stories being complete — T017/T018 are full-suite
  and eval-harness runs, meaningless until both migrations have landed.

### Within Each Phase

- T003/T004/T005 (US1 tests) before T006–T010 (US1 implementation) — tests-first.
- T006 (base.py: `build_vision_message`, `LLMProviderError`, `Protocol`) before T008/T009
  (both providers use `build_vision_message`).
- T007 (prompts.py schema removal) before T008 (claude.py stops importing the removed schemas).
- T012 (fakes → `Embeddings`) before T011/T014 (retriever tests and implementation both need the
  updated fakes to construct a `Chroma` instance in tests).
- T013 (embedder.py) before T014 (retriever.py constructs `Chroma` with an `Embeddings` instance)
  and before T016 (`get_embedder()` calls into it).
- T014 before T015 (chroma_store.py's fate depends on what retriever.py still needs from it,
  which is nothing after T014 — T015 is about `ingest.py`'s separate upsert path).

### Parallel Opportunities

- T003, T004, T005 (US1 tests, overlapping files but independent assertions — coordinate if
  editing the same file simultaneously) — largely parallel.
- T006 and T007 (different files) — parallel.
- T011 and T012 (different files) — parallel.
- T019, T020, T021 (Polish, different files) — parallel.
- **Phase 2 (US1) and Phase 3 (US2) as whole phases can run in parallel** once Phase 1 is done —
  they touch entirely disjoint files (`llm/*` vs. `retriever.py`/`chroma_store.py`/
  `embedder.py`/`tests/_fakes.py`/`test_retriever.py`), aside from both editing different
  functions in `api.py` (T010 vs. T016 — coordinate order if working simultaneously, no line
  overlap expected).

---

## Parallel Example: Phase 2 (User Story 1) tests

```bash
Task: "Rewrite tests/test_llm_claude.py for ChatAnthropic"
Task: "Rewrite tests/test_llm_ollama.py for ChatOllama"
Task: "Add extract_document_text() tests to both files"
```

## Parallel Example: Phase 1 + both stories

```bash
Task: "Add LangChain dependencies to pyproject.toml, pip install -e ."
# then, in parallel:
Task: "User Story 1 — migrate llm/ to BaseChatModel"
Task: "User Story 2 — migrate retriever.py to langchain-chroma"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (dependencies).
2. Complete Phase 2: User Story 1 (generation).
3. **STOP and VALIDATE**: quickstart.md Scenarios 1–3 against a real backend, plus
   `eval/run_eval.py`'s grounding-enforcement check specifically (the one check US1 alone can
   fully validate — the retrieval checks need US2).
4. This alone satisfies the constitution's higher-priority half (generation named first in the
   amendment) and is independently shippable — US2 doesn't block it.

### Incremental Delivery

1. Foundational → US1 (validate Scenarios 1–3 + grounding check) → US2 (validate Scenario 4 +
   retrieval checks) → Polish (full suite + all four eval checks at parity, manual quickstart).
2. Each phase leaves the app in a fully working state — US1 alone still has fully-functional
   (unmigrated) retrieval, and vice versa.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to its user story for traceability.
- Verify each new-behavior test fails before implementing against it.
- Stop at each checkpoint to validate independently before moving on.
- FR-007/SC-001 make this feature's Polish phase (T017/T018) load-bearing, not optional — the
  migration isn't done at "tests pass," it's done at "tests and eval harness pass at parity."
