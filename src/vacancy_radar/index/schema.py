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

from typing import TYPE_CHECKING

import pyarrow as pa
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field

if TYPE_CHECKING:
    from lancedb.table import Table

EMBEDDING_MODEL_METADATA_KEY = b"embedding_model"
"""The Arrow schema metadata key `build_index` stamps the active build's
embedding model name into, and `read_embedding_model` reads back - see
build.py's `_open_or_create_table` and design.md's provenance decision."""


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


def schema_with_model_metadata(
    schema: "type[LanceModel]", model_name: str
) -> pa.Schema:
    """`schema`'s Arrow form, carrying `model_name` in its schema
    metadata under `EMBEDDING_MODEL_METADATA_KEY`.

    Table-level, not a column - `model_name` describes the whole table's
    vectors, not any one row, and Arrow schema metadata already survives
    a `connect()`/`open_table()` round-trip with no extra bookkeeping."""
    return schema.to_arrow_schema().with_metadata(
        {EMBEDDING_MODEL_METADATA_KEY: model_name.encode("utf-8")}
    )


def read_embedding_model(table: "Table") -> str | None:
    """The embedding model name recorded in `table`'s schema metadata,
    or `None` if the table predates this stage's provenance amendment
    (built by an older `build_index`, or never recorded)."""
    metadata = table.schema.metadata
    if not metadata or EMBEDDING_MODEL_METADATA_KEY not in metadata:
        return None
    return metadata[EMBEDDING_MODEL_METADATA_KEY].decode("utf-8")
