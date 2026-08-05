import tempfile
from pathlib import Path

import lancedb

from vacancy_radar.index.schema import (
    build_schema,
    read_embedding_model,
    schema_with_model_metadata,
)

TEST_VECTOR_DIM = 8
SMALL_VECTOR_DIM = 4
LARGE_VECTOR_DIM = 384

EXPECTED_COLUMNS = {
    "doc_id",
    "vacancy_id",
    "company_slug",
    "company",
    "role",
    "status",
    "kind",
    "title",
    "path",
    "date",
    "found_date",
    "applied_date",
    "last_activity",
    "tags",
    "text",
    "content_hash",
    "vector",
}


def test_column_set_matches_the_spec() -> None:
    schema = build_schema(vector_dim=TEST_VECTOR_DIM)

    assert set(schema.model_fields.keys()) == EXPECTED_COLUMNS


def test_vector_field_has_the_requested_fixed_dimensionality() -> None:
    schema = build_schema(vector_dim=TEST_VECTOR_DIM)
    arrow_schema = schema.to_arrow_schema()

    vector_field = arrow_schema.field("vector")
    assert vector_field.type.list_size == TEST_VECTOR_DIM


def test_a_different_vector_dim_produces_a_different_schema() -> None:
    small = build_schema(vector_dim=SMALL_VECTOR_DIM)
    large = build_schema(vector_dim=LARGE_VECTOR_DIM)

    assert small.to_arrow_schema().field("vector").type.list_size == SMALL_VECTOR_DIM
    assert large.to_arrow_schema().field("vector").type.list_size == LARGE_VECTOR_DIM


# --- Embedding-model provenance (stage 4) -----------------------------------


def test_freshly_created_table_records_model_name_across_reconnect() -> None:
    schema = build_schema(vector_dim=TEST_VECTOR_DIM)
    arrow_schema = schema_with_model_metadata(schema, "BAAI/bge-small-en-v1.5")

    with tempfile.TemporaryDirectory() as tmp:
        db = lancedb.connect(Path(tmp))
        db.create_table("documents", schema=arrow_schema)

        reopened = lancedb.connect(Path(tmp)).open_table("documents")
        assert read_embedding_model(reopened) == "BAAI/bge-small-en-v1.5"


def test_read_embedding_model_returns_none_when_absent() -> None:
    schema = build_schema(vector_dim=TEST_VECTOR_DIM)

    with tempfile.TemporaryDirectory() as tmp:
        db = lancedb.connect(Path(tmp))
        db.create_table("documents", schema=schema)

        table = lancedb.connect(Path(tmp)).open_table("documents")
        assert read_embedding_model(table) is None
