# Research: Migrate Generation and Retrieval to LangChain

No `[NEEDS CLARIFICATION]` markers were left in the spec. Every decision below was verified
against the actually-installed packages (`pip install langchain-anthropic langchain-ollama
langchain-chroma langchain-huggingface`, current versions: `langchain-core` 1.5.3,
`langchain-anthropic` 1.5.3, `langchain-ollama` 1.1.0, `langchain-chroma` 1.1.0,
`langchain-huggingface` 1.2.2) by reading their actual source, not assumed from general
LangChain knowledge — this repo's established habit (e.g. specs/007's live SDK check that
caught the `ANTHROPIC_API_KEY` `TypeError` gap) applied to a bigger surface area.

## 1. One shared vision content-block builder works for both providers

**Decision**: Both `ChatAnthropic` and `ChatOllama` accept the same standardized
`ImageContentBlock` shape — `{"type": "image", "mime_type": "...", "base64": "..."}`, built via
`langchain_core.messages.content.create_image_block(base64=..., mime_type=...)` — inside a
`HumanMessage`'s `content` list alongside a text block. A single
`build_vision_message(prompt: str, image_bytes: bytes, image_media_type: str) -> HumanMessage`
helper replaces today's two separately-hand-built request shapes.

**Verified, not assumed**:
- Read `langchain_anthropic.chat_models._format_data_content_block()`: for `block["type"] ==
  "image"` with a `"base64"` key, it builds exactly `{"type": "image", "source": {"type":
  "base64", "media_type": block["mime_type"], "data": block["base64"]}}` — byte-for-byte the
  same shape `ClaudeProvider._draft_from_image()` hand-builds today.
- Read `langchain_ollama.chat_models._get_image_from_data_content_block()`: for the same block
  shape, it extracts `block["base64"]` directly — feeding Ollama's `images` field exactly as
  `OllamaProvider._draft_from_image()` does today.

**Alternatives considered**: Keep two provider-specific request builders (today's design) —
rejected; the whole point of this migration is not re-deriving the same request shape twice
when the library already normalizes it.

## 2. Structured output: real capability gain, one gap to close explicitly

**Decision**: `ChatAnthropic(...).with_structured_output(CandidateReport, method="json_schema")`
and `ChatOllama(...).with_structured_output(CandidateReport, method="json_schema")` both return a
validated Pydantic instance directly — no manual `json.loads()` + `model_validate()`. Claude's
`method="json_schema"` uses "Claude's dedicated structured output feature" (confirmed from the
method's own docstring) — the same underlying mechanism `output_config.format` already uses
today, not a weaker fallback. Ollama's `method="json_schema"` similarly "uses Ollama's structured
output API" (also from its docstring), a real, schema-enforced improvement over today's
prompt-engineered `format: "json"` request flag.

**Retry stays a LangChain-level concern, not hand-rolled**: `.with_structured_output()` doesn't
retry on its own, but `Runnable.with_retry(retry_if_exception_type=..., stop_after_attempt=...)`
composes directly on top of it — confirmed `langchain_ollama.chat_models` raises
`langchain_core.exceptions.OutputParserException` (a `ValueError` subclass) when a response
can't be parsed against the schema. So:

```python
structured = chat_model.with_structured_output(
    CandidateReport, method="json_schema"
).with_retry(retry_if_exception_type=(OutputParserException,), stop_after_attempt=2)
```

replaces today's hand-rolled `RETRY_INSTRUCTION`-append-and-retry-once loop entirely — one retry
(`stop_after_attempt=2`), same failure mode covered (a malformed response on the first attempt),
zero custom retry code. The one behavior difference: today's retry appends
`RETRY_INSTRUCTION` ("your previous response was not valid JSON...") to the prompt on the second
attempt; `.with_retry()` re-invokes with the identical input. This is judged an acceptable,
simpler trade-off rather than a regression — `method="json_schema"` is a materially stronger
constraint than today's prompt-engineered `format: "json"` flag, so a malformed *first* response
is expected to be rarer to begin with, and a blind retry against a schema-constrained decode is
a reasonable second attempt without needing a hand-written corrective prompt.

**Alternatives considered**:
- *Hand-roll the retry with `include_raw=True` + a `parsing_error` check* — rejected per explicit
  direction: this is exactly the kind of "reimplement it ourselves" `.with_retry()` exists to
  avoid.
- *Rely on the chat model's own `max_retries` constructor param* — rejected; that retries the
  *network call* on transport errors, not a structurally-invalid-but-successfully-returned
  response — a different failure mode, still worth keeping at its default, but not a substitute
  for `.with_retry()` on the structured-output `Runnable`.

## 3. Error handling: Claude's exceptions pass through unchanged; Ollama's confirmed at implementation time

**Decision**: Keep catching `anthropic.APIConnectionError`, `anthropic.AuthenticationError`, and
`anthropic.APIError` around `ChatAnthropic` calls, re-raising as `LLMProviderError` exactly as
today.

**Verified**: Read `langchain_anthropic.chat_models` in full for exception handling — it only
specially handles `anthropic.BadRequestError` (converting context-overflow errors into
`AnthropicContextOverflowError`). It does not catch `APIConnectionError`/`AuthenticationError`;
these propagate from the underlying `anthropic` SDK client unchanged, so the existing catch
clauses keep working as-is around the new `.invoke()`/`.with_structured_output().invoke()` calls.

**Bonus, not just parity**: the `TypeError: Could not resolve authentication method...` gap
specs/009 found (an unset `ANTHROPIC_API_KEY` isn't validated at client construction) can no
longer occur in practice post-specs/010-preceding-work: `get_llm_provider()` (specs/010's
auto-detect design, already shipped) only constructs `ChatAnthropic` when `anthropic_api_key` is
actually present. This migration doesn't need to re-solve that problem; it's already closed by
construction.

**Ollama — confirmed empirically, not guessed**: ran `ChatOllama(base_url="http://127.0.0.1:1").invoke("hello")`
against a genuinely unreachable port. `httpx.ConnectError` propagates unchanged (confirmed
`issubclass(httpx.ConnectError, httpx.HTTPError) is True`) — today's `except httpx.HTTPError`
catch in `OllamaProvider` keeps working around the new `.invoke()` calls with zero changes.
`langchain-ollama` uses `httpx` under the hood for the connection itself, same as today's direct
`httpx.post` calls, just wrapped one layer deeper.

## 4. Retrieval: `similarity_search_with_relevance_scores` replaces the threshold/filter logic exactly; dedup/duplicate-flag stay custom

**Decision**: `Chroma.similarity_search_with_relevance_scores(query_text, k=n_results,
score_threshold=MIN_SIMILARITY, filter={"doc_type": doc_type})` (inherited from
`VectorStore`'s base implementation) replaces `retriever.py`'s hand-rolled `MIN_SIMILARITY`
post-query filter and `where={"doc_type": doc_type}` construction. For bullets (no threshold
today), `Chroma.similarity_search_with_score(query_text, k=top_k)` replaces the equivalent
unfiltered query.

**Verified, not assumed**:
- Read `VectorStore.similarity_search_with_relevance_scores()`'s base implementation: it pops
  `score_threshold` from kwargs, calls the vector-store-specific scored search, and filters
  `similarity >= score_threshold` — exactly `retriever.py`'s current `if similarity >=
  MIN_SIMILARITY` logic, just inside the library instead of hand-written.
- Read `Chroma._select_relevance_score_fn()` / `_cosine_relevance_score_fn()`: for a collection
  configured with `hnsw:space: cosine`, the relevance score is `1.0 - distance` — byte-for-byte
  the same formula `retriever.py` already computes by hand (`min(1.0, 1 - distance)`). Confirmed
  both existing collections actually carry `hnsw:space: cosine` metadata (`ingest.py`'s
  `BULLETS_COLLECTION_METADATA`/`VACANCIES_COLLECTION_METADATA`), so wrapping them with `Chroma`
  produces identical relevance scores to today, not a different normalization.
- `Chroma.__init__` accepts a `client: chromadb.ClientAPI` param — one shared
  `chromadb.PersistentClient` is constructed once and passed to *two* `Chroma` instances (one per
  `collection_name`), preserving `ChromaStore`'s existing "one client, one path" invariant (its
  own docstring already explains why two clients on the same path collide).

**What has no LangChain equivalent and stays hand-written** (confirmed by reading the
`VectorStore`/`Chroma` API surface — no generic "group by derived key, keep max" or "flag above a
second threshold" method exists):
- Deduplicating multiple chunks belonging to the same vacancy (grouped by the natural-key prefix
  of the chunk id) down to the single best-scoring one.
- Flagging a match as a likely duplicate when its score clears the separate, higher
  `DUPLICATE_SIMILARITY` bar.

Both remain plain Python over the `list[tuple[Document, float]]` LangChain's scored search
returns — this is spec.md FR-008's resolution, made concrete.

**Alternatives considered**: Build a custom LangChain `Retriever` subclass encapsulating the
dedup/duplicate-flag logic — rejected; `Retriever.invoke()` returns bare `Document`s with the
score discarded (confirmed by reading `VectorStoreRetriever._get_relevant_documents`, which does
`docs = [doc for doc, _ in docs_and_similarities]`), which is exactly the wrong direction for
logic that needs the score. Calling `Chroma`'s scored-search methods directly (still "LangChain's
vector store interface," just not the `as_retriever()` wrapper) is simpler and keeps the score.

## 5. `chroma_store.py`'s remaining role

**Decision**: `chroma_store.py`'s query/retrieval responsibilities move entirely to
`langchain-chroma`'s `Chroma`. Its ingestion-side responsibilities (`upsert`, `delete`,
`delete_all`, `reset_collection`, `count` — used by `ingest.py`, not by retrieval) are
re-evaluated during implementation: `Chroma` also exposes `add_texts`/`delete`/collection-reset
equivalents, so `ingest.py` may migrate onto `Chroma` too for full consistency, or `chroma_store.py`
may be kept solely as `ingest.py`'s thin upsert wrapper if `Chroma`'s add/upsert semantics don't
line up cleanly with the natural-key upsert-by-id pattern `ingest.py` relies on (Constitution VI).
This is scoped as a `tasks.md`-level decision, not resolved here, since spec.md's FR-002 only
requires *retrieval* to move to LangChain — `ingest.py`'s upsert path is out of this feature's
stated scope (it doesn't retrieve anything) and changing it isn't necessary to satisfy any FR.

## 6. Embedder has a real behavior difference — noted, but no compat-stamp bump

**Decision**: `embedder.py` wraps `langchain_huggingface.HuggingFaceEmbeddings(model_name="BAAI/
bge-small-en-v1.5")` instead of calling `sentence_transformers.SentenceTransformer` directly.
`compat.py`'s `CURRENT_STAMP.schema_version` is **not** bumped for this.

**Verified, not assumed**: read `HuggingFaceEmbeddings._embed()`: it does `texts =
[x.replace("\n", " ") for x in texts]` before calling `SentenceTransformer.encode()`. The
current `SentenceTransformersEmbedder.embed()` does not do this, so multi-line text embeds to a
measurably different vector than before — a real difference, not a cosmetic one.

**Why no version bump, though the mechanism exists for exactly this**: the `schema_version`
mechanism (Constitution VI) protects a *real running installation's* previously-embedded store
across an upgrade. There is no such installation yet — no tagged release depends on today's
embedding output, and every current consumer (`data/example` in CI, the maintainer's own local
runs) re-ingests from source directly rather than upgrading a long-lived store in place. Bumping
`schema_version` for a difference nothing is actually running against yet is exactly the kind of
process weight Constitution IV (YAGNI) says not to add. If a real installation depending on this
matters later, `vacancy-radar reindex` already exists and is the correct manual remedy — no
enforcement machinery is needed today.

**Alternatives considered**: Bump `schema_version` anyway "to be safe" — rejected per explicit
direction: there's no release and no real run for it to protect, so it would be paying a
process cost against a risk that doesn't exist yet.

## 7. The custom `Embedder` ABC is dropped, not bridged to `Embeddings`

**Decision**: `embedder.py`'s `Embedder` ABC (`embed(texts) -> list[list[float]]`) is removed.
Code that needs an embedding function depends on `langchain_core.embeddings.Embeddings`
(`embed_documents(texts)` / `embed_query(text)`) directly — `HuggingFaceEmbeddings` for real use.
`tests/_fakes.py`'s `FakeEmbedder`/`BagOfWordsEmbedder` are changed to subclass `Embeddings`
instead of `Embedder`.

**Rationale**: `Chroma(embedding_function=...)` expects LangChain's `Embeddings` interface, not
this project's own `Embedder`. Keeping `Embedder` and writing an adapter class to bridge it to
`Embeddings` at the `Chroma` construction site would be exactly the "reimplement something
LangChain already provides" pattern this migration exists to remove — `Embedder`'s only reason
to exist was as this project's pre-migration seam for swapping embedding implementations, a job
`Embeddings` now does. Consistent with how `LLMProvider` isn't kept and adapted to
`BaseChatModel` either — it's replaced by it.

**Alternatives considered**: Keep `Embedder`, write a thin `_EmbedderAsLangChainEmbeddings`
bridge — rejected per the same "no reimplementing" direction that shaped the rest of this
migration; a bridge class is still hand-written glue code for a problem `Embeddings` already
solves by being the interface directly.

## 8. What is explicitly NOT changing

- Prompt text (`prompts.py`'s instructions to the model) stays the same in spirit — only the
  JSON-schema *plumbing* around it changes (Pydantic models passed directly to
  `with_structured_output()` instead of hand-written JSON Schema dicts + manual parsing).
- `grounding.py`'s `enforce()` function, `models.py`'s Pydantic schemas (`CandidateReport`,
  `DraftVacancyMetadata`, `Report`, `SimilarVacancy`), and every HTTP route's request/response
  shape (FR-003) are untouched.
- `LLMConfig` (specs/009) and the Claude/Ollama auto-detect-by-API-key-presence logic in
  `get_llm_provider()` are orthogonal to this migration and stay as-is — only the concrete
  classes `get_llm_provider()` returns change.
