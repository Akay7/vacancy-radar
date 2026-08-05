from vacancy_radar.index.schema import build_schema

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
