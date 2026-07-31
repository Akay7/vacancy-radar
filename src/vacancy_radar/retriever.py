"""Per-collection Chroma queries with payload filtering.

Two collections (see ../../../../learning/rag-project-plan.md in the maintainer's
private notes for full reasoning): experience_bullets, vacancies.

Every embedded vacancy chunk carries doc_type/company/position/date/outcome
metadata, so /similar can e.g. filter to doc_type=posting only for duplicate-JD
detection without pulling in correspondence.
"""


class Retriever:
    def __init__(self, chroma_path: str = ".cache/chroma") -> None:
        self.chroma_path = chroma_path

    def query_bullets(self, query_text: str, top_k: int = 5) -> list[dict]:
        raise NotImplementedError("M3")

    def query_similar_vacancies(
        self, query_text: str, top_k: int = 3, doc_type: str | None = "posting"
    ) -> list[dict]:
        raise NotImplementedError("M3")
