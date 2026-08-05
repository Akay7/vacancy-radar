"""The LanceDB table schema: one row per indexable document or vacancy.

No sub-document chunking - a document is the semantic unit; splitting
an email strands the signature from the ask (see design.md). Vacancy
fields are denormalized onto every document row so stage 4 filters
inside the query rather than post-filtering.

Vector dimensionality is a parameter, read from the configured
embedding model (`embed.vector_dim`), never hardcoded - changing the
model and rebuilding produces a table with the new dimensionality with
no migration step.
"""

from lancedb.pydantic import LanceModel, Vector
from pydantic import Field


def build_schema(vector_dim: int) -> type[LanceModel]:
    """Build the row schema for a table whose vectors have `vector_dim`
    dimensions."""

    class DocumentRow(LanceModel):
        doc_id: str
        vacancy_id: str
        company_slug: str
        company: str
        role: str
        status: str
        kind: str
        title: str
        path: str
        date: str
        found_date: str
        applied_date: str | None = None
        last_activity: str
        tags: list[str] = Field(default_factory=list)
        text: str
        content_hash: str
        vector: Vector(vector_dim)  # type: ignore[valid-type]

    return DocumentRow
