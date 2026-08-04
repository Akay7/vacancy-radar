# Contract: `Retriever` methods, migrated to `langchain-chroma`

Public signatures unchanged: `Retriever.query_bullets(query_text, top_k=5) -> list[dict]`,
`Retriever.query_similar_vacancies(query_text, top_k=3, doc_type="posting") ->
list[SimilarVacancy]` (FR-003). Internals change as follows.

## Shared setup

```python
client = chromadb.PersistentClient(path=str(Path(chroma_path).resolve()))  # one client, shared
bullets_store = Chroma(
    client=client, collection_name=BULLETS_COLLECTION, embedding_function=embeddings
)
vacancies_store = Chroma(
    client=client, collection_name=VACANCIES_COLLECTION, embedding_function=embeddings
)
```

One `chromadb.PersistentClient`, two `Chroma` wrappers — preserves `ChromaStore`'s existing
"one client, one path" invariant (research.md #4).

## `query_bullets()`

```python
results = bullets_store.similarity_search_with_score(query_text, k=top_k)
return [
    {"id": doc.id, "text": doc.page_content, "similarity": min(1.0, 1 - distance)}
    for doc, distance in results
]
```

No threshold (unchanged behavior — grounding, not retrieval, gates what's citable).
`similarity_search_with_score` (not `_with_relevance_scores`) returns raw distance, matching
today's raw-distance-to-similarity conversion exactly — `_with_relevance_scores` would apply
the same `1 - distance` formula internally, either is usable; `_with_score` is used here to
keep the `min(1.0, ...)` clamp explicit as today's code already does it.

## `query_similar_vacancies()`

```python
n_results = min(max(top_k * OVERFETCH_MULTIPLIER, top_k), MAX_OVERFETCH)
where = {"doc_type": doc_type} if doc_type else None

results = vacancies_store.similarity_search_with_relevance_scores(
    query_text, k=n_results, score_threshold=MIN_SIMILARITY, filter=where
)

best_by_key: dict[str, tuple[float, Document]] = {}
for doc, similarity in results:
    natural_key = doc.id.split("/", 1)[0]
    existing = best_by_key.get(natural_key)
    if existing is None or similarity > existing[0]:
        best_by_key[natural_key] = (similarity, doc)

matches = [
    SimilarVacancy(
        vacancy_id=natural_key,
        company=doc.metadata.get("company", ""),
        position=doc.metadata.get("position", ""),
        outcome=doc.metadata.get("outcome", ""),
        similarity=similarity,
        excerpt=_excerpt(doc.page_content),
        is_duplicate=similarity >= DUPLICATE_SIMILARITY,
    )
    for natural_key, (similarity, doc) in best_by_key.items()
]
matches.sort(key=lambda m: m.similarity, reverse=True)
return matches[:top_k]
```

`MIN_SIMILARITY`/doc-type filtering delegated to LangChain (research.md #4); natural-key
dedup + `DUPLICATE_SIMILARITY` flagging stay hand-written on the returned scored `Document`s —
same order of operations as today (filter/threshold happens at the query level now instead of
after the fact, confirmed behaviorally equivalent since dedup only ever needs the *max*-scoring
chunk per vacancy, and a chunk that would have been filtered by the threshold either way never
wins that max).

## Non-goals

- `chroma_store.py`'s ingestion-side API (`upsert`, `delete_all`, `reset_collection`) is not
  touched by this contract — see research.md #5 for its status.
- No change to `MIN_SIMILARITY`/`DUPLICATE_SIMILARITY`/`OVERFETCH_MULTIPLIER`/`MAX_OVERFETCH`
  constant values — only how they're applied.
