# Data Model: Migrate Generation and Retrieval to LangChain

No new persisted entities, and no change to any existing Pydantic schema's *fields* —
`CandidateReport`, `DraftVacancyMetadata`, `Report`, `SimilarVacancy` (`models.py`) are all
unchanged (FR-003/FR-004). What changes is which library reads/writes them and how the
underlying vector store is queried.

## `CandidateReport` / `DraftVacancyMetadata` — now passed directly as schemas

Today, `CANDIDATE_REPORT_JSON_SCHEMA`/`DRAFT_METADATA_JSON_SCHEMA` (hand-written JSON Schema
dicts in `prompts.py`) are passed to `output_config`/`format`, and the raw text response is
manually `json.loads()`-ed and `model_validate()`-ed.

After migration: the Pydantic classes themselves are passed to `.with_structured_output()`,
which returns a validated instance directly:

```python
structured_llm = chat_model.with_structured_output(CandidateReport, method="json_schema")
result: CandidateReport = structured_llm.invoke(prompt)  # already validated, no json.loads
```

The hand-written JSON Schema dicts in `prompts.py` become unnecessary for this purpose (kept
only if still needed for prompt text construction, e.g. describing the shape in English to the
model — a `tasks.md`-level decision).

## Retrieval's intermediate shape: `list[tuple[Document, float]]`

`Chroma`'s scored-search methods return LangChain's own `Document` (`page_content: str`,
`metadata: dict`) paired with a relevance score, instead of `chroma_store.py`'s raw dict shape
(`{"ids": [[...]], "documents": [[...]], "metadatas": [[...]], "distances": [[...]]}`).
`retriever.py`'s post-processing (natural-key dedup, `DUPLICATE_SIMILARITY` flagging) is rewritten
against this shape:

```python
results: list[tuple[Document, float]] = vectorstore.similarity_search_with_relevance_scores(
    query_text, k=n_results, score_threshold=MIN_SIMILARITY, filter={"doc_type": doc_type}
)
# each Document.metadata carries company/position/date/outcome/doc_type — same fields
# ingest.py already writes today, now read via LangChain's Document instead of a raw dict.
```

Public function signatures (`Retriever.query_bullets() -> list[dict]`,
`Retriever.query_similar_vacancies() -> list[SimilarVacancy]`) are unchanged — this is an
internal implementation detail of `retriever.py`, invisible to `api.py`'s callers (FR-003).

## `compat.CompatStamp` — unchanged

Not touched by this migration (research.md #6) — no real running installation currently depends
on today's embedding output to protect, so the version stamp stays as-is; `vacancy-radar
reindex` remains the manual remedy if it's ever needed.
