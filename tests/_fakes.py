"""Test-only fakes — never hits the network or downloads a real embedding model."""

import hashlib
import re

from langchain_core.embeddings import Embeddings

BOW_VECTOR_DIM = 64


class FakeEmbedder(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 0.1, 0.2] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class BagOfWordsEmbedder(Embeddings):
    """Deterministic bag-of-words embedding — shared vocabulary means shared-word texts
    score a meaningful positive cosine similarity, unrelated texts score near zero. Used
    where a test needs realistic similarity ranking/threshold behavior without a real model.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * BOW_VECTOR_DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            index = int(hashlib.md5(word.encode()).hexdigest(), 16) % BOW_VECTOR_DIM
            vector[index] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]
