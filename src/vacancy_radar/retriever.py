"""Per-collection retrieval via langchain-chroma (specs/010-langchain-integration).

Two collections (see ../../../../learning/rag-project-plan.md in the maintainer's
private notes for full reasoning): experience_bullets, vacancies.

Every embedded vacancy chunk carries doc_type/company/position/date/outcome
metadata, so /similar can e.g. filter to doc_type=posting only for duplicate-JD
detection without pulling in correspondence.

The minimum-similarity cutoff and doc_type filter are delegated to `Chroma`'s own
`score_threshold`/`filter` search arguments (research.md #4) rather than hand-implemented
post-query filtering. Deduplicating multiple chunks from the same vacancy down to the
best-scoring one, and flagging a match as a likely duplicate above a second, higher threshold,
have no generic LangChain equivalent and stay hand-written here, operating on the scored
`Document` results `Chroma` returns.
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import get_embeddings
from vacancy_radar.ingest import (
    BULLETS_COLLECTION,
    BULLETS_COLLECTION_METADATA,
    CHROMA_PATH,
    VACANCIES_COLLECTION,
    VACANCIES_COLLECTION_METADATA,
)
from vacancy_radar.models import SimilarVacancy

# Calibrated against the real bge-small-en-v1.5 model on data/example: unrelated postings
# (different profession entirely) scored 0.47-0.59 cosine similarity against a backend-
# engineering posting, while a genuine different-role-same-domain posting scored 0.645 and a
# reworded near-duplicate scored 0.88+. 0.6 sits in the gap between those two clusters.
MIN_SIMILARITY = 0.6
DUPLICATE_SIMILARITY = 0.85
EXCERPT_LENGTH = 280
OVERFETCH_MULTIPLIER = 4
MAX_OVERFETCH = 20


def _excerpt(text: str, length: int = EXCERPT_LENGTH) -> str:
    text = text.strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


class Retriever:
    def __init__(
        self,
        chroma_path: str = CHROMA_PATH,
        store: ChromaStore | None = None,
        embedder: Embeddings | None = None,
    ) -> None:
        self.chroma_path = chroma_path
        store = store or ChromaStore(chroma_path)
        embedder = embedder or get_embeddings()

        # Must exist with the correct (cosine) metadata before Chroma wraps them — mirrors
        # ingest.py's own get_or_create_collection-before-use pattern; a collection created
        # fresh here without this would default to a non-cosine space.
        store.get_or_create_collection(BULLETS_COLLECTION, metadata=BULLETS_COLLECTION_METADATA)
        store.get_or_create_collection(
            VACANCIES_COLLECTION, metadata=VACANCIES_COLLECTION_METADATA
        )

        # One shared chromadb client (store.client) behind both Chroma wrappers — a second
        # PersistentClient pointed at the same path is exactly what ChromaStore's own docstring
        # warns against.
        self._bullets_store = Chroma(
            client=store.client, collection_name=BULLETS_COLLECTION, embedding_function=embedder
        )
        self._vacancies_store = Chroma(
            client=store.client,
            collection_name=VACANCIES_COLLECTION,
            embedding_function=embedder,
        )

    def query_bullets(self, query_text: str, top_k: int = 5) -> list[dict]:
        """Retrieve the `top_k` experience bullets most similar to `query_text`.

        No similarity threshold (unlike `query_similar_vacancies`): these bullets are
        internal grounding context for /analyze, not shown to the user directly — the
        grounding validator (`grounding.py`), not retrieval, is what gates what a report
        can actually cite (specs/003-analyze-report-generation/research.md).
        """
        results = self._bullets_store.similarity_search_with_score(query_text, k=top_k)
        return [
            {"id": doc.id, "text": doc.page_content, "similarity": min(1.0, 1 - distance)}
            for doc, distance in results
        ]

    def query_similar_vacancies(
        self, query_text: str, top_k: int = 3, doc_type: str | None = "posting"
    ) -> list[SimilarVacancy]:
        """Rank previously-ingested vacancies by similarity to `query_text`.

        Only `doc_type` chunks are compared (default "posting", per FR-004), delegated to
        `Chroma`'s `filter` search argument. Multiple chunks belonging to the same vacancy
        (natural key) are collapsed to their best-scoring hit (data-model.md's grouping rule)
        among the already-`MIN_SIMILARITY`-filtered results (delegated to `score_threshold`)
        before the `DUPLICATE_SIMILARITY` flag (FR-008) is applied.
        """
        n_results = min(max(top_k * OVERFETCH_MULTIPLIER, top_k), MAX_OVERFETCH)
        where = {"doc_type": doc_type} if doc_type else None

        results: list[tuple[Document, float]] = (
            self._vacancies_store.similarity_search_with_relevance_scores(
                query_text, k=n_results, score_threshold=MIN_SIMILARITY, filter=where
            )
        )

        best_by_key: dict[str, tuple[float, Document]] = {}
        for doc, raw_similarity in results:
            # float32 cosine math can overshoot 1.0 by a hair (e.g. 1.0000001192092896) —
            # clamped here, same as query_bullets()'s min(1.0, ...).
            similarity = min(1.0, raw_similarity)
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
