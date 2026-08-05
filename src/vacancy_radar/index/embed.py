"""Lazy, per-model-name cached text embedding via `fastembed`.

Nothing here instantiates a model at import time: stage 8 imports this
module (transitively, via `build.py`) on every MCP client start, and
most sessions never search - paying `fastembed`'s ONNX-model load cost
on that common path would be pure waste. A model loads on the first
`embed_texts` call for its name and is reused after.
"""

from fastembed import TextEmbedding

DEFAULT_EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

_models: dict[str, TextEmbedding] = {}


def _get_model(model_name: str) -> TextEmbedding:
    if model_name not in _models:
        _models[model_name] = TextEmbedding(model_name=model_name)
    return _models[model_name]


def embed_texts(
    texts: list[str], model_name: str = DEFAULT_EMBEDDING_MODEL_NAME
) -> list[list[float]]:
    """Embed `texts`, batched, with the model for `model_name`."""
    model = _get_model(model_name)
    return [vector.tolist() for vector in model.embed(texts)]


def vector_dim(model_name: str = DEFAULT_EMBEDDING_MODEL_NAME) -> int:
    """`model_name`'s native output dimension.

    Looked up from `fastembed`'s static supported-model metadata, not
    by loading the model - this must stay cheap, since `schema.py`
    calls it on every index open.
    """
    return TextEmbedding.get_embedding_size(model_name)
