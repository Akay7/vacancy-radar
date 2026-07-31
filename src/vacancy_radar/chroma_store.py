"""Thin wrapper around the embedded Chroma client.

One client, one path (`.cache/chroma`), shared by ingestion and (later) retrieval — so the
disposable-cache contract (delete the directory, rebuild from source) only ever has one
directory to delete.
"""

from pathlib import Path

import chromadb


class ChromaStore:
    def __init__(self, path: str = ".cache/chroma") -> None:
        # chromadb caches its internal System keyed by this exact path string (see
        # SharedSystemClient._get_identifier_from_settings) — resolving to an absolute path
        # ensures two ChromaStores that mean different directories (e.g. relative to different
        # cwds, as in tests) never collide on the same cached connection.
        self._client = chromadb.PersistentClient(path=str(Path(path).resolve()))

    def get_or_create_collection(self, name: str):
        return self._client.get_or_create_collection(name=name)

    def upsert(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> None:
        if not ids:
            return
        self.get_or_create_collection(collection).upsert(
            ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
        )

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        self.get_or_create_collection(collection).delete(ids=ids)

    def delete_all(self, collection: str) -> None:
        existing = self.get_or_create_collection(collection).get(include=[])
        ids = existing.get("ids", [])
        if ids:
            self.get_or_create_collection(collection).delete(ids=ids)

    def reset_collection(self, collection: str) -> None:
        """Drop and recreate a collection via the Chroma client API.

        Deliberately does NOT delete `.cache/chroma` on disk: doing so out from under a
        `PersistentClient` already open in this process leaves chromadb's Rust backend in a
        broken read-only state. `delete_collection` achieves the same "wipe this collection"
        outcome through the supported API instead.
        """
        try:
            self._client.delete_collection(name=collection)
        except chromadb.errors.NotFoundError:
            pass
        self.get_or_create_collection(collection)

    def count(self, collection: str) -> int:
        return self.get_or_create_collection(collection).count()
