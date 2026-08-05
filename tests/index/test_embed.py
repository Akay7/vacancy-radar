import importlib

import pytest
from fastembed import TextEmbedding

from vacancy_radar.index import embed
from vacancy_radar.index.embed import (
    DEFAULT_EMBEDDING_MODEL_NAME,
    embed_texts,
    vector_dim,
)

SECOND_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def test_importing_embed_module_does_not_load_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, object]] = []
    original_init = TextEmbedding.__init__

    def spy_init(self: TextEmbedding, *args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(TextEmbedding, "__init__", spy_init)

    importlib.reload(embed)

    assert calls == []


# test_importing_build_module_does_not_load_a_model lives in
# tests/index/test_build.py, once build.py exists (section 11).


@pytest.mark.embedding
def test_model_loads_on_first_call_and_is_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    importlib.reload(embed)
    load_count = 0
    original_init = TextEmbedding.__init__

    def counting_init(self: TextEmbedding, *args: object, **kwargs: object) -> None:
        nonlocal load_count
        load_count += 1
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(TextEmbedding, "__init__", counting_init)

    first = embed_texts(["hello world"])
    assert load_count == 1

    second = embed_texts(["a second batch of text"])
    assert load_count == 1  # reused, not reloaded
    assert len(first[0]) == len(second[0])


@pytest.mark.embedding
def test_vector_length_matches_default_model_dimension() -> None:
    vectors = embed_texts(["hello world", "another piece of text"])

    expected_dim = vector_dim(DEFAULT_EMBEDDING_MODEL_NAME)
    assert all(len(v) == expected_dim for v in vectors)


@pytest.mark.embedding
def test_changing_model_name_changes_returned_dimension() -> None:
    default_vectors = embed_texts(
        ["hello world"], model_name=DEFAULT_EMBEDDING_MODEL_NAME
    )
    second_vectors = embed_texts(["hello world"], model_name=SECOND_MODEL_NAME)

    assert len(default_vectors[0]) == vector_dim(DEFAULT_EMBEDDING_MODEL_NAME)
    assert len(second_vectors[0]) == vector_dim(SECOND_MODEL_NAME)
    assert len(default_vectors[0]) != len(second_vectors[0])
