"""Per-collection Chroma queries with payload filtering.

Two collections (see ../../../../learning/rag-project-plan.md in the maintainer's
private notes for full reasoning): experience_bullets, vacancies.

Every embedded vacancy chunk carries doc_type/company/position/date/outcome
metadata, so /similar can e.g. filter to doc_type=posting only for duplicate-JD
detection without pulling in correspondence.
"""

from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import Embedder, SentenceTransformersEmbedder
from vacancy_radar.ingest import CHROMA_PATH, VACANCIES_COLLECTION, VACANCIES_COLLECTION_METADATA
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
        embedder: Embedder | None = None,
    ) -> None:
        self.chroma_path = chroma_path
        self._store = store or ChromaStore(chroma_path)
        self._embedder = embedder or SentenceTransformersEmbedder()

    def query_bullets(self, query_text: str, top_k: int = 5) -> list[dict]:
        raise NotImplementedError("M4")

    def query_similar_vacancies(
        self, query_text: str, top_k: int = 3, doc_type: str | None = "posting"
    ) -> list[SimilarVacancy]:
        """Rank previously-ingested vacancies by similarity to `query_text`.

        Only `doc_type` chunks are compared (default "posting", per FR-004). Multiple chunks
        belonging to the same vacancy (natural key) are collapsed to their best-scoring hit
        (data-model.md's grouping rule) before the MIN_SIMILARITY threshold (FR-007) and
        DUPLICATE_SIMILARITY flag (FR-008) are applied.
        """
        query_vector = self._embedder.embed([query_text])[0]
        n_results = min(max(top_k * OVERFETCH_MULTIPLIER, top_k), MAX_OVERFETCH)
        where = {"doc_type": doc_type} if doc_type else None

        result = self._store.query(
            VACANCIES_COLLECTION,
            query_embeddings=[query_vector],
            n_results=n_results,
            where=where,
            metadata=VACANCIES_COLLECTION_METADATA,
        )

        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        best_by_key: dict[str, tuple[float, str, dict]] = {}
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            natural_key = chunk_id.split("/", 1)[0]
            similarity = min(1.0, 1 - distance)
            existing = best_by_key.get(natural_key)
            if existing is None or similarity > existing[0]:
                best_by_key[natural_key] = (similarity, document, metadata)

        matches = [
            SimilarVacancy(
                vacancy_id=natural_key,
                company=metadata.get("company", ""),
                position=metadata.get("position", ""),
                outcome=metadata.get("outcome", ""),
                similarity=similarity,
                excerpt=_excerpt(document),
                is_duplicate=similarity >= DUPLICATE_SIMILARITY,
            )
            for natural_key, (similarity, document, metadata) in best_by_key.items()
            if similarity >= MIN_SIMILARITY
        ]

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:top_k]
