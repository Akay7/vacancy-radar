"""Embedder interface — local sentence-transformers by default, hosted is a config swap."""

from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class SentenceTransformersEmbedder(Embedder):
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._model = None  # lazy-loaded in M2

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("M2: load sentence-transformers model and embed")
