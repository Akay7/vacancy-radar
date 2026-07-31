"""Test-only fakes — never hits the network or downloads a real embedding model."""

from vacancy_radar.embedder import Embedder


class FakeEmbedder(Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 0.1, 0.2] for t in texts]
